from datetime import UTC, datetime, timedelta

from tradingcat.repositories.state import OperationsJournalRepository
from tradingcat.services.operations import OperationsJournalService


def test_operations_journal_records_and_summarizes(tmp_path):
    service = OperationsJournalService(OperationsJournalRepository(tmp_path))

    first = service.record(
        {
            "ready": True,
            "diagnostics": {"category": "ready_for_validation", "severity": "info", "findings": [], "next_actions": []},
            "alerts": {"count": 0},
            "compliance": {"checklists": [{"counts": {"pending": 2, "blocked": 0}}]},
            "latest_report_dir": "data/reports/one",
        }
    )
    second = service.record(
        {
            "ready": False,
            "diagnostics": {"category": "trade_channel_failed", "severity": "error", "findings": [], "next_actions": []},
            "alerts": {"count": 2},
            "compliance": {"checklists": [{"counts": {"pending": 1, "blocked": 1}}]},
            "latest_report_dir": "data/reports/two",
        }
    )

    summary = service.summary()

    assert first.id != second.id
    assert summary["count"] == 2
    assert summary["ready_ratio"] == 0.5
    assert summary["average_alert_count"] == 1
    assert summary["latest"].latest_report_dir == "data/reports/two"
    assert "incident_day" in summary["latest"].evidence_tags


def test_operations_acceptance_summary_tracks_paper_trading_thresholds(tmp_path):
    service = OperationsJournalService(OperationsJournalRepository(tmp_path))

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(56):
        entry = service.record(
            {
                "ready": True,
                "diagnostics": {"category": "ready_for_validation", "severity": "info", "findings": [], "next_actions": []},
                "alerts": {"count": 0},
                "compliance": {"checklists": [{"counts": {"pending": 0, "blocked": 0}}]},
                "latest_report_dir": f"data/reports/{index}",
            }
        )
        entry.recorded_at = base + timedelta(days=index)
        service._entries[entry.id] = entry
    service._repository.save(service._entries)

    acceptance = service.acceptance_summary()

    assert acceptance["paper_trading"]["hk_us_passed"] is True
    assert acceptance["paper_trading"]["cn_passed"] is True
    assert acceptance["ready_weeks"] == 8
    assert acceptance["rollout"]["recommended_stage"] == "100%"
    assert acceptance["evidence"]["counts"]["clean_day"] == 56


def test_operations_rollout_summary_includes_blockers_and_remaining_gates(tmp_path):
    service = OperationsJournalService(OperationsJournalRepository(tmp_path))

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(7):
        entry = service.record(
            {
                "ready": True,
                "diagnostics": {"category": "ready_for_validation", "severity": "info", "findings": [], "next_actions": []},
                "alerts": {"count": 0},
                "compliance": {"checklists": [{"counts": {"pending": 0, "blocked": 0}}]},
                "latest_report_dir": f"data/reports/{index}",
            }
        )
        entry.recorded_at = base + timedelta(days=index)
        service._entries[entry.id] = entry
    service._repository.save(service._entries)

    rollout = service.rollout_summary(
        readiness={
            "ready": False,
            "diagnostics": {"category": "trade_channel_failed", "severity": "error", "next_actions": ["Reconnect OpenD"]},
        },
        compliance_summary={"checklists": [{"id": "broker_capabilities", "counts": {"pending": 1, "blocked": 1}}]},
        alerts_summary={"count": 2},
    )

    assert rollout["ready_for_rollout"] is False
    assert rollout["current_recommendation"] == "10%"
    assert rollout["next_stage"] == "30%"
    assert rollout["remaining_gates"]["hk_us_paper_weeks"] == 5
    assert len(rollout["blockers"]) == 4
    assert any("clean week" in blocker.lower() for blocker in rollout["blockers"])


def test_operations_acceptance_timeline_and_milestones(tmp_path):
    service = OperationsJournalService(OperationsJournalRepository(tmp_path))

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(35):
        entry = service.record(
            {
                "ready": index % 2 == 0,
                "diagnostics": {"category": "ready_for_validation" if index % 2 == 0 else "trade_channel_failed", "severity": "info" if index % 2 == 0 else "error", "findings": [], "next_actions": []},
                "alerts": {"count": 0 if index % 2 == 0 else 1},
                "compliance": {"checklists": [{"counts": {"pending": 0, "blocked": 0}}]},
                "latest_report_dir": f"data/reports/{index}",
            }
        )
        entry.recorded_at = base + timedelta(days=index)
        service._entries[entry.id] = entry
    service._repository.save(service._entries)

    timeline = service.acceptance_timeline(window_days=14)
    milestones = service.rollout_milestones()

    assert timeline["window_days"] == 14
    assert len(timeline["points"]) == 14
    assert "evidence_tags" in timeline["points"][0]
    assert "incident_day" in timeline["evidence_counts"]
    assert "next_requirement" in timeline
    assert "current_recommendation" in milestones
    assert len(milestones["milestones"]) == 4


def test_operations_journal_persists_manual_and_blocked_evidence_tags(tmp_path):
    service = OperationsJournalService(OperationsJournalRepository(tmp_path))

    entry = service.record(
        {
            "ready": False,
            "diagnostics": {"category": "manual_pending", "severity": "error", "findings": [], "next_actions": []},
            "alerts": {"count": 1},
            "execution": {"pending_approval_count": 1},
            "compliance": {"checklists": [{"counts": {"pending": 0, "blocked": 0}}]},
            "latest_report_dir": "data/reports/manual",
        }
    )

    acceptance = service.acceptance_summary()
    timeline = service.acceptance_timeline(window_days=1)

    assert set(entry.evidence_tags) == {"manual_day", "incident_day", "blocked_day"}
    assert acceptance["evidence"]["counts"]["manual_day"] == 1
    assert timeline["points"][0]["evidence_tags"] == ["blocked_day", "incident_day", "manual_day"]


def test_operations_rollout_summary_uses_acceptance_evidence(tmp_path):
    service = OperationsJournalService(OperationsJournalRepository(tmp_path))

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(21):
        entry = service.record(
            {
                "ready": index < 14,
                "diagnostics": {"category": "ready_for_validation" if index < 14 else "trade_channel_failed", "severity": "info" if index < 14 else "error", "findings": [], "next_actions": []},
                "alerts": {"count": 0 if index < 14 else 1},
                "execution": {"pending_approval_count": 0},
                "compliance": {"checklists": [{"counts": {"pending": 0, "blocked": 0}}]},
                "latest_report_dir": f"data/reports/{index}",
            }
        )
        entry.recorded_at = base + timedelta(days=index)
        service._entries[entry.id] = entry
    service._repository.save(service._entries)

    rollout = service.rollout_summary(
        readiness={"ready": True, "diagnostics": {"next_actions": []}},
        compliance_summary={"checklists": []},
        alerts_summary={"count": 0},
    )

    assert rollout["evidence"]["ready_weeks"] == 2
    assert rollout["evidence"]["counts"]["incident_day"] == 7
    assert rollout["ready_for_rollout"] is False
    assert any("incident day" in blocker.lower() for blocker in rollout["blockers"])
