from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TradingCatModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        validate_assignment=True,
    )


class AssetClass(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    OPTION = "option"
    CRYPTO = "crypto"
    BOND = "bond"
    CASH = "cash"


class Market(str, Enum):
    US = "US"
    HK = "HK"
    CN = "CN"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PENDING_APPROVAL = "pending_approval"
    EXPIRED = "expired"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class Instrument(TradingCatModel):
    symbol: str
    market: Market
    asset_class: AssetClass
    currency: str
    name: str | None = None
    lot_size: float = 1.0


class OptionContract(Instrument):
    asset_class: AssetClass = AssetClass.OPTION
    underlying: str
    strike: float
    expiry: date
    option_type: Literal["call", "put"]


class Bar(TradingCatModel):
    instrument: Instrument
    timestamp: datetime = Field(validation_alias=AliasChoices("timestamp", "time", "as_of"))
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class FxRate(TradingCatModel):
    base_currency: str
    quote_currency: str
    date: date
    rate: float


class CorporateAction(TradingCatModel):
    instrument: Instrument
    effective_date: date = Field(validation_alias=AliasChoices("effective_date", "date"))
    action_type: str
    cash_amount: float = 0.0
    ratio: float = 1.0
    currency: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class Signal(TradingCatModel):
    id: str | None = None
    strategy_id: str | None = None
    generated_at: datetime = Field(default_factory=_utcnow, validation_alias=AliasChoices("generated_at", "as_of"))
    instrument: Instrument
    side: OrderSide
    target_weight: float
    reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _populate_id(self) -> "Signal":
        if not self.id:
            strategy_id = self.strategy_id or "signal"
            object.__setattr__(self, "id", f"{strategy_id}:{self.instrument.symbol}:{self.generated_at.isoformat()}")
        return self


class OrderIntent(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    signal_id: str
    instrument: Instrument
    side: OrderSide
    quantity: float
    requires_approval: bool = False
    notes: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None


class ExecutionReport(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order_intent_id: str
    broker_order_id: str
    status: OrderStatus
    filled_quantity: float = 0.0
    average_price: float | None = Field(
        default=None,
        validation_alias=AliasChoices("average_price", "fill_price"),
    )
    message: str | None = None
    timestamp: datetime = Field(default_factory=_utcnow)
    market: Market | None = None


class Position(TradingCatModel):
    instrument: Instrument
    quantity: float
    market_value: float = 0.0
    weight: float = 0.0
    average_cost: float = 0.0
    current_price: float | None = None
    cost_basis: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_return: float | None = None


class PortfolioSnapshot(TradingCatModel):
    timestamp: datetime = Field(
        default_factory=_utcnow,
        validation_alias=AliasChoices("timestamp", "recorded_at"),
    )
    nav: float
    cash: float
    positions: list[Position] = Field(default_factory=list)
    drawdown: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    cash_by_market: dict[str, float] = Field(default_factory=dict)
    base_currency: str = "CNY"


class ManualFill(TradingCatModel):
    order_intent_id: str
    broker_order_id: str
    filled_quantity: float = Field(validation_alias=AliasChoices("filled_quantity", "quantity"))
    average_price: float = Field(validation_alias=AliasChoices("average_price", "fill_price"))
    filled_at: datetime = Field(default_factory=_utcnow)
    market: Market | None = None
    side: OrderSide | None = None
    symbol: str | None = None
    notes: str | None = None


class ApprovalRequest(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order_intent: OrderIntent
    order_intent_id: str | None = None
    instrument: Instrument | None = None
    side: OrderSide | None = None
    quantity: float | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=_utcnow)
    decided_at: datetime | None = None
    decision_reason: str | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _populate_from_intent(self) -> "ApprovalRequest":
        object.__setattr__(self, "order_intent_id", self.order_intent.id)
        object.__setattr__(self, "instrument", self.order_intent.instrument)
        object.__setattr__(self, "side", self.order_intent.side)
        object.__setattr__(self, "quantity", self.order_intent.quantity)
        if self.expires_at is None:
            object.__setattr__(self, "expires_at", self.created_at + timedelta(hours=12))
        return self


class KillSwitchEvent(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    enabled: bool
    reason: str | None = None
    changed_at: datetime = Field(default_factory=_utcnow)


class AuditLogEntry(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(
        default_factory=_utcnow,
        validation_alias=AliasChoices("created_at", "recorded_at"),
    )
    category: str
    action: str
    status: str = "ok"
    details: dict[str, object] = Field(default_factory=dict)


class AlertEvent(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=_utcnow)
    severity: str = "info"
    category: str
    message: str
    recovery_action: str = ""
    details: dict[str, object] = Field(default_factory=dict)
    resolved: bool = False


class ChecklistItem(TradingCatModel):
    id: str
    label: str
    status: Literal["pending", "done", "blocked"] = "pending"
    notes: str | None = None
    updated_at: datetime = Field(default_factory=_utcnow)


class ComplianceChecklist(TradingCatModel):
    checklist_id: str
    title: str
    items: list[ChecklistItem] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_utcnow)


class OperationsJournalEntry(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    recorded_at: datetime = Field(default_factory=_utcnow)
    ready: bool
    diagnostics_category: str
    diagnostics_severity: str
    alert_count: int
    checklist_pending: int
    checklist_blocked: int
    latest_report_dir: str | None = None
    notes: dict[str, object] = Field(default_factory=dict)


class DailyTradingPlanNote(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    as_of: date
    generated_at: datetime = Field(default_factory=_utcnow)
    status: Literal["planned", "no_trade", "blocked"] = "planned"
    account: Literal["total", "CN", "HK", "US"] = "total"
    headline: str
    reasons: list[str] = Field(default_factory=list)
    counts: dict[str, int | float] = Field(default_factory=dict)
    metrics: dict[str, object] = Field(default_factory=dict)
    items: list[dict[str, object]] = Field(default_factory=list)


class DailyTradingSummaryNote(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    as_of: date
    generated_at: datetime = Field(default_factory=_utcnow)
    account: Literal["total", "CN", "HK", "US"] = "total"
    headline: str
    highlights: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)


class HistorySyncRun(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    start: date
    end: date
    instrument_count: int = 0
    complete_instruments: int = 0
    minimum_coverage_ratio: float = 0.0
    include_corporate_actions: bool = True
    symbols: list[str] = Field(default_factory=list)
    missing_symbols: list[str] = Field(default_factory=list)
    status: str = "ok"
    notes: list[str] = Field(default_factory=list)


class RecoveryAttempt(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    attempted_at: datetime = Field(
        default_factory=_utcnow,
        validation_alias=AliasChoices("attempted_at", "triggered_at"),
    )
    trigger: str
    retries: int = 0
    before_healthy: bool = False
    after_healthy: bool = False
    changed: bool = False
    status: str = "unchanged"
    detail: str | None = None
    before_backend: str | None = None
    after_backend: str | None = None


class MarketSession(TradingCatModel):
    market: Market
    timezone: str
    local_date: date
    open_time: time
    close_time: time
    is_trading_day: bool
    phase: str


class SchedulerJob(TradingCatModel):
    id: str
    name: str
    description: str
    timezone: str
    local_time: time
    market: Market | None = None
    enabled: bool = True
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None


class SchedulerRunResult(TradingCatModel):
    job_id: str
    status: str
    executed_at: datetime = Field(
        default_factory=_utcnow,
        validation_alias=AliasChoices("executed_at", "ran_at"),
    )
    detail: str | None = Field(default=None, validation_alias=AliasChoices("detail", "message"))


class ReconciliationSummary(TradingCatModel):
    order_updates: int = 0
    fill_updates: int = 0
    duplicate_fills: int = 0
    unmatched_broker_orders: int = 0
    state_counts: dict[str, int] = Field(default_factory=dict)
    applied_fill_order_ids: list[str] = Field(default_factory=list)


class PortfolioReconciliationSummary(TradingCatModel):
    broker_cash: float = 0.0
    snapshot_cash: float = 0.0
    cash_difference: float = 0.0
    broker_position_count: int = 0
    snapshot_position_count: int = 0
    missing_symbols: list[str] = Field(default_factory=list)
    unexpected_symbols: list[str] = Field(default_factory=list)


class RolloutPolicy(TradingCatModel):
    stage: str = "100%"
    allocation_ratio: float = 1.0
    source: Literal["default", "manual", "recommendation"] = "default"
    reason: str | None = None
    updated_at: datetime = Field(default_factory=_utcnow)


class RolloutPromotionAttempt(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    attempted_at: datetime = Field(default_factory=_utcnow)
    requested_stage: str
    recommended_stage: str
    current_stage: str
    allowed: bool
    reason: str | None = None
    blocker: str | None = None


class BacktestMetrics(TradingCatModel):
    gross_return: float = 0.0
    net_return: float = 0.0
    turnover: float = 0.0
    max_drawdown: float = 0.0
    annualized_return: float = 0.0
    volatility: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    sample_months: int = 0


class BacktestLedgerEntry(TradingCatModel):
    period: str
    starting_nav: float
    pnl: float
    costs: float
    ending_nav: float
    gross_return: float
    net_return: float


class BacktestExperiment(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    strategy_id: str
    started_at: datetime = Field(default_factory=_utcnow)
    as_of: date
    signal_count: int = 0
    metrics: BacktestMetrics = Field(default_factory=BacktestMetrics)
    sample_start: date = date(2018, 1, 1)
    window_count: int = 0
    passed_validation: bool = False
    assumptions: dict[str, object] = Field(default_factory=dict)
    ledger: list[BacktestLedgerEntry] = Field(default_factory=list)


class StrategySelectionRecord(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    reviewed_at: datetime = Field(default_factory=_utcnow)
    as_of: date
    strategy_id: str
    recommended_action: Literal["keep", "paper_only", "drop"]
    selected_for_next_phase: bool = False
    decision: Literal["active", "paper_only", "rejected"] = "rejected"
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)
    capacity_tier: str = "unknown"
    max_selected_correlation: float = 0.0


class StrategyAllocationRecord(TradingCatModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    reviewed_at: datetime = Field(default_factory=_utcnow)
    as_of: date
    strategy_id: str
    decision: Literal["active", "paper_only", "rejected"] = "rejected"
    target_weight: float = 0.0
    shadow_weight: float = 0.0
    score: float = 0.0
    capacity_tier: str = "unknown"
    market_distribution: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
