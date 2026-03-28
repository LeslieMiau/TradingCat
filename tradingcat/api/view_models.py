from __future__ import annotations

from datetime import date
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


class ResearchScorecardRowView(FlexibleModel):
    strategy_id: str
    verdict: str
    profitability_score: float
    annualized_return: float
    sharpe: float
    max_drawdown: float


class ResearchScorecardResponse(FlexibleModel):
    as_of: date
    portfolio_passed: bool
    accepted_strategy_ids: list[str] = Field(default_factory=list)
    deploy_candidate_count: int = 0
    paper_only_count: int = 0
    rejected_count: int = 0
    rows: list[ResearchScorecardRowView] = Field(default_factory=list)
    correlation_matrix: dict[str, Any] = Field(default_factory=dict)
    reject_summary: list[dict[str, Any]] = Field(default_factory=list)
    verdict_groups: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class OperationsReadinessResponse(FlexibleModel):
    ready: bool
    diagnostics: dict[str, Any]
    preflight: dict[str, Any]
    broker_status: dict[str, Any]
    broker_validation: dict[str, Any]
    alerts: dict[str, Any]
    compliance: dict[str, Any]
    latest_report_dir: str | None = None
