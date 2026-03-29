import subprocess
from pathlib import Path

from datetime import UTC, datetime

from tradingcat.domain.models import AlertEvent, AuditLogEntry, OperationsJournalEntry, RecoveryAttempt
from tradingcat.services.reporting import (
    build_incident_replay,
    build_operations_period_report,
    build_postmortem_report,
    latest_report_dir,
    load_report_summary,
    resolve_report_dir,
    summarize_report_for_dashboard,
)


def test_reports_helper_creates_timestamped_dir(tmp_path):
    script = Path("/Users/miau/Documents/TradingCat/scripts/reports.sh")
    command = f"source {script} && ensure_report_dir {tmp_path}"
    result = subprocess.run(["bash", "-lc", command], capture_output=True, text=True, check=True)

    created = Path(result.stdout.strip())
    assert created.exists()
    assert created.parent == tmp_path


def test_reports_helper_finds_latest_dir(tmp_path):
    script = Path("/Users/miau/Documents/TradingCat/scripts/reports.sh")
    first = tmp_path / "20260307-100000"
    second = tmp_path / "20260307-110000"
    first.mkdir()
    second.mkdir()
    command = f"source {script} && latest_report_dir {tmp_path}"
    result = subprocess.run(["bash", "-lc", command], capture_output=True, text=True, check=True)

    assert Path(result.stdout.strip()) == second


def test_reports_helper_resolves_report_dir(tmp_path):
    script = Path("/Users/miau/Documents/TradingCat/scripts/reports.sh")
    target = tmp_path / "20260307-120000"
    target.mkdir()
    command = f"source {script} && resolve_report_dir 20260307-120000 {tmp_path}"
    result = subprocess.run(["bash", "-lc", command], capture_output=True, text=True, check=True)

    assert Path(result.stdout.strip()) == target


def test_reports_cleanup_keeps_latest(tmp_path):
    script = Path("/Users/miau/Documents/TradingCat/scripts/cleanup_reports.sh")
    reports_root = tmp_path / "data" / "reports"
    (reports_root / "20260307-100000").mkdir(parents=True)
    (reports_root / "20260307-110000").mkdir(parents=True)
    (reports_root / "20260307-120000").mkdir(parents=True)
    env = {"TRADINGCAT_ROOT_DIR": str(tmp_path)}
    result = subprocess.run(["bash", str(script), "2"], capture_output=True, text=True, check=True, env=env)

    assert "Removed 1 report directories" in result.stdout
    assert not (reports_root / "20260307-100000").exists()
    assert (reports_root / "20260307-110000").exists()
    assert (reports_root / "20260307-120000").exists()


def test_reporting_service_loads_latest_summary(tmp_path):
    report_dir = tmp_path / "reports" / "20260308-100000"
    report_dir.mkdir(parents=True)
    (report_dir / "01_diagnostics_summary.json").write_text(
        '{"summary":{"category":"ready_for_validation","severity":"info","ready":true},"execution_run":{"ignored":true}}',
        encoding="utf-8",
    )
    (report_dir / "10_execution_run.json").write_text(
        '{"submitted_orders":[{"broker_order_id":"8445001","status":"submitted"}],"failed_orders":[],"approval_count":1}',
        encoding="utf-8",
    )

    assert latest_report_dir(tmp_path) == report_dir
    assert resolve_report_dir(tmp_path, "20260308-100000") == report_dir

    payload = load_report_summary(report_dir)

    assert payload["summary"]["category"] == "ready_for_validation"
    assert payload["execution_run"]["approval_count"] == 1


