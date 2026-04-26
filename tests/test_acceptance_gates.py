from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from tradingcat.config import AppConfig, FutuConfig, RiskConfig
from tradingcat.domain.models import KillSwitchEvent, PortfolioSnapshot
from tradingcat.main import TradingCatApplication
from tradingcat.repositories.state import AcceptanceGateSnapshotRepository
from tradingcat.services.acceptance_gates import (
    EXCEPTION_RATE_THRESHOLD,
    KILL_SWITCH_LATENCY_SECONDS,
    PORTFOLIO_CASH_TOLERANCE,
    SCHEDULER_DAILY_STALE_HOURS,
    SLIPPAGE_BPS_THRESHOLD,
    TRADE_LEDGER_RECONCILIATION_STALE_HOURS,
    AcceptanceGateEvidenceService,
    compute_acceptance_gates,
    evaluate_scheduler_health,
    evaluate_trade_ledger_reconciliation,
)


_CLEAN_PORTFOLIO_RECON = {
    "broker_cash": 100_000.0,
    "snapshot_cash": 100_000.0,
    "cash_difference": 0.0,
    "broker_position_count": 3,
    "snapshot_position_count": 3,
    "missing_symbols": [],
    "unexpected_symbols": [],
}


def _clean_ledger_recon(now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(UTC)
    return {
        "as_of": now.date().isoformat(),
        "captured_at": now.isoformat(),
        "status": "ok",
        "broker_fill_count": 5,
        "ledger_entry_count": 5,
        "missing_ledger_count": 0,
        "missing_broker_count": 0,
        "amount_drift_count": 0,
        "max_amount_drift_pct": 0.0,
    }


@dataclass
class _StubJob:
    id: str
    enabled: bool = True
    interval_seconds: int | None = None


@dataclass
class _StubRun:
    job_id: str
    executed_at: datetime
    status: str = "success"


def _fresh_scheduler_payload(now: datetime | None = None) -> tuple[list[_StubJob], list[_StubRun]]:
    """Return (jobs, runs) where every daily job has a recent successful run."""
    now = now or datetime.now(UTC)
    jobs = [_StubJob(id="daily_one"), _StubJob(id="daily_two"), _StubJob(id="tick", interval_seconds=60)]
    runs = [
        _StubRun(job_id="daily_one", executed_at=now - timedelta(hours=1)),
        _StubRun(job_id="daily_two", executed_at=now - timedelta(hours=2)),
        _StubRun(job_id="tick", executed_at=now - timedelta(seconds=30)),
    ]
    return jobs, runs


def test_compute_gates_all_green_when_inputs_clean():
    jobs, runs = _fresh_scheduler_payload()
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 100, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=_CLEAN_PORTFOLIO_RECON,
        kill_switch_events=[
            KillSwitchEvent(
                enabled=True,
                detected_at=datetime(2026, 4, 18, 10, 0, 0),
                changed_at=datetime(2026, 4, 18, 10, 0, 30),
            )
        ],
        scheduler_jobs=jobs,
        scheduler_runs=runs,
        trade_ledger_reconciliation=_clean_ledger_recon(),
    )
    assert result["status"] == "pass"
    assert result["gates"]["slippage"]["status"] == "pass"
    assert result["gates"]["exception_rate"]["status"] == "pass"
    assert result["gates"]["reconciliation"]["status"] == "pass"
    assert result["gates"]["portfolio_reconciliation"]["status"] == "pass"
    assert result["gates"]["trade_ledger_reconciliation"]["status"] == "pass"
    assert result["gates"]["kill_switch_latency"]["status"] == "pass"
    assert result["gates"]["scheduler_health"]["status"] == "pass"
    assert result["thresholds"]["slippage_bps"] == SLIPPAGE_BPS_THRESHOLD
    assert result["thresholds"]["exception_rate"] == EXCEPTION_RATE_THRESHOLD
    assert result["thresholds"]["kill_switch_latency_seconds"] == KILL_SWITCH_LATENCY_SECONDS
    assert result["thresholds"]["portfolio_cash_tolerance"] == PORTFOLIO_CASH_TOLERANCE
    assert result["thresholds"]["scheduler_daily_stale_hours"] == SCHEDULER_DAILY_STALE_HOURS
    assert result["thresholds"]["trade_ledger_reconciliation_stale_hours"] == TRADE_LEDGER_RECONCILIATION_STALE_HOURS


