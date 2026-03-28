from __future__ import annotations

import math

from tradingcat.config import RiskConfig
from tradingcat.domain.models import AssetClass, KillSwitchEvent, Market, OrderIntent, Signal
from tradingcat.repositories.state import KillSwitchRepository


class RiskViolation(Exception):
    pass


class RiskEngine:
    def __init__(self, config: RiskConfig, kill_switch_repository: KillSwitchRepository | None = None) -> None:
        self._config = config
        self._kill_switch = False
        self._kill_switch_repository = kill_switch_repository
        self._kill_switch_events = kill_switch_repository.load() if kill_switch_repository is not None else {}
        if self._kill_switch_events:
            latest = max(self._kill_switch_events.values(), key=lambda event: event.changed_at)
            self._kill_switch = latest.enabled

    def set_kill_switch(self, enabled: bool, reason: str | None = None) -> KillSwitchEvent:
        self._kill_switch = enabled
        event = KillSwitchEvent(enabled=enabled, reason=reason)
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
    ) -> list[OrderIntent]:
        if self._kill_switch:
            raise RiskViolation("Kill switch is active")
        if abs(daily_pnl) >= portfolio_nav * self._config.daily_stop_loss and daily_pnl < 0:
            raise RiskViolation("Daily loss limit breached")
        if abs(weekly_pnl) >= portfolio_nav * self._config.weekly_drawdown_limit and weekly_pnl < 0:
            raise RiskViolation("Weekly loss limit breached")

        intents: list[OrderIntent] = []
        cash_remaining = available_cash
        market_cash_remaining = dict(available_cash_by_market or {})
        option_premium_risk = 0.0
        for signal in signal_set:
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
