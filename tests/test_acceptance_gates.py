from datetime import date, datetime, timedelta

from tradingcat.config import AppConfig, FutuConfig, RiskConfig
from tradingcat.domain.models import KillSwitchEvent, PortfolioSnapshot
from tradingcat.main import TradingCatApplication
from tradingcat.repositories.state import AcceptanceGateSnapshotRepository
from tradingcat.services.acceptance_gates import (
    EXCEPTION_RATE_THRESHOLD,
    KILL_SWITCH_LATENCY_SECONDS,
    SLIPPAGE_BPS_THRESHOLD,
    AcceptanceGateEvidenceService,
    compute_acceptance_gates,
)


def test_compute_gates_all_green_when_inputs_clean():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 100, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        kill_switch_events=[
            KillSwitchEvent(
                enabled=True,
                detected_at=datetime(2026, 4, 18, 10, 0, 0),
                changed_at=datetime(2026, 4, 18, 10, 0, 30),
            )
        ],
    )
    assert result["status"] == "pass"
    assert result["gates"]["slippage"]["status"] == "pass"
    assert result["gates"]["exception_rate"]["status"] == "pass"
    assert result["gates"]["reconciliation"]["status"] == "pass"
    assert result["gates"]["kill_switch_latency"]["status"] == "pass"
    assert result["thresholds"]["slippage_bps"] == SLIPPAGE_BPS_THRESHOLD
    assert result["thresholds"]["exception_rate"] == EXCEPTION_RATE_THRESHOLD
    assert result["thresholds"]["kill_switch_latency_seconds"] == KILL_SWITCH_LATENCY_SECONDS


def test_compute_gates_flag_slippage_breach():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 2},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["slippage"]["status"] == "fail"


def test_compute_gates_flag_exception_rate_breach():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 100, "exception_count": 5},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
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
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["reconciliation"]["status"] == "fail"
    assert result["gates"]["reconciliation"]["metric"]["unmatched_broker_orders"] == 1


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
        kill_switch_events=[slow],
    )
    assert result["status"] == "fail"
    assert result["gates"]["kill_switch_latency"]["status"] == "fail"
    assert result["gates"]["kill_switch_latency"]["metric"]["max_seconds"] == 300.0


def test_compute_gates_pending_when_no_samples():
    result = compute_acceptance_gates()
    # Reconciliation with no data = no diffs; the other three are pending.
    assert result["gates"]["slippage"]["status"] == "pending"
    assert result["gates"]["exception_rate"]["status"] == "pending"
    assert result["gates"]["kill_switch_latency"]["status"] == "pending"
    assert result["gates"]["reconciliation"]["status"] == "pass"
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
    assert detail.startswith("Captured acceptance gates")


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
