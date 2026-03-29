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


def test_audit_service_summarizes_order_context_and_transitions(tmp_path):
    service = AuditService(AuditLogRepository(tmp_path))

    service.log(
        category="execution",
        action="manual_order_submitted",
        details=service.build_order_details(
            order_intent_id="order-1",
            broker_order_id="broker-1",
            order_status="pending_approval",
            authorization_context={
                "authorization_mode": "manual_pending",
                "final_authorization_mode": "manual_pending",
                "approval_request_id": "approval-1",
                "approval_status": "pending",
            },
            extra={"symbol": "SPY"},
        ),
    )
    service.log(
        category="approval",
        action="approve",
        details=service.build_order_details(
            order_intent_id="order-1",
            broker_order_id="broker-1",
            previous_order_status="pending_approval",
            order_status="submitted",
            authorization_context={
                "authorization_mode": "manual_approved",
                "final_authorization_mode": "manual_approved",
                "approval_request_id": "approval-1",
                "approval_status": "approved",
            },
        ),
    )
    service.log(
        category="execution",
        action="manual_fill",
        details=service.build_order_details(
            order_intent_id="order-1",
            broker_order_id="broker-1",
            previous_order_status="submitted",
            order_status="filled",
            authorization_context={
                "authorization_mode": "manual_pending",
                "final_authorization_mode": "manual_fill_external",
                "approval_request_id": "approval-1",
                "approval_status": "external_fill",
                "external_source": "broker_statement",
            },
            reconciliation_source="broker_statement",
        ),
    )

    summary = service.summary()
    order = summary["orders"][0]
    events = service.list_events(order_intent_id="order-1")

    assert summary["tracked_order_count"] == 1
    assert summary["order_transition_count"] == 3
    assert len(events) == 3
    assert order["approval_request_id"] == "approval-1"
    assert order["final_authorization_mode"] == "manual_fill_external"
    assert order["reconciliation_sources"] == ["broker_statement"]
    assert [transition["to_status"] for transition in order["status_transitions"]] == [
        "pending_approval",
        "submitted",
        "filled",
    ]