def test_compute_gates_flag_slippage_breach():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 2},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=_CLEAN_PORTFOLIO_RECON,
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["slippage"]["status"] == "fail"


def test_compute_gates_flag_exception_rate_breach():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 100, "exception_count": 5},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=_CLEAN_PORTFOLIO_RECON,
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["exception_rate"]["status"] == "fail"
    assert result["gates"]["exception_rate"]["metric"]["observed_ratio"] == 0.05


def test_compute_gates_flag_reconciliation_diff():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 1, "unmatched_broker_orders": ["BR-1"]},
        portfolio_reconciliation=_CLEAN_PORTFOLIO_RECON,
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["reconciliation"]["status"] == "fail"
    assert result["gates"]["reconciliation"]["metric"]["unmatched_broker_orders"] == 1


def test_compute_gates_flag_portfolio_cash_drift():
    drift = dict(_CLEAN_PORTFOLIO_RECON, cash_difference=50.0)
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=drift,
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["portfolio_reconciliation"]["status"] == "fail"
    assert result["gates"]["portfolio_reconciliation"]["metric"]["cash_difference"] == 50.0


def test_compute_gates_flag_portfolio_position_mismatch():
    drift = dict(_CLEAN_PORTFOLIO_RECON, missing_symbols=["AAPL"], unexpected_symbols=["NVDA", "TSLA"])
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=drift,
        kill_switch_events=[],
    )
    assert result["gates"]["portfolio_reconciliation"]["status"] == "fail"
    metric = result["gates"]["portfolio_reconciliation"]["metric"]
    assert metric["missing_symbols"] == 1
    assert metric["unexpected_symbols"] == 2


def test_compute_gates_portfolio_cash_within_tolerance_still_passes():
    tight = dict(_CLEAN_PORTFOLIO_RECON, cash_difference=PORTFOLIO_CASH_TOLERANCE)
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=tight,
        kill_switch_events=[],
    )
    assert result["gates"]["portfolio_reconciliation"]["status"] == "pass"


def test_compute_gates_flag_kill_latency_breach():
    slow = KillSwitchEvent(
        enabled=True,
        detected_at=datetime(2026, 4, 18, 10, 0, 0),
        changed_at=datetime(2026, 4, 18, 10, 5, 0),
    )
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=_CLEAN_PORTFOLIO_RECON,
        kill_switch_events=[slow],
    )
    assert result["status"] == "fail"
    assert result["gates"]["kill_switch_latency"]["status"] == "fail"
    assert result["gates"]["kill_switch_latency"]["metric"]["max_seconds"] == 300.0


def test_scheduler_health_passes_when_all_jobs_recent():
    jobs, runs = _fresh_scheduler_payload()
    gate = evaluate_scheduler_health(jobs, runs)
    assert gate["status"] == "pass"
    assert gate["metric"]["stale_jobs"] == 0
    assert gate["metric"]["enabled_jobs"] == 3


def test_scheduler_health_flags_stale_daily_job():
    now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    jobs = [_StubJob(id="stale_daily"), _StubJob(id="fresh_daily")]
    runs = [
        _StubRun(job_id="stale_daily", executed_at=now - timedelta(hours=48)),
        _StubRun(job_id="fresh_daily", executed_at=now - timedelta(hours=2)),
    ]
    gate = evaluate_scheduler_health(jobs, runs, now=now)
    assert gate["status"] == "fail"
    assert gate["metric"]["stale_jobs"] == 1
    stale_entry = gate["metric"]["stale"][0]
    assert stale_entry["job_id"] == "stale_daily"
    assert stale_entry["job_kind"] == "daily"


