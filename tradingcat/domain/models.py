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
