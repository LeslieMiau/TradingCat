from tradingcat.repositories.state import ComplianceRepository
from tradingcat.services.compliance import ComplianceService


def test_compliance_service_seeds_and_updates_checklists(tmp_path):
    service = ComplianceService(ComplianceRepository(tmp_path))

    checklists = service.list_checklists()
    assert len(checklists) >= 2

    updated = service.update_item(
        "cn_programmatic_trading",
        "cn_manual_only",
        "done",
        "A-share remains manual in V1.",
    )

    item = next(item for item in updated.items if item.id == "cn_manual_only")
    assert item.status == "done"
    assert item.notes == "A-share remains manual in V1."