def test_scheduler_health_flags_last_failed_run():
    now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    jobs = [_StubJob(id="errored")]
    runs = [
        _StubRun(job_id="errored", executed_at=now - timedelta(hours=1), status="error"),
    ]
    gate = evaluate_scheduler_health(jobs, runs, now=now)
    # No successful run ever — status is pending rather than fail, because we
    # need at least some success on record to confirm the scheduler is up.
    assert gate["status"] == "pending"
    stale_entry = gate["metric"]["stale"][0]
    assert stale_entry["reason"] == "last_run_failed"


def test_scheduler_health_flags_last_failed_after_earlier_success():
    now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    jobs = [_StubJob(id="flaky"), _StubJob(id="healthy")]
    runs = [
        _StubRun(job_id="healthy", executed_at=now - timedelta(hours=1)),
        _StubRun(job_id="flaky", executed_at=now - timedelta(hours=48)),  # old success
        _StubRun(job_id="flaky", executed_at=now - timedelta(hours=1), status="error"),
    ]
    gate = evaluate_scheduler_health(jobs, runs, now=now)
    assert gate["status"] == "fail"
    stale = {entry["job_id"]: entry for entry in gate["metric"]["stale"]}
    assert "flaky" in stale
    assert stale["flaky"]["reason"] == "last_run_failed"


def test_scheduler_health_flags_stale_interval_job():
    now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    jobs = [_StubJob(id="tick", interval_seconds=60), _StubJob(id="daily_ok")]
    runs = [
        _StubRun(job_id="tick", executed_at=now - timedelta(seconds=600)),  # way past 3×60s
        _StubRun(job_id="daily_ok", executed_at=now - timedelta(hours=1)),
    ]
    gate = evaluate_scheduler_health(jobs, runs, now=now)
    assert gate["status"] == "fail"
    stale = {entry["job_id"]: entry for entry in gate["metric"]["stale"]}
    assert stale["tick"]["job_kind"] == "interval"


def test_scheduler_health_ignores_disabled_jobs():
    now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    jobs = [_StubJob(id="muted", enabled=False), _StubJob(id="live")]
    runs = [_StubRun(job_id="live", executed_at=now - timedelta(hours=1))]
    gate = evaluate_scheduler_health(jobs, runs, now=now)
    assert gate["status"] == "pass"
    assert gate["metric"]["enabled_jobs"] == 1


def test_scheduler_health_pending_before_first_tick():
    now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    jobs = [_StubJob(id="fresh_install")]
    gate = evaluate_scheduler_health(jobs, runs=[], now=now)
    assert gate["status"] == "pending"
    assert gate["metric"]["stale_jobs"] == 1


def test_compute_gates_pending_when_no_samples():
    result = compute_acceptance_gates()
    # Reconciliation (execution) with no data = no diffs; portfolio reconciliation
    # is pending because broker is disconnected; slippage/exception/latency all pending.
    assert result["gates"]["slippage"]["status"] == "pending"
    assert result["gates"]["exception_rate"]["status"] == "pending"
    assert result["gates"]["kill_switch_latency"]["status"] == "pending"
    assert result["gates"]["reconciliation"]["status"] == "pass"
    assert result["gates"]["portfolio_reconciliation"]["status"] == "pending"
    assert result["status"] == "pending"


def test_evidence_service_capture_is_idempotent_per_day(tmp_path):
    repo = AcceptanceGateSnapshotRepository(tmp_path)
    service = AcceptanceGateEvidenceService(repo)
    payload = {
        "status": "pass",
        "gates": {"slippage": {"status": "pass"}},
        "thresholds": {"slippage_bps": 20.0},
    }
    target_day = date(2026, 4, 19)
    first = service.capture(payload, as_of=target_day, notes=["first"])
    second = service.capture(payload, as_of=target_day, notes=["second"])
    snapshots = AcceptanceGateEvidenceService(repo).list_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0].notes == ["second"]
    assert first.id == second.id  # Same id preserved across re-captures


