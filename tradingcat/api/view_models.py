from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PositionView(FlexibleModel):
    symbol: str
    market: str
    asset_class: str
    quantity: float
    average_cost: float
    market_value: float
    weight: float
    unrealized_pnl: float | None = None
    unrealized_return: float | None = None
    name: str | None = None


class PlanItemView(FlexibleModel):
    intent_id: str | None = None
    strategy_id: str
    symbol: str
    market: str
    side: str
    quantity: float
    target_weight: float | None = None
    reference_price: float | None = None
    requires_approval: bool
    reason: str | None = None


class AccountSummaryView(FlexibleModel):
    account: str
    label: str
    nav: float
    cash: float
    cash_weight: float | None = None
    cash_ratio: float | None = None
    total_return: float | None = None
    drawdown: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    position_count: int = 0
    position_value: float = 0.0
    positions: list[PositionView] = Field(default_factory=list)
    nav_curve: list[dict[str, object]] = Field(default_factory=list)
    allocation_mix: dict[str, float] = Field(default_factory=dict)
    plan_items: list[PlanItemView] = Field(default_factory=list)


class DashboardSummaryResponse(FlexibleModel):
    as_of: date
    overview: dict[str, Any]
    assets: dict[str, Any]
    accounts: dict[str, AccountSummaryView]
    strategies: dict[str, Any]
    candidates: dict[str, Any]
    trading_plan: dict[str, Any]
    journal: dict[str, Any]
    summaries: dict[str, Any]
    details: dict[str, Any]


class HistoryCoverageReportView(FlexibleModel):
    symbol: str
    market: str | None = None
    coverage_ratio: float = 0.0
    missing_count: int = 0
    missing_preview: list[str] = Field(default_factory=list)


class HistoryCoverageResponse(FlexibleModel):
    start: date | None = None
    end: date | None = None
    minimum_coverage_ratio: float | None = None
    minimum_required_ratio: float | None = None
    missing_symbols: list[str] = Field(default_factory=list)
    missing_windows: list[dict[str, Any]] = Field(default_factory=list)
    blocked: bool | None = None
    blocker_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    reports: list[HistoryCoverageReportView] = Field(default_factory=list)


class PreflightCheckView(FlexibleModel):
    name: str = ""
    ok: bool = False
    detail: str = ""


class DataQualityResponse(FlexibleModel):
    ready: bool
    scope: str
    target_symbols: list[str] = Field(default_factory=list)
    incomplete_count: int = 0
    minimum_coverage_ratio: float | None = None
    minimum_required_ratio: float | None = None
    missing_symbols: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    reports: list[HistoryCoverageReportView] = Field(default_factory=list)


class CorporateActionItemView(FlexibleModel):
    effective_date: date
    action_type: str = ""
    ratio: float = 1.0
    cash_amount: float = 0.0
    notes: str | None = None
    instrument: dict[str, Any] | None = None


class CorporateActionsResponse(FlexibleModel):
    symbol: str
    start: date
    end: date
    ready: bool
    status: str
    market: str | None = None
    action_count: int = 0
    missing_symbols: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    actions: list[CorporateActionItemView] = Field(default_factory=list)


class FxRateItemView(FlexibleModel):
    base_currency: str
    quote_currency: str
    date: date
    rate: float


class FxRatesResponse(FlexibleModel):
    base_currency: str
    quote_currency: str
    start: date
    end: date
    ready: bool
    status: str
    rate_count: int = 0
    missing_quote_currencies: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    rates: list[FxRateItemView] = Field(default_factory=list)


class ResearchSignalInsightView(FlexibleModel):
    symbol: str
    signal_source: str | None = None
    indicator_snapshot: dict[str, Any] = Field(default_factory=dict)


class ResearchStrategyReportView(FlexibleModel):
    strategy_id: str
    validation_status: str
    data_source: str | None = None
    data_ready: bool | None = None
    promotion_blocked: bool | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    minimum_coverage_ratio: float | None = None
    signal_insights: list[ResearchSignalInsightView] = Field(default_factory=list)


class ResearchReportResponse(FlexibleModel):
    as_of: date
    blocked_count: int = 0
    blocked_strategy_ids: list[str] = Field(default_factory=list)
    hard_blocked: bool = False
    report_status: str
    minimum_history_coverage_ratio: float | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    strategy_reports: list[ResearchStrategyReportView] = Field(default_factory=list)


class StrategyDetailSignalView(FlexibleModel):
    symbol: str
    market: str
    asset_class: str
    side: str
    target_weight: float
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    signal_source: str | None = None
    indicator_snapshot: dict[str, Any] = Field(default_factory=dict)


