"""Domain model classes for TradingCat."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

UTC = timezone.utc
from enum import Enum
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:  # pragma: no cover — typing only
    from tradingcat.domain.sentiment import MarketSentimentSnapshot


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


class MarketAwarenessRegime(str, Enum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    CAUTION = "caution"
    RISK_OFF = "risk_off"


class MarketAwarenessConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MarketAwarenessRiskPosture(str, Enum):
    BUILD_RISK = "build_risk"
    HOLD_PACE = "hold_pace"
    REDUCE_RISK = "reduce_risk"
    PAUSE_NEW_ADDS = "pause_new_adds"


class MarketAwarenessSignalStatus(str, Enum):
    SUPPORTIVE = "supportive"
    MIXED = "mixed"
    WARNING = "warning"
    BLOCKED = "blocked"


class MarketAwarenessActionSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MarketAwarenessStrategyStance(str, Enum):
    OFFENSE = "offense"
    BALANCED = "balanced"
    DEFENSIVE = "defensive"
    HEDGED = "hedged"


class MarketAwarenessDataStatus(str, Enum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    FALLBACK = "fallback"


class MarketAwarenessSentimentBand(str, Enum):
    FEAR = "fear"
    CAUTION = "caution"
    NEUTRAL = "neutral"
    CONSTRUCTIVE = "constructive"
    GREED = "greed"


class MarketAwarenessPriceVolumeState(str, Enum):
    PRICE_UP_VOLUME_UP = "price_up_volume_up"
    PRICE_UP_VOLUME_DOWN = "price_up_volume_down"
    PRICE_DOWN_VOLUME_UP = "price_down_volume_up"
    PRICE_DOWN_VOLUME_DOWN = "price_down_volume_down"
    DIVERGENCE = "divergence"
    REPAIR = "repair"


class MarketAwarenessParticipationDecision(str, Enum):
    PARTICIPATE = "participate"
    SELECTIVE = "selective"
    WAIT = "wait"
    AVOID = "avoid"


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
    fill_id: str = ""
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
    source: str = "live"


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
    detected_at: datetime | None = None


class ReconciliationSummary(BaseModel):
    order_updates: int = 0
    fill_updates: int = 0
    duplicate_fills: int = 0
    unmatched_broker_orders: int = 0
    state_counts: dict[str, int] = Field(default_factory=dict)
    applied_fill_order_ids: list[str] = Field(default_factory=list)


class TradeLedgerEntry(BaseModel):
    """Tax/audit-grade trade ledger row.

    Schema established now (Stage B) so the year-end export has all fields
    populated from day one of live trading. Fee columns are filled by the
    TradeLedgerService from market-specific schedules — HK (stamp duty both
    sides, no capital gains), US (SEC fee on sells, 30% dividend withholding
    tracked separately), CN (0.05% seller stamp duty, 0.001% transfer fee).
    """

    order_intent_id: str
    broker_order_id: str = ""
    fill_id: str = ""
    trade_date: date
    trade_datetime: datetime
    symbol: str
    market: Market
    asset_class: AssetClass
    side: OrderSide
    currency: str
    quantity: float
    price: float
    gross_amount: float
    commission: float = 0.0
    stamp_duty: float = 0.0
    transfer_fee: float = 0.0
    exchange_fee: float = 0.0
    regulatory_fee: float = 0.0
    other_fees: float = 0.0
    net_amount: float
    withholding_tax: float = 0.0
    realized_slippage_bps: float | None = None
    strategy_id: str = "unknown"
    fill_source: str = "live"
    fee_schedule_version: str = "v1"
    reporting_notes: list[str] = Field(default_factory=list)


class PortfolioReconciliationSummary(BaseModel):
    broker_cash: float = 0.0
    snapshot_cash: float = 0.0
    cash_difference: float = 0.0
    broker_position_count: int = 0
    snapshot_position_count: int = 0
    missing_symbols: list[str] = Field(default_factory=list)
    unexpected_symbols: list[str] = Field(default_factory=list)


class MarketAwarenessEvidenceRow(BaseModel):
    market: str = "overall"
    signal_key: str
    label: str
    status: MarketAwarenessSignalStatus
    value: float | None = None
    unit: str | None = None
    explanation: str


class MarketAwarenessNewsItem(BaseModel):
    source: str
    title: str
    topic: str = "macro"
    tone: MarketAwarenessSignalStatus = MarketAwarenessSignalStatus.MIXED
    importance: float = 0.0
    published_at: datetime | None = None
    url: str | None = None
    markets: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)


class MarketAwarenessNewsObservation(BaseModel):
    score: float = 0.0
    tone: MarketAwarenessSignalStatus = MarketAwarenessSignalStatus.MIXED
    dominant_topics: list[str] = Field(default_factory=list)
    key_items: list[MarketAwarenessNewsItem] = Field(default_factory=list)
    degraded: bool = False
    blockers: list[str] = Field(default_factory=list)
    explanation: str = ""


class MarketAwarenessAshareIndexView(BaseModel):
    label: str
    symbol: str
    trend_status: MarketAwarenessSignalStatus = MarketAwarenessSignalStatus.MIXED
    price_volume_state: MarketAwarenessPriceVolumeState = MarketAwarenessPriceVolumeState.DIVERGENCE
    score: float = 0.0
    close: float | None = None
    return_1d: float | None = None
    return_5d: float | None = None
    return_20d: float | None = None
    volume_ratio_20d: float | None = None
    above_sma20: bool | None = None
    above_sma50: bool | None = None
    above_sma200: bool | None = None
    explanation: str = ""


class MarketAwarenessAshareIndices(BaseModel):
    score: float = 0.0
    tone: MarketAwarenessSignalStatus = MarketAwarenessSignalStatus.MIXED
    index_views: list[MarketAwarenessAshareIndexView] = Field(default_factory=list)
    degraded: bool = False
    blockers: list[str] = Field(default_factory=list)
    explanation: str = ""


class MarketAwarenessContributor(BaseModel):
    label: str
    score: float = 0.0
    explanation: str = ""


class MarketAwarenessFearGreed(BaseModel):
    score: float = 0.0
    band: MarketAwarenessSentimentBand = MarketAwarenessSentimentBand.NEUTRAL
    explanation: str = ""
    contributors: list[MarketAwarenessContributor] = Field(default_factory=list)


class MarketAwarenessVolumePrice(BaseModel):
    state: MarketAwarenessPriceVolumeState = MarketAwarenessPriceVolumeState.DIVERGENCE
    score: float = 0.0
    explanation: str = ""
    guidance: str = ""
    contributors: list[MarketAwarenessContributor] = Field(default_factory=list)


class MarketAwarenessParticipation(BaseModel):
    decision: MarketAwarenessParticipationDecision = MarketAwarenessParticipationDecision.WAIT
    probability: float = 0.0
    odds: float = 1.0
    confidence: MarketAwarenessConfidence = MarketAwarenessConfidence.LOW
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class MarketAwarenessMarketView(BaseModel):
    market: Market
    benchmark_symbol: str
    reference_symbols: list[str] = Field(default_factory=list)
    regime: MarketAwarenessRegime
    confidence: MarketAwarenessConfidence
    risk_posture: MarketAwarenessRiskPosture
    score: float = 0.0
    breadth_ratio: float | None = None
    momentum_21d: float | None = None
    drawdown_20d: float | None = None
    realized_volatility_20d: float | None = None
    evidence: list[MarketAwarenessEvidenceRow] = Field(default_factory=list)


class MarketAwarenessActionItem(BaseModel):
    severity: MarketAwarenessActionSeverity
    action_key: str
    text: str
    rationale: str
    markets: list[str] = Field(default_factory=list)


class MarketAwarenessStrategyGuidance(BaseModel):
    strategy_id: str
    stance: MarketAwarenessStrategyStance
    summary: str
    rationale: str
    action_key: str | None = None


class MarketAwarenessDataQuality(BaseModel):
    status: MarketAwarenessDataStatus = MarketAwarenessDataStatus.COMPLETE
    complete: bool = True
    degraded: bool = False
    fallback_driven: bool = False
    missing_symbols: list[str] = Field(default_factory=list)
    stale_windows: list[str] = Field(default_factory=list)
    adapter_limitations: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class MarketAwarenessSnapshot(BaseModel):
    as_of: date
    overall_regime: MarketAwarenessRegime
    confidence: MarketAwarenessConfidence
    risk_posture: MarketAwarenessRiskPosture
    overall_score: float = 0.0
    market_views: list[MarketAwarenessMarketView] = Field(default_factory=list)
    evidence: list[MarketAwarenessEvidenceRow] = Field(default_factory=list)
    actions: list[MarketAwarenessActionItem] = Field(default_factory=list)
    strategy_guidance: list[MarketAwarenessStrategyGuidance] = Field(default_factory=list)
    data_quality: MarketAwarenessDataQuality = Field(default_factory=MarketAwarenessDataQuality)
    news_observation: MarketAwarenessNewsObservation = Field(default_factory=MarketAwarenessNewsObservation)
    a_share_indices: MarketAwarenessAshareIndices = Field(default_factory=MarketAwarenessAshareIndices)
    fear_greed: MarketAwarenessFearGreed = Field(default_factory=MarketAwarenessFearGreed)
    volume_price: MarketAwarenessVolumePrice = Field(default_factory=MarketAwarenessVolumePrice)
    participation: MarketAwarenessParticipation = Field(default_factory=MarketAwarenessParticipation)
    # Sentiment snapshot is appended alongside the existing payload. It never
    # feeds the weighted regime score — the weighted formula + existing tests
    # must be unchanged by Round 1. See tradingcat.domain.sentiment.
    market_sentiment: "MarketSentimentSnapshot | None" = None


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


class HistoryAuditRun(BaseModel):
    """Deep long-window history coverage audit, complementing HistorySyncRun.

    One row per audit date, keyed by as_of ISO so weekly reruns overwrite.
    Retains only top findings + summary counts; re-run to get full detail.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    as_of: date
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window_days: int = 90
    instrument_count: int = 0
    complete_instruments: int = 0
    minimum_coverage_ratio: float = 1.0
    missing_symbol_count: int = 0
    top_findings: list[dict[str, object]] = Field(default_factory=list)
    status: Literal["ok", "drift", "critical"] = "ok"
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
    interval_seconds: int | None = None


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


class AcceptanceGateSnapshot(BaseModel):
    """Daily Stage-C wall-clock acceptance evidence row.

    One row per day per evaluation; keyed by ISO date so re-running on the
    same day overwrites instead of duplicating. The ``gates`` payload is
    the structured output from :func:`compute_acceptance_gates` so the
    timeline view can reconstruct per-gate detail without re-running.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    as_of: date
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["pass", "fail", "pending"] = "pending"
    gates: dict[str, object] = Field(default_factory=dict)
    thresholds: dict[str, object] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


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


# Resolve the forward reference from MarketAwarenessSnapshot.market_sentiment.
# Imported here (not at top-of-file) to avoid a circular import since
# tradingcat.domain.sentiment depends on Market defined in this module.
from tradingcat.domain.sentiment import MarketSentimentSnapshot  # noqa: E402

MarketAwarenessSnapshot.model_rebuild()
