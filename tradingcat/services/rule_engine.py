from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from tradingcat.config import AppConfig
from tradingcat.domain.models import AssetClass, Instrument, Market, OrderIntent
from tradingcat.domain.triggers import SmartOrder
from tradingcat.services.execution import ExecutionService
from tradingcat.services.market_data import MarketDataService


logger = logging.getLogger(__name__)


class TriggerRepository:
    def __init__(self, config: AppConfig) -> None:
        self._path = config.data_dir / "triggers.json"

    def load(self) -> dict[str, SmartOrder]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return {key: SmartOrder.model_validate(value) for key, value in data.items()}
        except Exception:
            logger.exception("Failed to load smart-order trigger state; starting from empty repository")
            return {}

    def save(self, triggers: dict[str, SmartOrder]) -> None:
        raw = {key: json.loads(value.model_dump_json()) for key, value in triggers.items()}
        self._path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


class RuleEngine:
    def __init__(
        self,
        config: AppConfig,
        repository: TriggerRepository,
        market_data: MarketDataService,
        execution: ExecutionService,
    ) -> None:
        self._config = config
        self._repository = repository
        self._market_data = market_data
        self._execution = execution
        self._triggers = self._repository.load()

    def register_order(self, order: SmartOrder) -> SmartOrder:
        self._triggers[order.smart_order_id] = order
        self._repository.save(self._triggers)
        return order

    def list_orders(self) -> list[SmartOrder]:
        return list(self._triggers.values())

    def cancel_order(self, trigger_id: str) -> None:
        if trigger_id in self._triggers:
            self._triggers[trigger_id].status = "CANCELLED"
            self._repository.save(self._triggers)

    def evaluate_all(self) -> dict[str, object]:
        instruments = self._pending_instruments()
        quotes = self._market_data.fetch_quotes(instruments) if instruments else {}
        return self._evaluate_pending(quotes)

    async def evaluate_all_async(self) -> dict[str, object]:
        instruments = self._pending_instruments()
        quotes = await self._market_data.fetch_quotes_async(instruments) if instruments else {}
        return self._evaluate_pending(quotes)

    def _pending_instruments(self) -> list[Instrument]:
        instruments: dict[str, Instrument] = {}
        for order in self._triggers.values():
            if order.status != "PENDING":
                continue
            market = Market(str(order.market))
            key = f"{market.value}:{order.symbol}"
            instruments[key] = Instrument(symbol=order.symbol, market=market, asset_class=AssetClass.STOCK)
        return list(instruments.values())

    def _evaluate_pending(self, quotes: dict[str, float]) -> dict[str, object]:
        pending = [order for order in self._triggers.values() if order.status == "PENDING"]
        if not pending:
            return {"evaluated": 0, "triggered": 0, "failed": 0}

        triggered_count = 0
        failed_count = 0
        updated = False
        results: list[dict[str, object]] = []
        now = datetime.now(timezone.utc)

        for order in pending:
            price = float(quotes.get(order.symbol, 100.0))
            all_met, condition_results = self._evaluate_conditions(order, price)
            order.last_evaluated_at = now
            order.evaluation_summary = {
                "symbol": order.symbol,
                "market": order.market,
                "price": price,
                "all_conditions_met": all_met,
                "conditions": condition_results,
            }
            updated = True
            result_row = {
                "smart_order_id": order.smart_order_id,
                "symbol": order.symbol,
                "market": order.market,
                "status": order.status,
                "triggered": False,
                "conditions": condition_results,
                "reasons": [
                    {
                        "metric": item["metric"],
                        "reason_type": item["reason_type"],
                        "reason": item["reason"],
                    }
                    for item in condition_results
                    if not bool(item["passed"])
                ],
            }
            if not all_met:
                results.append(result_row)
                continue

            order.status = "TRIGGERED"
            order.triggered_at = now
            intent = self._build_intent(order, price)
            try:
                self._execution.register_expected_prices([intent], {order.symbol: price}, source="trigger_quote")
                report = self._execution.submit(intent)
                order.execution_order_id = report.broker_order_id
                triggered_count += 1
                result_row["status"] = order.status
                result_row["triggered"] = True
            except Exception:
                logger.exception("Smart order execution failed", extra={"smart_order_id": order.smart_order_id, "symbol": order.symbol})
                order.status = "FAILED"
                failed_count += 1
                result_row["status"] = order.status
                result_row["reasons"].append(
                    {
                        "metric": "EXECUTION",
                        "reason_type": "execution_failed",
                        "reason": "Order submission failed after trigger conditions passed.",
                    }
                )
            results.append(result_row)

        if updated or triggered_count > 0 or failed_count > 0:
            self._repository.save(self._triggers)

        return {"evaluated": len(pending), "triggered": triggered_count, "failed": failed_count, "results": results}

    def _evaluate_conditions(self, order: SmartOrder, price: float) -> tuple[bool, list[dict[str, object]]]:
        results: list[dict[str, object]] = []
        all_met = True
        for condition in order.trigger_conditions:
            observation = self._metric_observation(condition.metric, order.symbol, Market(str(order.market)), price)
            value = float(observation["value"])
            target = condition.target_value
            data_ready = bool(observation["data_ready"])
            passed = data_ready and self._compare(value=value, operator=condition.operator, target=target)
            reason_type, reason = self._condition_reason(
                metric=condition.metric,
                operator=condition.operator,
                target=target,
                value=value,
                data_ready=data_ready,
                observation_reason=str(observation.get("reason", "")),
            )
            results.append(
                {
                    "metric": condition.metric,
                    "operator": condition.operator,
                    "target": target,
                    "value": value,
                    "passed": passed,
                    "data_ready": data_ready,
                    "source": observation["source"],
                    "reason_type": reason_type,
                    "reason": reason,
                }
            )
            if not passed:
                logger.info("Smart order condition not met", extra={"smart_order_id": order.smart_order_id, "metric": condition.metric, "value": value, "operator": condition.operator, "target": target})
                all_met = False
        return all_met, results

    def _metric_value(self, metric: str, symbol: str, market: Market, price: float) -> float:
        return float(self._metric_observation(metric, symbol, market, price)["value"])

    def _metric_observation(self, metric: str, symbol: str, market: Market, price: float) -> dict[str, object]:
        metric_upper = metric.upper()
        if metric_upper == "PRICE":
            return {"value": price, "data_ready": True, "source": "quote", "reason": ""}
        if metric_upper.startswith("RSI"):
            period = self._metric_period(metric_upper, default=14)
            return self._rsi_observation(symbol=symbol, market=market, period=period, metric=metric_upper)
        if metric_upper.startswith("SMA"):
            period = self._metric_period(metric_upper, default=20)
            return self._sma_observation(symbol=symbol, market=market, period=period, metric=metric_upper)
        return {"value": price, "data_ready": True, "source": "quote", "reason": ""}

    def _metric_period(self, metric: str, default: int) -> int:
        parts = metric.split("_", 1)
        if len(parts) != 2:
            return default
        try:
            value = int(parts[1])
        except ValueError:
            return default
        return value if value > 0 else default

    def _rsi_observation(self, *, symbol: str, market: Market, period: int, metric: str) -> dict[str, object]:
        closes = self._recent_closes(symbol=symbol, market=market, lookback_days=max(period * 4, 30))
        if len(closes) <= period:
            return {
                "value": 50.0,
                "data_ready": False,
                "source": "history",
                "reason": f"{metric} needs {period + 1} closes but only {len(closes)} are available.",
            }
        deltas = [current - previous for previous, current in zip(closes, closes[1:], strict=False)]
        window = deltas[-period:]
        average_gain = sum(max(delta, 0.0) for delta in window) / period
        average_loss = sum(abs(min(delta, 0.0)) for delta in window) / period
        if average_loss == 0:
            value = 100.0 if average_gain > 0 else 50.0
            return {"value": value, "data_ready": True, "source": "history", "reason": ""}
        relative_strength = average_gain / average_loss
        return {"value": round(100.0 - (100.0 / (1.0 + relative_strength)), 4), "data_ready": True, "source": "history", "reason": ""}

    def _sma_observation(self, *, symbol: str, market: Market, period: int, metric: str) -> dict[str, object]:
        closes = self._recent_closes(symbol=symbol, market=market, lookback_days=max(period * 4, 30))
        if len(closes) < period:
            return {
                "value": closes[-1] if closes else 0.0,
                "data_ready": False,
                "source": "history",
                "reason": f"{metric} needs {period} closes but only {len(closes)} are available.",
            }
        window = closes[-period:]
        return {"value": round(sum(window) / len(window), 4), "data_ready": True, "source": "history", "reason": ""}

    def _recent_closes(self, *, symbol: str, market: Market, lookback_days: int) -> list[float]:
        end = date.today()
        start = end - timedelta(days=lookback_days)
        bars = self._market_data.ensure_history([symbol], start, end).get(symbol, [])
        ordered = sorted(
            bars,
            key=lambda item: (
                item.timestamp.year,
                item.timestamp.month,
                item.timestamp.day,
                item.timestamp.hour,
                item.timestamp.minute,
                item.timestamp.second,
                item.timestamp.microsecond,
            ),
        )
        return [float(bar.close) for bar in ordered if getattr(bar.instrument, "market", market) == market]

    def _compare(self, *, value: float, operator: str, target: float) -> bool:
        if operator == "<":
            return value < target
        if operator == "<=":
            return value <= target
        if operator == ">":
            return value > target
        if operator == ">=":
            return value >= target
        if operator == "==":
            return value == target
        return False

    def _condition_reason(
        self,
        *,
        metric: str,
        operator: str,
        target: float,
        value: float,
        data_ready: bool,
        observation_reason: str,
    ) -> tuple[str, str]:
        metric_upper = metric.upper()
        if not data_ready:
            return "data_missing", observation_reason or f"{metric} is missing required data."
        if self._compare(value=value, operator=operator, target=target):
            return "passed", "Condition passed."
        if metric_upper == "PRICE":
            return "price_not_reached", f"PRICE value {value:.4f} did not satisfy {operator} {target:.4f}."
        if metric_upper.startswith(("RSI", "SMA")):
            return "indicator_not_met", f"{metric_upper} value {value:.4f} did not satisfy {operator} {target:.4f}."
        return "condition_not_met", f"{metric_upper} value {value:.4f} did not satisfy {operator} {target:.4f}."

    def _build_intent(self, order: SmartOrder, reference_price: float) -> OrderIntent:
        market = Market(str(order.market))
        instrument = Instrument(symbol=order.symbol, market=market, asset_class=AssetClass.STOCK)
        return OrderIntent(
            signal_id=f"smart_order:{order.smart_order_id}",
            instrument=instrument,
            side=order.side,
            quantity=order.quantity,
            requires_approval=(market == Market.CN),
            notes=f"Smart order {order.smart_order_id} triggered",
            metadata={"trigger_context": order.evaluation_summary},
        )