class StrategyDetailResponse(FlexibleModel):
    as_of: date
    strategy_id: str
    signal_count: int = 0
    data_source: str | None = None
    data_ready: bool | None = None
    promotion_blocked: bool | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    minimum_coverage_ratio: float | None = None
    history_coverage_threshold: float | None = None
    missing_coverage_symbols: list[str] = Field(default_factory=list)
    history_coverage_blockers: list[str] = Field(default_factory=list)
    fx_ready: bool | None = None
    missing_fx_pairs: list[str] = Field(default_factory=list)
    fx_blockers: list[str] = Field(default_factory=list)
    fx_coverage: dict[str, Any] = Field(default_factory=dict)
    corporate_actions_ready: bool | None = None
    missing_corporate_action_symbols: list[str] = Field(default_factory=list)
    corporate_action_blockers: list[str] = Field(default_factory=list)
    corporate_action_coverage: dict[str, Any] = Field(default_factory=dict)
    signals: list[StrategyDetailSignalView] = Field(default_factory=list)
    indicator_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    nav_curve: list[dict[str, Any]] = Field(default_factory=list)
    benchmark: dict[str, Any] = Field(default_factory=dict)
    yearly_performance: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: dict[str, Any] = Field(default_factory=dict)


class ResearchReadinessStrategyView(FlexibleModel):
    strategy_id: str
    validation_status: str
    data_source: str | None = None
    data_ready: bool | None = None
    promotion_blocked: bool | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


class ResearchReadinessResponse(FlexibleModel):
    as_of: date
    ready: bool
    report_status: str
    blocked_count: int = 0
    blocked_strategy_ids: list[str] = Field(default_factory=list)
    ready_strategy_ids: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    minimum_history_coverage_ratio: float | None = None
    strategies: list[ResearchReadinessStrategyView] = Field(default_factory=list)


def _default_research_readiness_response() -> "ResearchReadinessResponse":
    return ResearchReadinessResponse(
        as_of=date.today(),
        ready=False,
        report_status="unknown",
    )


class StartupPreflightResponse(FlexibleModel):
    healthy: bool
    checks: list[PreflightCheckView] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    research_ready: bool
    research_blockers: list[str] = Field(default_factory=list)
    research_readiness: ResearchReadinessResponse
    system_ready: bool


def _default_startup_preflight_response() -> "StartupPreflightResponse":
    return StartupPreflightResponse(
        healthy=False,
        research_ready=False,
        research_readiness=_default_research_readiness_response(),
        system_ready=False,
    )


class ResearchScorecardRowView(FlexibleModel):
    strategy_id: str
    action: str | None = None
    verdict: str
    profitability_score: float
    annualized_return: float
    sharpe: float
    max_drawdown: float
    data_source: str | None = None
    data_ready: bool | None = None
    promotion_blocked: bool | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


class ResearchScorecardResponse(FlexibleModel):
    as_of: date
    portfolio_passed: bool
    accepted_strategy_ids: list[str] = Field(default_factory=list)
    blocked_strategy_ids: list[str] = Field(default_factory=list)
    blocked_count: int = 0
    deploy_candidate_count: int = 0
    paper_only_count: int = 0
    rejected_count: int = 0
    rows: list[ResearchScorecardRowView] = Field(default_factory=list)
    correlation_matrix: dict[str, Any] = Field(default_factory=dict)
    reject_summary: list[dict[str, Any]] = Field(default_factory=list)
    verdict_groups: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class DiagnosticsSummaryView(FlexibleModel):
    ready: bool = False
    category: str = "unknown"
    severity: str = "info"
    findings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class AlertEventView(FlexibleModel):
    id: str | None = None
    severity: str = "info"
    category: str = ""
    message: str = ""
    recovery_action: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AlertsSummaryView(FlexibleModel):
    count: int = 0
    latest: AlertEventView | None = None
    active: list[AlertEventView] = Field(default_factory=list)


class ComplianceCountsView(FlexibleModel):
    pending: int = 0
    done: int = 0
    blocked: int = 0


class ComplianceChecklistSummaryView(FlexibleModel):
    checklist_id: str | None = None
    title: str | None = None
    counts: ComplianceCountsView = Field(default_factory=ComplianceCountsView)


class ComplianceSummaryView(FlexibleModel):
    checklists: list[ComplianceChecklistSummaryView] = Field(default_factory=list)
    pending_count: int = 0
    blocked_count: int = 0


class OperationsReadinessResponse(FlexibleModel):
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    diagnostics: DiagnosticsSummaryView = Field(default_factory=DiagnosticsSummaryView)
    preflight: StartupPreflightResponse = Field(default_factory=_default_startup_preflight_response)
    broker_status: dict[str, Any] = Field(default_factory=dict)
    broker_validation: dict[str, Any] = Field(default_factory=dict)
    data_quality: DataQualityResponse = Field(default_factory=lambda: DataQualityResponse(ready=True, scope="unknown"))
    research_readiness: ResearchReadinessResponse = Field(default_factory=_default_research_readiness_response)
    alerts: AlertsSummaryView = Field(default_factory=AlertsSummaryView)
    compliance: ComplianceSummaryView = Field(default_factory=ComplianceSummaryView)
    execution: dict[str, Any] = Field(default_factory=dict)
    latest_report_dir: str | None = None
