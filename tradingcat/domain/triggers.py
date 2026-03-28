import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from tradingcat.domain.models import OrderSide


class TriggerCondition(BaseModel):
    metric: str  # e.g., "PRICE", "RSI_14", "SMA_200"
    operator: str  # "<", "<=", ">", ">=", "=="
    target_value: float


class SmartOrder(BaseModel):
    smart_order_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    account: str
    symbol: str
    market: str
    side: OrderSide
    quantity: float
    trigger_conditions: list[TriggerCondition]
    status: str = "PENDING"  # PENDING, TRIGGERED, CANCELLED, FAILED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    triggered_at: datetime | None = None
    execution_order_id: str | None = None
