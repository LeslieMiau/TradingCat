from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from tradingcat.config import RiskConfig
from tradingcat.domain.models import AssetClass, Instrument, KillSwitchEvent, Market, OrderIntent, OrderSide, PortfolioSnapshot, Signal
from tradingcat.repositories.state import KillSwitchRepository


class RiskViolation(Exception):
    pass


@dataclass(slots=True)
class IntradayRiskCheck:
    breached: list[dict[str, object]] = field(default_factory=list)
    kill_switch_activated: bool = False
    kill_switch_already_active: bool = False
    nav_available: bool = True

    @property
    def severity(self) -> str:
        if self.kill_switch_activated or not self.nav_available:
            return "error"
        if self.breached:
            return "warning"
        return "info"


class RiskEngine:
    def __init__(self, config: RiskConfig, kill_switch_repository: KillSwitchRepository | None = None) -> None:
        self._config = config
        self._kill_switch = False
        self._kill_switch_repository = kill_switch_repository
        self._kill_switch_events = kill_switch_repository.load() if kill_switch_repository is not None else {}
        if self._kill_switch_events:
            latest = max(self._kill_switch_events.values(), key=lambda event: event.changed_at)
            self._kill_switch = latest.enabled

    def set_kill_switch(
        self,
        enabled: bool,
        reason: str | None = None,
        *,
        detected_at: datetime | None = None,
    ) -> KillSwitchEvent:
        self._kill_switch = enabled
        event = KillSwitchEvent(enabled=enabled, reason=reason, detected_at=detected_at)
        self._kill_switch_events[event.id] = event
        if self._kill_switch_repository is not None:
            self._kill_switch_repository.save(self._kill_switch_events)
        return event

    def kill_switch_status(self) -> dict[str, object]:
        events = sorted(self._kill_switch_events.values(), key=lambda item: item.changed_at, reverse=True)
        return {
            "enabled": self._kill_switch,
            "count": len(events),
            "latest": events[0] if events else None,
            "recent": events[:10],
        }

    def kill_switch_events(self) -> list[KillSwitchEvent]:
        return sorted(self._kill_switch_events.values(), key=lambda item: item.changed_at)

    def config_snapshot(self) -> dict[str, object]:
        return self._config.model_dump(mode="json")

    def update_config(self, **changes: float) -> dict[str, object]:
        for key, value in changes.items():
            setattr(self._config, key, value)
        return self.config_snapshot()

    def check(
        self,
        signal_set: list[Signal],
        portfolio_nav: float,
        drawdown: float,
        daily_pnl: float,
        weekly_pnl: float,
        prices: dict[str, float] | None = None,
        available_cash: float | None = None,
        available_cash_by_market: dict[Market, float] | None = None,
        portfolio_source: str = "live",
    ) -> list[OrderIntent]:
        if self._kill_switch:
            raise RiskViolation("Kill switch is active")
        portfolio_degraded = portfolio_source == "degraded"
        if abs(daily_pnl) >= portfolio_nav * self._config.daily_stop_loss and daily_pnl < 0:
            raise RiskViolation("Daily loss limit breached")
        if abs(weekly_pnl) >= portfolio_nav * self._config.weekly_drawdown_limit and weekly_pnl < 0:
            raise RiskViolation("Weekly loss limit breached")

        intents: list[OrderIntent] = []
        cash_remaining = available_cash
        market_cash_remaining = dict(available_cash_by_market or {})
        option_premium_risk = 0.0
        for signal in signal_set:
            # Fail-closed on broker degradation: refuse new opens (BUY) when the live
            # portfolio snapshot is stale. Closes (SELL) are still permitted because
            # an operator may need to flatten exposure during an outage.
            if portfolio_degraded and signal.side == OrderSide.BUY:
                raise RiskViolation(
                    "Portfolio snapshot is degraded (broker unavailable) — fail-closed on new buys"
                )
            self._check_cn_market_rules(signal, prices)
            max_weight = (
                self._config.max_single_etf_weight
                if signal.instrument.asset_class == AssetClass.ETF
                else self._config.max_single_stock_weight
            )
            if signal.target_weight > max_weight:
                raise RiskViolation(f"Target weight exceeds limit for {signal.instrument.symbol}")
            if drawdown >= self._config.no_new_risk_drawdown:
                raise RiskViolation("Portfolio drawdown lockout is active")

            scaled_weight = signal.target_weight / 2 if drawdown >= self._config.half_risk_drawdown else signal.target_weight
            target_notional = portfolio_nav * scaled_weight
            if cash_remaining is not None:
                target_notional = min(target_notional, cash_remaining)
            if signal.instrument.market in market_cash_remaining:
                target_notional = min(target_notional, market_cash_remaining[signal.instrument.market])

            reference_price = self._resolve_reference_price(signal, prices)
            lot_size = self._lot_size(signal.instrument.market)
            quantity = self._quantize_quantity(target_notional, reference_price, lot_size)
            if quantity <= 0:
                continue
            option_notional = quantity * reference_price if signal.instrument.asset_class == AssetClass.OPTION else 0.0
            if signal.instrument.asset_class == AssetClass.OPTION:
                if option_notional > portfolio_nav * self._config.max_daily_option_premium_risk:
                    raise RiskViolation(f"Daily option premium risk exceeded for {signal.instrument.symbol}")
                if option_premium_risk + option_notional > portfolio_nav * self._config.max_total_option_risk:
                    raise RiskViolation("Total option risk budget exceeded")

            intents.append(
                OrderIntent(
                    signal_id=signal.id,
                    instrument=signal.instrument,
                    side=signal.side,
                    quantity=quantity,
                    requires_approval=signal.instrument.market.value == "CN",
                    notes=signal.reason,
                )
            )
            option_premium_risk += option_notional
            if cash_remaining is not None and signal.side.value == "buy":
                cash_remaining = max(0.0, cash_remaining - (quantity * reference_price))
            if signal.side.value == "buy" and signal.instrument.market in market_cash_remaining:
                market_cash_remaining[signal.instrument.market] = max(
                    0.0,
                    market_cash_remaining[signal.instrument.market] - (quantity * reference_price),
                )
        return intents

    def evaluate_intraday(
        self,
        snapshot: PortfolioSnapshot | None,
        *,
        detected_at: datetime | None = None,
    ) -> IntradayRiskCheck:
        """Read-only intraday risk check with automatic kill-switch activation on hard breaches.

        Fail-closed: if no snapshot is available (e.g. broker degraded), treat NAV as
        unavailable and activate the kill switch so no new orders are accepted until an
        operator clears it.
        """
        result = IntradayRiskCheck()
        if snapshot is None or snapshot.nav <= 0:
            result.nav_available = False
            if not self._kill_switch:
                self.set_kill_switch(
                    True,
                    reason="Intraday tick: NAV unavailable (fail-closed)",
                    detected_at=detected_at,
                )
                result.kill_switch_activated = True
            else:
                result.kill_switch_already_active = True
            return result

        if self._kill_switch:
            result.kill_switch_already_active = True

        nav = snapshot.nav
        if snapshot.daily_pnl < 0 and abs(snapshot.daily_pnl) >= nav * self._config.daily_stop_loss:
            result.breached.append(
                {
                    "rule": "daily_stop_loss",
                    "threshold": self._config.daily_stop_loss,
                    "observed": round(snapshot.daily_pnl / nav, 6),
                    "message": "Daily loss limit breached",
                }
            )
        if snapshot.weekly_pnl < 0 and abs(snapshot.weekly_pnl) >= nav * self._config.weekly_drawdown_limit:
            result.breached.append(
                {
                    "rule": "weekly_drawdown_limit",
                    "threshold": self._config.weekly_drawdown_limit,
                    "observed": round(snapshot.weekly_pnl / nav, 6),
                    "message": "Weekly loss limit breached",
                }
            )
        if snapshot.drawdown >= self._config.no_new_risk_drawdown:
            result.breached.append(
                {
                    "rule": "no_new_risk_drawdown",
                    "threshold": self._config.no_new_risk_drawdown,
                    "observed": round(snapshot.drawdown, 6),
                    "message": "Portfolio drawdown lockout threshold hit",
                }
            )

        if result.breached and not self._kill_switch:
            reason = "Intraday tick: " + "; ".join(str(item["message"]) for item in result.breached)
            self.set_kill_switch(True, reason=reason, detected_at=detected_at)
            result.kill_switch_activated = True

        return result

    def _resolve_reference_price(self, signal: Signal, prices: dict[str, float] | None) -> float:
        if prices is not None:
            candidate = prices.get(signal.instrument.symbol)
            if candidate is not None and math.isfinite(candidate) and candidate > 0:
                return candidate
        return self._fallback_reference_price(signal)

    def fallback_reference_price(self, signal: Signal) -> float:
        return self._fallback_reference_price(signal)

    def _fallback_reference_price(self, signal: Signal) -> float:
        if signal.instrument.market == Market.US:
            return self._config.fallback_price_us_etf if signal.instrument.asset_class == AssetClass.ETF else self._config.fallback_price_us_stock
        if signal.instrument.market == Market.HK:
            return self._config.fallback_price_hk
        if signal.instrument.market == Market.CN:
            return self._config.fallback_price_cn_etf if signal.instrument.asset_class == AssetClass.ETF else self._config.fallback_price_cn_stock
        return 100.0

    def _lot_size(self, market: Market) -> float:
        if market in {Market.HK, Market.CN}:
            return 100.0
        return 1.0

    def _quantize_quantity(self, notional: float, price: float, lot_size: float) -> float:
        raw_quantity = notional / price
        lots = math.floor(raw_quantity / lot_size)
        return round(lots * lot_size, 2)

    def _check_cn_market_rules(self, signal: Signal, prices: dict[str, float] | None) -> None:
        if not self._config.cn_market_rules_enabled or signal.instrument.market != Market.CN:
            return
        if self._is_st_or_delisting(signal.instrument):
            raise RiskViolation(f"CN risk flag blocks trading for {signal.instrument.symbol}")

        metadata = signal.metadata or {}
        if signal.side.value == "sell" and self._is_t_plus_one_locked(signal):
            raise RiskViolation(f"CN T+1 sell lock active for {signal.instrument.symbol}")

        limit_status = str(metadata.get("limit_status") or "").lower()
        if signal.side.value == "buy" and limit_status in {"up", "limit_up"}:
            raise RiskViolation(f"CN limit-up blocks buy for {signal.instrument.symbol}")
        if signal.side.value == "sell" and limit_status in {"down", "limit_down"}:
            raise RiskViolation(f"CN limit-down blocks sell for {signal.instrument.symbol}")

        previous_close = self._metadata_float(metadata.get("previous_close"))
        current_price = self._metadata_float(metadata.get("current_price"))
        if current_price is None and prices is not None:
            current_price = self._metadata_float(prices.get(signal.instrument.symbol))
        if previous_close is None or current_price is None or previous_close <= 0:
            raise RiskViolation(f"CN price data unavailable for {signal.instrument.symbol}")

        limit_pct = self._cn_limit_pct(signal.instrument)
        limit_up = previous_close * (1 + limit_pct)
        limit_down = previous_close * (1 - limit_pct)
        tolerance = max(previous_close * 0.0005, 0.001)
        if signal.side.value == "buy" and current_price >= limit_up - tolerance:
            raise RiskViolation(f"CN limit-up blocks buy for {signal.instrument.symbol}")
        if signal.side.value == "sell" and current_price <= limit_down + tolerance:
            raise RiskViolation(f"CN limit-down blocks sell for {signal.instrument.symbol}")

    def _cn_limit_pct(self, instrument: Instrument) -> float:
        if self._is_st_or_delisting(instrument):
            return self._config.cn_limit_pct_st
        symbol = instrument.symbol.strip()
        if symbol.startswith(("300", "301", "688")):
            return self._config.cn_limit_pct_growth_board
        return self._config.cn_limit_pct_regular

    @staticmethod
    def _is_st_or_delisting(instrument: Instrument) -> bool:
        text = f"{instrument.symbol} {instrument.name} {' '.join(instrument.tags)}".casefold()
        if re.search(r"\bst\b", text):
            return True
        return any(flag in text for flag in {"退市", "delisting"})

    @staticmethod
    def _is_t_plus_one_locked(signal: Signal) -> bool:
        bought_at = signal.metadata.get("bought_at") or signal.metadata.get("acquired_at") or signal.metadata.get("last_buy_date")
        if bought_at is None:
            return False
        bought_date = RiskEngine._metadata_date(bought_at)
        if bought_date is None:
            return False
        return bought_date == signal.generated_at.date()

    @staticmethod
    def _metadata_float(raw: object) -> float | None:
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @staticmethod
    def _metadata_date(raw: object):
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw).date()
            except ValueError:
                try:
                    return date.fromisoformat(raw)
                except ValueError:
                    return None
        return None
