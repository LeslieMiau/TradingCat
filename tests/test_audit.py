from tradingcat.repositories.state import AuditLogRepository
from tradingcat.services.audit import AuditService


def test_audit_service_records_and_summarizes(tmp_path):
    service = AuditService(AuditLogRepository(tmp_path))

    service.log(category="approval", action="approve", details={"request_id": "1"})
    service.log(category="risk", action="kill_switch_set", status="warning", details={"enabled": True})

    summary = service.summary()
    approval_events = service.list_events(category="approval")

    assert summary["count"] == 2
    assert summary["warning_count"] == 1
    assert "approval" in summary["categories"]
    assert len(approval_events) == 1


def test_audit_service_builds_execution_metrics_summary(tmp_path):
    service = AuditService(AuditLogRepository(tmp_path))

    service.log(category="execution", action="preview_ok", details={"intent_count": 2})
    service.log(category="execution", action="run_partial", status="warning", details={"failed_count": 1})
    service.log(category="risk", action="violation", status="warning", details={"source": "execution_run"})

    metrics = service.execution_metrics_summary()

    assert metrics["cycle_count"] == 3
    assert metrics["risk_hit_count"] == 1
    assert metrics["risk_hit_rate"] > 0
