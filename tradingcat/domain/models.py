"""Domain model classes for TradingCat."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

UTC = timezone.utc
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Core Domain Models
# ---------------------------------------------------------------------------


class Instrument(BaseModel):
    symbol: str
    market: Market
    asset_class: AssetClass = AssetClass.STOCK
    currency: str = "USD"
    name: str = ""
    lot_size: float = 1.0
    enabled: bool = True
    tradable: bool = True
    liquidity_bucket: str = "medium"
    avg_daily_dollar_volume_m: float | None = None
    tags: list[str] = Field(default_factory=list)


class OptionContract(BaseModel):
    symbol: str
    underlying: str
    strike: float
    expiry: date
    option_type: str = "call"  # "call" or "put"
    market: Market = Market.US
    currency: str = "USD"


class Bar(BaseModel):
    instrument: Instrument
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class FxRate(BaseModel):
    base_currency: str
    quote_currency: str
    date: date
    rate: float


class CorporateAction(BaseModel):
    instrument: Instrument
    effective_date: date
    action_type: str = ""
    ratio: float = 1.0
    cash_amount: float = 0.0
    notes: str | None = None


class Signal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    strategy_id: str
    generated_at: datetime
    instrument: Instrument
    side: OrderSide
    target_weight: float
    reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class AlgoExecution(BaseModel):
    strategy: str  # TWAP, VWAP
    start_time: datetime | None = None
    end_time: datetime | None = None
    participation_rate: float | None = None
    # Ladder specific
    levels: int | None = None
    price_start: float | None = None
    price_end: float | None = None


class OrderIntent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    signal_id: str | None = None
    instrument: Instrument
    side: OrderSide
    quantity: float
    requires_approval: bool = False
    notes: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    order_type: str = "market"  # "market" or "limit"
    limit_price: float | None = None
    algo: AlgoExecution | None = None


class ExecutionReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order_intent_id: str = ""
    broker_order_id: str = ""
    status: OrderStatus = OrderStatus.SUBMITTED
    filled_quantity: float = 0.0
    average_price: float | None = None
    message: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    market: Market | None = None
    emotional_tag: str | None = None
    slippage: float | None = None


class ManualFill(BaseModel):
    order_intent_id: str
    broker_order_id: str = ""
    external_source: str | None = None
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    filled_quantity: float = 0.0
    average_price: float = 0.0
    filled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    market: Market | None = None
    notes: str | None = None
    emotional_tag: str | None = None
    slippage: float | None = None


class Position(BaseModel):
    instrument: Instrument
    quantity: float
    market_value: float = 0.0
    weight: float = 0.0
    average_cost: float = 0.0
    cost_basis: float = 0.0
    unrealized_pnl: float | None = None
    unrealized_return: float | None = None


class PortfolioSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    nav: float = 0.0
    cash: float = 0.0
    drawdown: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    positions: list[Position] = Field(default_factory=list)
    cash_by_market: dict[str, float] = Field(default_factory=dict)
    base_currency: str = "CNY"


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order_intent: OrderIntent
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decision_reason: str | None = None
    expires_at: datetime | None = None


class KillSwitchEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    enabled: bool
    reason: str | None = None
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReconciliationSummary(BaseModel):
    order_updates: int = 0
    fill_updates: int = 0
    duplicate_fills: int = 0
    unmatched_broker_orders: int = 0
    state_counts: dict[str, int] = Field(default_factory=dict)
    applied_fill_order_ids: list[str] = Field(default_factory=list)


class PortfolioReconciliationSummary(BaseModel):
    broker_cash: float = 0.0
    snapshot_cash: float = 0.0
    cash_difference: float = 0.0
    broker_position_count: int = 0
    snapshot_position_count: int = 0
    missing_symbols: list[str] = Field(default_factory=list)
    unexpected_symbols: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Infrastructure Models
# ---------------------------------------------------------------------------


class AlertEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    severity: str = "info"
    category: str = ""
    message: str = ""
    recovery_action: str = ""
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    category: str
    action: str
    status: str = "ok"
    details: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChecklistItem(BaseModel):
    id: str
    label: str
    status: str = "pending"  # "pending", "done", "blocked"
    notes: str | None = None
    updated_at: datetime | None = None


class ComplianceChecklist(BaseModel):
    checklist_id: str
    title: str
    items: list[ChecklistItem] = Field(default_factory=list)
    updated_at: datetime | None = None


class HistorySyncRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    start: date | None = None
    end: date | None = None
    instrument_count: int = 0
    complete_instruments: int = 0
    minimum_coverage_ratio: float = 0.0
    include_corporate_actions: bool = True
    symbols: list[str] = Field(default_factory=list)
    successful_symbols: list[str] = Field(default_factory=list)
    failed_symbols: list[str] = Field(default_factory=list)
    missing_symbols: list[str] = Field(default_factory=list)
    failed_symbol_count: int = 0
    missing_symbol_count: int = 0
    symbol_stats: list[dict[str, object]] = Field(default_factory=list)
    status: str = "ok"
    notes: list[str] = Field(default_factory=list)


class RolloutPolicy(BaseModel):
    stage: str = "100%"
    allocation_ratio: float = 1.0
    source: str = "default"
    reason: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RolloutPromotionAttempt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    requested_stage: str
    recommended_stage: str
    current_stage: str
    allowed: bool
    reason: str | None = None
    blocker: str | None = None
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecoveryAttempt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trigger: str
    retries: int = 0
    before_healthy: bool = False
    after_healthy: bool = False
    changed: bool = False
    status: str = "unchanged"  # "recovered", "failed", "unchanged"
    detail: str | None = None
    before_backend: str | None = None
    after_backend: str | None = None


# ---------------------------------------------------------------------------
# Scheduler Models
# ---------------------------------------------------------------------------


class SchedulerJob(BaseModel):
    id: str
    name: str
    description: str = ""
    market: Market | None = None
    timezone: str = "UTC"
    local_time: time = time(0, 0)
    enabled: bool = True
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None


class SchedulerRunResult(BaseModel):
    job_id: str
    status: str  # "success", "skipped", "error"
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detail: str | None = None


class MarketSession(BaseModel):
    market: Market
    timezone: str
    local_date: date
    open_time: time
    close_time: time
    is_trading_day: bool
    phase: str  # "open", "pre_open", "closed"


# ---------------------------------------------------------------------------
# Research Models
# ---------------------------------------------------------------------------


class BacktestMetrics(BaseModel):
    gross_return: float = 0.0
    net_return: float = 0.0
    turnover: float = 0.0
    max_drawdown: float = 0.0
    annualized_return: float = 0.0
    volatility: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    sample_months: int = 0


class BacktestLedgerEntry(BaseModel):
    period: str
    starting_nav: float
    pnl: float
    costs: float
    ending_nav: float
    gross_return: float
    net_return: float


class BacktestExperiment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    strategy_id: str
    as_of: date
    signal_count: int = 0
    metrics: BacktestMetrics = Field(default_factory=BacktestMetrics)
    sample_start: date = date(2018, 1, 1)
    window_count: int = 0
    passed_validation: bool = False
    assumptions: dict[str, object] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def experiment_id(self) -> str:
        return self.id


class DashboardScorecardSnapshot(BaseModel):
    as_of: date
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    snapshot_status: str = "ready"
    snapshot_reason: str | None = None
    portfolio_passed: bool = False
    portfolio_metrics: dict[str, object] = Field(default_factory=dict)
    accepted_strategy_ids: list[str] = Field(default_factory=list)
    blocked_strategy_ids: list[str] = Field(default_factory=list)
    blocked_count: int = 0
    deploy_candidate_count: int = 0
    paper_only_count: int = 0
    rejected_count: int = 0
    rows: list[dict[str, object]] = Field(default_factory=list)
    top_candidates: list[dict[str, object]] = Field(default_factory=list)
    correlation_matrix: dict[str, object] = Field(default_factory=dict)
    reject_summary: list[dict[str, object]] = Field(default_factory=list)
    verdict_groups: list[dict[str, object]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Existing classes (kept exactly as-is)
# ---------------------------------------------------------------------------


class OperationsJournalEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ready: bool
    diagnostics_category: str
    diagnostics_severity: str
    alert_count: int
    checklist_pending: int
    checklist_blocked: int
    latest_report_dir: str | None = None
    evidence_tags: list[str] = Field(default_factory=list)
    notes: dict[str, object] = Field(default_factory=dict)


class DailyTradingPlanNote(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    as_of: date
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["planned", "no_trade", "blocked"] = "planned"
    account: Literal["total", "CN", "HK", "US"] = "total"
    headline: str
    reasons: list[str] = Field(default_factory=list)
    counts: dict[str, int | float] = Field(default_factory=dict)
    metrics: dict[str, object] = Field(default_factory=dict)
    items: list[dict[str, object]] = Field(default_factory=list)


class DailyTradingSummaryNote(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    as_of: date
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    account: Literal["total", "CN", "HK", "US"] = "total"
    headline: str
    highlights: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)


class StrategySelectionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    as_of: date
    strategy_id: str
    recommended_action: Literal["keep", "paper_only", "drop"]
    selected_for_next_phase: bool = False
    decision: Literal["active", "paper_only", "rejected"] = "rejected"
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, object] = Field(default_factory=dict)
    capacity_tier: str = "unknown"
    max_selected_correlation: float = 0.0


class StrategyAllocationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    as_of: date
    strategy_id: str
    decision: Literal["active", "paper_only", "rejected"] = "rejected"
    target_weight: float = 0.0
    shadow_weight: float = 0.0
    score: float = 0.0
    capacity_tier: str = "unknown"
    market_distribution: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