def test_reporting_service_builds_dashboard_summary():
    payload = {
        "report_dir": "data/reports/20260308-100000",
        "summary": {"category": "ready_for_validation", "severity": "info", "ready": True, "findings": ["ok"]},
        "operations_readiness": {"ready": True},
        "ops_execution_metrics": {
            "exception_rate": 0.0,
            "risk_hit_rate": 0.1,
            "top_execution_drags": [{"symbol": "SPY", "direction": "buy", "deviation_metric": "slippage_bps", "deviation_value": 25.0}],
            "top_anomaly_sources": [{"source": "alert:trade_channel_failed", "count": 2}],
        },
        "ops_rollout": {"ready_for_rollout": True, "current_recommendation": "10%", "next_stage": "30%", "blockers": []},
        "ops_go_live": {"promotion_allowed": False},
        "ops_live_acceptance": {"ready_for_live": False, "incident_count": 2, "blockers": ["gate"]},
        "ops_rollout_checklist": {"stage": "10%", "ready": False, "blockers": ["gate"]},
        "ops_rollout_milestones": {"next_pending_stage": "30%"},
        "rollout_policy": {"stage": "30%", "allocation_ratio": 0.3, "policy_matches_recommendation": False},
        "data_quality": {"ready": True, "incomplete_count": 0},
        "history_sync": {"healthy": True, "stale": False},
        "selection_summary": {"active": ["strategy_a_etf_rotation"], "paper_only": ["strategy_c_option_overlay"]},
        "allocation_summary": {"active": [{"strategy_id": "strategy_a_etf_rotation", "target_weight": 1.0}], "total_target_weight": 1.0},
        "alerts_summary": {"count": 0},
        "compliance_summary": {"checklists": [{"checklist_id": "cn_programmatic_trading"}]},
        "recovery_summary": {"count": 1},
        "broker_order_check": {
            "instrument": {"symbol": "0700"},
            "submission": {"status": "submitted", "broker_order_id": "8445001"},
            "cancellation": {"status": "cancelled"},
        },
        "execution_gate": {"ready": True, "should_block": False, "policy_stage": "30%", "recommended_stage": "10%", "reasons": []},
        "cancel_open_orders": {"cancelled_count": 2, "failed_count": 1},
        "execution_run": {"submitted_orders": [{}, {}], "failed_orders": [], "approval_count": 1},
        "execution_quality": {"filled_samples": 1, "within_limits": True, "equity_breaches": 0, "option_breaches": 0},
        "execution_authorization": {"order_count": 2, "unauthorized_count": 0, "all_authorized": True},
        "manual_reconcile": {"status": "ok", "approval": {"approval": {"status": "approved"}}, "reconciliation": {"status": "filled"}},
    }

    summary = summarize_report_for_dashboard(payload)

    assert summary["ready"] is True
    assert summary["cards"]["operations"]["ready"] is True
    assert summary["cards"]["operations"]["alert_count"] == 0
    assert summary["cards"]["operations"]["recovery_attempts"] == 1
    assert summary["cards"]["operations"]["data_ready"] is True
    assert summary["cards"]["operations"]["data_incomplete_count"] == 0
    assert summary["cards"]["operations"]["history_sync_healthy"] is True
    assert summary["cards"]["operations"]["history_sync_stale"] is False
    assert summary["cards"]["operations"]["active_strategy_count"] == 1
    assert summary["cards"]["operations"]["paper_only_strategy_count"] == 1
    assert summary["cards"]["operations"]["allocated_strategy_count"] == 1
    assert summary["cards"]["operations"]["allocated_target_weight"] == 1.0
    assert summary["cards"]["operations"]["exception_rate"] == 0.0
    assert summary["cards"]["operations"]["top_execution_drag"]["symbol"] == "SPY"
    assert summary["cards"]["operations"]["top_anomaly_source"]["source"] == "alert:trade_channel_failed"
    assert summary["cards"]["operations"]["gate_ready"] is True
    assert summary["cards"]["operations"]["gate_blocked"] is False
    assert summary["cards"]["operations"]["live_ready"] is False
    assert summary["cards"]["rollout"]["current_recommendation"] == "10%"
    assert summary["cards"]["rollout"]["promotion_allowed"] is False
    assert summary["cards"]["rollout"]["ready_for_live"] is False
    assert summary["cards"]["rollout"]["checklist_ready"] is False
    assert summary["cards"]["rollout"]["next_pending_stage"] == "30%"
    assert summary["cards"]["rollout"]["active_stage"] == "30%"
    assert summary["cards"]["rollout"]["allocation_ratio"] == 0.3
    assert summary["cards"]["broker_order_check"]["symbol"] == "0700"
    assert summary["cards"]["execution_run"]["submitted_count"] == 2
    assert summary["cards"]["execution_gate"]["ready"] is True
    assert summary["cards"]["execution_gate"]["should_block"] is False
    assert summary["cards"]["execution_quality"]["within_limits"] is True
    assert summary["cards"]["execution_authorization"]["all_authorized"] is True
    assert summary["cards"]["live_acceptance"]["ready_for_live"] is False
    assert summary["cards"]["live_acceptance"]["incident_count"] == 2
    assert summary["cards"]["rollout_checklist"]["stage"] == "10%"
    assert summary["cards"]["rollout_checklist"]["ready"] is False
    assert summary["cards"]["manual_reconcile"]["reconcile_status"] == "filled"


