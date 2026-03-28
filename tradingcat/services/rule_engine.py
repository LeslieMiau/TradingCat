import json
from datetime import datetime, timezone
from pathlib import Path

from tradingcat.config import AppConfig
from tradingcat.domain.triggers import SmartOrder
from tradingcat.domain.models import OrderIntent
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.execution import ExecutionService


class TriggerRepository:
    def __init__(self, config: AppConfig) -> None:
        self._path = config.data_dir / "triggers.json"
        
    def load(self) -> dict[str, SmartOrder]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text())
            return {k: SmartOrder.model_validate(v) for k, v in data.items()}
        except Exception:
            return {}
            
    def save(self, triggers: dict[str, SmartOrder]) -> None:
        raw = {k: json.loads(v.model_dump_json()) for k, v in triggers.items()}
        self._path.write_text(json.dumps(raw, indent=2))


class RuleEngine:
    def __init__(
        self,
        repository: TriggerRepository,
        market_data: MarketDataService,
        execution: ExecutionService
    ) -> None:
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
        pending = [v for v in self._triggers.values() if v.status == "PENDING"]
        if not pending:
            return {"evaluated": 0, "triggered": 0}
            
        symbols = list({order.symbol for order in pending})
        quotes = self._market_data.fetch_quotes(symbols) if hasattr(self._market_data, "fetch_quotes") else {}
        # In a real system, we'd also calculate RSI, SMAs, etc.
        # For Phase 2 sandbox, we use spot price or mock indicators
        
        triggered_count = 0
        now = datetime.now(timezone.utc)
        
        for order in pending:
            price = quotes.get(order.symbol, 100.0)  # Fallback 100
            
            # Evaluate all conditions (AND logic)
            all_met = True
            for cond in order.trigger_conditions:
                # Simulating metric fetching
                if cond.metric.upper() == "PRICE":
                    val = price
                elif cond.metric.upper().startswith("RSI"):
                    val = 30.0  # Simulated
                elif cond.metric.upper().startswith("SMA"):
                    val = price * 0.95  # Simulated
                else:
                    val = price
                    
                target = cond.target_value
                if cond.operator == "<" and not (val < target):
                    all_met = False
                    break
                elif cond.operator == "<=" and not (val <= target):
                    all_met = False
                    break
                elif cond.operator == ">" and not (val > target):
                    all_met = False
                    break
                elif cond.operator == ">=" and not (val >= target):
                    all_met = False
                    break
                elif cond.operator == "==" and not (val == target):
                    all_met = False
                    break
                    
            if all_met:
                order.status = "TRIGGERED"
                order.triggered_at = now
                # Fire an execution intent immediately
                intent = OrderIntent(
                    strategy_id="complex_trigger",
                    symbol=order.symbol,
                    market=order.market,
                    side=order.side,
                    quantity=order.quantity,
                    reference_price=price,
                    reason=f"Smart order {order.smart_order_id} triggered",
                    requires_approval=False
                )
                try:
                    report = self._execution.execute_intent(intent, enforce_gate=False)
                    order.execution_order_id = report.broker_order_id
                except Exception:
                    pass
                triggered_count += 1
                
        if triggered_count > 0:
            self._repository.save(self._triggers)
            
        return {
            "evaluated": len(pending),
            "triggered": triggered_count
        }