def test_evidence_timeline_summarises_pass_streak(tmp_path):
    repo = AcceptanceGateSnapshotRepository(tmp_path)
    service = AcceptanceGateEvidenceService(repo)
    payload_pass = {"status": "pass", "gates": {}, "thresholds": {}}
    payload_fail = {"status": "fail", "gates": {}, "thresholds": {}}
    today = date.today()
    service.capture(payload_fail, as_of=today - timedelta(days=4))
    for offset in range(3, -1, -1):
        service.capture(payload_pass, as_of=today - timedelta(days=offset))
    timeline = service.timeline(window_days=7)
    summary = timeline["summary"]
    assert summary["pass_days"] == 4
    assert summary["fail_days"] == 1
    assert summary["current_pass_streak"] == 4
    assert summary["max_pass_streak"] == 4
    # Days outside the captured window register as missing.
    assert summary["missing_days"] == 2


def test_capture_acceptance_evidence_uses_live_gates(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    snapshot = app.capture_acceptance_evidence(notes=["test"])
    assert "status" in snapshot
    assert snapshot["status"] in {"pass", "fail", "pending"}
    timeline = app.acceptance_evidence_timeline(window_days=14)
    assert timeline["window_days"] == 14
    assert any(point["status"] == snapshot["status"] for point in timeline["points"])


def test_acceptance_evidence_job_handler(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    detail = app.scheduler_runtime.run_acceptance_evidence_job()
    assert detail.startswith("已采集")


def test_gate_readiness_blocks_promotion_when_streak_short(tmp_path):
    repo = AcceptanceGateSnapshotRepository(tmp_path)
    service = AcceptanceGateEvidenceService(repo)
    today = date.today()
    payload_pass = {"status": "pass", "gates": {}, "thresholds": {}}
    for offset in range(2, -1, -1):
        service.capture(payload_pass, as_of=today - timedelta(days=offset))
    readiness = service.gate_readiness("10%")
    assert readiness["eligible"] is False
    assert readiness["current_pass_streak"] == 3
    assert readiness["required_pass_streak"] == AcceptanceGateEvidenceService.STAGE_PASS_STREAK_REQUIREMENTS["10%"]
    assert readiness["blockers"]


def test_gate_readiness_allows_when_streak_meets_requirement(tmp_path):
    repo = AcceptanceGateSnapshotRepository(tmp_path)
    service = AcceptanceGateEvidenceService(repo)
    today = date.today()
    payload_pass = {"status": "pass", "gates": {}, "thresholds": {}}
    required = AcceptanceGateEvidenceService.STAGE_PASS_STREAK_REQUIREMENTS["10%"]
    for offset in range(required - 1, -1, -1):
        service.capture(payload_pass, as_of=today - timedelta(days=offset))
    readiness = service.gate_readiness("10%")
    assert readiness["eligible"] is True
    assert readiness["current_pass_streak"] >= required
    assert readiness["blockers"] == []


def test_gate_readiness_passthrough_for_hold_stage(tmp_path):
    repo = AcceptanceGateSnapshotRepository(tmp_path)
    service = AcceptanceGateEvidenceService(repo)
    readiness = service.gate_readiness("hold")
    assert readiness["eligible"] is True
    assert readiness["blockers"] == []


def test_operations_rollout_is_blocked_when_evidence_missing(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    rollout = app.operations_rollout()
    gate_readiness = rollout["acceptance_gate_readiness"]
    if gate_readiness["required_pass_streak"] is not None:
        # No paper-trading data → must be blocked.
        assert gate_readiness["eligible"] is False
        assert rollout["ready_for_rollout"] is False
        assert any("Stage-C evidence" in str(b) for b in rollout["blockers"])


def test_app_acceptance_gates_records_latency_on_intraday_tick(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
            risk=RiskConfig(no_new_risk_drawdown=0.15),
        )
    )
    breach = PortfolioSnapshot(nav=1_000_000.0, cash=900_000.0, drawdown=0.20, daily_pnl=0.0, weekly_pnl=0.0)
    app.portfolio.current_snapshot = lambda: breach  # type: ignore[method-assign]

    app.run_intraday_risk_tick()
    gates = app.acceptance_gates()

    latency_gate = gates["gates"]["kill_switch_latency"]
    assert latency_gate["metric"]["sampled_events"] >= 1
    assert latency_gate["status"] in {"pass", "fail"}
    # Either way, a latency number should be present.
    assert "max_seconds" in latency_gate["metric"]


# ---------------------------------------------------------------------------
# Trade ledger reconciliation gate
# ---------------------------------------------------------------------------


def test_trade_ledger_gate_pending_when_no_run_recorded():
    gate = evaluate_trade_ledger_reconciliation(None)
    assert gate["status"] == "pending"


def test_trade_ledger_gate_passes_when_run_is_clean_and_fresh():
    gate = evaluate_trade_ledger_reconciliation(_clean_ledger_recon())
    assert gate["status"] == "pass"
    assert gate["metric"]["broker_fill_count"] == 5
    assert gate["metric"]["ledger_entry_count"] == 5


def test_trade_ledger_gate_fails_on_drift_status():
    now = datetime.now(UTC)
    payload = dict(
        _clean_ledger_recon(now),
        status="drift",
        missing_ledger_count=1,
    )
    gate = evaluate_trade_ledger_reconciliation(payload)
    assert gate["status"] == "fail"
    assert gate["metric"]["missing_ledger_count"] == 1


def test_trade_ledger_gate_fails_on_critical_status():
    now = datetime.now(UTC)
    payload = dict(
        _clean_ledger_recon(now),
        status="critical",
        amount_drift_count=1,
        max_amount_drift_pct=0.05,
    )
    gate = evaluate_trade_ledger_reconciliation(payload)
    assert gate["status"] == "fail"
    assert "5.00%" in gate["detail"]


def test_trade_ledger_gate_fails_on_stale_clean_run():
    # A clean run from 2 days ago is as dangerous as a drift today — the audit
    # didn't tick, so we have no coverage for the interim.
    stale_clock = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    stale_captured = stale_clock - timedelta(hours=36)
    payload = {
        "as_of": stale_captured.date().isoformat(),
        "captured_at": stale_captured.isoformat(),
        "status": "ok",
        "broker_fill_count": 0,
        "ledger_entry_count": 0,
        "missing_ledger_count": 0,
        "missing_broker_count": 0,
        "amount_drift_count": 0,
        "max_amount_drift_pct": 0.0,
    }
    gate = evaluate_trade_ledger_reconciliation(payload, now=stale_clock)
    assert gate["status"] == "fail"
    assert "stale" in gate["detail"].lower()


def test_compute_gates_trade_ledger_drift_flips_overall_status():
    jobs, runs = _fresh_scheduler_payload()
    now = datetime.now(UTC)
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 100, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        portfolio_reconciliation=_CLEAN_PORTFOLIO_RECON,
        kill_switch_events=[
            KillSwitchEvent(
                enabled=True,
                detected_at=datetime(2026, 4, 18, 10, 0, 0),
                changed_at=datetime(2026, 4, 18, 10, 0, 30),
            )
        ],
        scheduler_jobs=jobs,
        scheduler_runs=runs,
        trade_ledger_reconciliation=dict(
            _clean_ledger_recon(now), status="drift", missing_ledger_count=2
        ),
    )
    assert result["status"] == "fail"
    assert result["gates"]["trade_ledger_reconciliation"]["status"] == "fail"


def test_application_acceptance_gates_includes_trade_ledger(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )
    # Seed one clean run so the gate is pass, not pending.
    app.run_trade_ledger_reconciliation(as_of=date.today())
    gates = app.acceptance_gates()
    assert "trade_ledger_reconciliation" in gates["gates"]
    assert gates["gates"]["trade_ledger_reconciliation"]["status"] == "pass"