def test_reporting_service_loads_operations_files(tmp_path):
    report_dir = tmp_path / "reports" / "20260308-150000"
    report_dir.mkdir(parents=True)
    (report_dir / "01_diagnostics_summary.json").write_text(
        '{"summary":{"category":"ready_for_validation","severity":"info","ready":true}}',
        encoding="utf-8",
    )
    (report_dir / "08_alerts_summary.json").write_text('{"count":0,"latest":null,"active":[]}', encoding="utf-8")
    (report_dir / "09_compliance_summary.json").write_text(
        '{"checklists":[{"checklist_id":"cn_programmatic_trading","counts":{"pending":1,"done":3,"blocked":0}}]}',
        encoding="utf-8",
    )
    (report_dir / "10_operations_readiness.json").write_text(
        '{"ready":true,"latest_report_dir":"data/reports/20260308-150000"}',
        encoding="utf-8",
    )
    (report_dir / "11_ops_execution_metrics.json").write_text(
        '{"exception_rate":0.0,"risk_hit_rate":0.0}',
        encoding="utf-8",
    )
    (report_dir / "11_data_quality.json").write_text(
        '{"ready":true,"incomplete_count":0}',
        encoding="utf-8",
    )
    (report_dir / "11_history_sync.json").write_text(
        '{"count":1,"healthy":true,"stale":false}',
        encoding="utf-8",
    )
    (report_dir / "11_selection_summary.json").write_text(
        '{"active":["strategy_a_etf_rotation"],"paper_only":["strategy_c_option_overlay"],"rejected":[]}',
        encoding="utf-8",
    )
    (report_dir / "11_allocation_summary.json").write_text(
        '{"active":[{"strategy_id":"strategy_a_etf_rotation","target_weight":1.0}],"paper_only":[],"rejected":[],"total_target_weight":1.0,"market_weights":{"US":1.0}}',
        encoding="utf-8",
    )
    (report_dir / "11_ops_rollout.json").write_text(
        '{"ready_for_rollout":true,"current_recommendation":"10%","next_stage":"30%","blockers":[]}',
        encoding="utf-8",
    )
    (report_dir / "11_ops_go_live.json").write_text(
        '{"promotion_allowed":false,"policy":{"stage":"30%"},"rollout":{"current_recommendation":"10%"}}',
        encoding="utf-8",
    )
    (report_dir / "11_ops_live_acceptance.json").write_text(
        '{"ready_for_live":false,"incident_count":2,"blockers":["gate still blocked"]}',
        encoding="utf-8",
    )
    (report_dir / "11_ops_rollout_checklist.json").write_text(
        '{"stage":"10%","ready":false,"blockers":["gate still blocked"]}',
        encoding="utf-8",
    )
    (report_dir / "11_ops_rollout_milestones.json").write_text(
        '{"next_pending_stage":"30%","milestones":[]}',
        encoding="utf-8",
    )
    (report_dir / "11_rollout_policy.json").write_text(
        '{"stage":"30%","allocation_ratio":0.3,"policy_matches_recommendation":false}',
        encoding="utf-8",
    )
    (report_dir / "12_execution_quality.json").write_text(
        '{"filled_samples":1,"within_limits":true,"equity_breaches":0,"option_breaches":0}',
        encoding="utf-8",
    )
    (report_dir / "13_recovery_summary.json").write_text(
        '{"count":1,"recovered_count":0,"failed_count":0}',
        encoding="utf-8",
    )
    (report_dir / "14_execution_authorization.json").write_text(
        '{"order_count":2,"unauthorized_count":0,"all_authorized":true}',
        encoding="utf-8",
    )
    (report_dir / "14_execution_gate.json").write_text(
        '{"ready":true,"should_block":false,"policy_stage":"30%","recommended_stage":"10%","reasons":[]}',
        encoding="utf-8",
    )

    payload = load_report_summary(report_dir)

    assert payload["operations_readiness"]["ready"] is True
    assert payload["ops_execution_metrics"]["exception_rate"] == 0.0
    assert payload["data_quality"]["ready"] is True
    assert payload["history_sync"]["healthy"] is True
    assert payload["selection_summary"]["active"] == ["strategy_a_etf_rotation"]
    assert payload["allocation_summary"]["market_weights"] == {"US": 1.0}
    assert payload["ops_rollout"]["current_recommendation"] == "10%"
    assert payload["ops_go_live"]["promotion_allowed"] is False
    assert payload["ops_live_acceptance"]["ready_for_live"] is False
    assert payload["ops_rollout_checklist"]["stage"] == "10%"
    assert payload["ops_rollout_milestones"]["next_pending_stage"] == "30%"
    assert payload["rollout_policy"]["stage"] == "30%"
    assert payload["execution_gate"]["ready"] is True
    assert payload["execution_quality"]["within_limits"] is True
    assert payload["recovery_summary"]["count"] == 1
    assert payload["execution_authorization"]["all_authorized"] is True
    assert payload["alerts_summary"]["count"] == 0
    assert len(payload["compliance_summary"]["checklists"]) == 1


def test_reporting_service_builds_period_report():
    now = datetime.now(UTC)
    payload = build_operations_period_report(
        label="daily",
        window_days=1,
        readiness={"ready": False, "diagnostics": {"category": "trade_channel_failed"}},
        acceptance={"ready_weeks": 1},
        rollout={"blockers": [{"actions": ["Fix trade channel before next cycle."]}]},
        execution_metrics={
            "exception_rate": 0.2,
            "risk_hit_rate": 0.1,
            "filled_samples": 2,
            "slippage_within_limits": True,
            "authorization_ok": True,
            "unauthorized_count": 0,
            "execution_tca": {
                "samples": [
                    {
                        "timestamp": now.isoformat(),
                        "symbol": "SPY",
                        "direction": "buy",
                        "asset_class": "etf",
                        "deviation_metric": "slippage_bps",
                        "deviation_value": 25.0,
                        "threshold": 20.0,
                        "expected_price": 200.0,
                        "realized_price": 200.5,
                        "reference_source": "market_quote",
                        "within_threshold": False,
                    }
                ]
            },
        },
        audit_events=[
            AuditLogEntry(created_at=now, category="execution", action="run_error", status="error", details={"detail": "trade failed"}),
            AuditLogEntry(created_at=now, category="risk", action="violation", status="warning", details={"detail": "drawdown"}),
        ],
        alerts=[
            AlertEvent(
                created_at=now,
                severity="error",
                category="trade_channel_failed",
                message="trade down",
                recovery_action="Reconnect trade channel.",
            )
        ],
        recoveries=[
            RecoveryAttempt(attempted_at=now, trigger="automatic", status="failed", detail="still down")
        ],
        journal_entries=[OperationsJournalEntry(recorded_at=now, ready=False, diagnostics_category="trade_channel_failed", diagnostics_severity="error", alert_count=1, checklist_pending=0, checklist_blocked=0)],
        period_insights={
            "tca_sample_count": 1,
            "top_execution_drags": [
                {
                    "symbol": "SPY",
                    "direction": "buy",
                    "asset_class": "etf",
                    "deviation_metric": "slippage_bps",
                    "deviation_value": 25.0,
                    "threshold": 20.0,
                    "expected_price": 200.0,
                    "realized_price": 200.5,
                    "reference_source": "market_quote",
                    "within_threshold": False,
                }
            ],
            "top_anomaly_sources": [{"source": "alert:trade_channel_failed", "type": "alert", "count": 1, "latest_at": now.isoformat()}],
        },
    )

    assert payload["label"] == "daily"
    assert payload["counts"]["alerts"] == 1
    assert payload["counts"]["execution_errors"] == 1
    assert payload["metrics"]["exception_rate"] == 0.2
    assert payload["metrics"]["tca_sample_count"] == 1
    assert payload["top_execution_drags"][0]["symbol"] == "SPY"
    assert payload["top_anomaly_sources"][0]["source"] == "alert:trade_channel_failed"
    assert payload["next_actions"]


def test_reporting_service_builds_postmortem():
    now = datetime.now(UTC)
    payload = build_postmortem_report(
        window_days=7,
        readiness={"ready": False},
        execution_metrics={"exception_rate": 0.3, "risk_hit_rate": 0.1, "authorization_ok": True, "slippage_within_limits": False},
        audit_events=[
            AuditLogEntry(created_at=now, category="execution", action="run_error", status="error", details={"detail": "trade down"})
        ],
        alerts=[
            AlertEvent(
                created_at=now,
                severity="error",
                category="trade_channel_failed",
                message="trade down",
                recovery_action="Reconnect trade channel.",
            )
        ],
        recoveries=[RecoveryAttempt(attempted_at=now, trigger="manual", status="failed", detail="failed to recover")],
    )

    assert payload["label"] == "postmortem"
    assert payload["incident_count"] >= 1
    assert payload["latest_incident"] is not None
    assert payload["recommended_actions"]


def test_reporting_service_builds_incident_replay():
    now = datetime.now(UTC)
    payload = build_incident_replay(
        window_days=7,
        audit_events=[AuditLogEntry(created_at=now, category="execution", action="run_error", status="error", details={"detail": "trade down"})],
        alerts=[AlertEvent(created_at=now, severity="error", category="trade_channel_failed", message="trade down", recovery_action="Reconnect trade channel.")],
        recoveries=[RecoveryAttempt(attempted_at=now, trigger="manual", status="failed", detail="failed to recover")],
    )

    assert payload["label"] == "incident_replay"
    assert payload["event_count"] == 3
    assert len(payload["events"]) == 3
