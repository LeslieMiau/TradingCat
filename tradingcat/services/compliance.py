from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.domain.models import ChecklistItem, ComplianceChecklist
from tradingcat.repositories.state import ComplianceRepository


def default_checklists() -> dict[str, ComplianceChecklist]:
    return {
        "cn_programmatic_trading": ComplianceChecklist(
            checklist_id="cn_programmatic_trading",
            title="A-share Compliance Checklist",
            items=[
                ChecklistItem(
                    id="cn_manual_only",
                    label="Confirm A-share execution remains manual until broker/API compliance is explicitly cleared.",
                ),
                ChecklistItem(
                    id="cn_exchange_rules_review",
                    label="Review current SSE/SZSE programmatic trading filing and reporting obligations.",
                ),
                ChecklistItem(
                    id="cn_broker_confirmation",
                    label="Confirm broker-side reporting or filing requirements for semi-automated trading.",
                ),
                ChecklistItem(
                    id="cn_operator_runbook",
                    label="Document the manual approval, kill switch, and fill reconciliation runbook for A-share trades.",
                ),
            ],
        ),
        "broker_capabilities": ComplianceChecklist(
            checklist_id="broker_capabilities",
            title="Broker Capability Checklist",
            items=[
                ChecklistItem(id="futu_sim_account", label="Verify Futu simulated account is accessible."),
                ChecklistItem(id="futu_quote_permissions", label="Verify quote permissions for HK, US, and CN markets."),
                ChecklistItem(id="futu_trade_permissions", label="Verify trade permissions for HK and US markets."),
                ChecklistItem(id="futu_us_options_permissions", label="Verify US options permissions for hedge and covered-call workflows."),
            ],
        ),
    }


class ComplianceService:
    def __init__(self, repository: ComplianceRepository) -> None:
        self._repository = repository
        self._checklists = repository.load()
        if not self._checklists:
            self._checklists = default_checklists()
            self._repository.save(self._checklists)

    def list_checklists(self) -> list[ComplianceChecklist]:
        return sorted(self._checklists.values(), key=lambda item: item.checklist_id)

    def summary(self) -> dict[str, object]:
        payload = []
        for checklist in self.list_checklists():
            counts = {"pending": 0, "done": 0, "blocked": 0}
            for item in checklist.items:
                counts[item.status] += 1
            payload.append({"checklist_id": checklist.checklist_id, "title": checklist.title, "counts": counts})
        return {"checklists": payload}

    def update_item(self, checklist_id: str, item_id: str, status: str, notes: str | None = None) -> ComplianceChecklist:
        checklist = self._checklists[checklist_id]
        updated_items = []
        found = False
        for item in checklist.items:
            if item.id == item_id:
                updated_items.append(
                    ChecklistItem(
                        id=item.id,
                        label=item.label,
                        status=status,
                        notes=notes,
                        updated_at=datetime.now(UTC),
                    )
                )
                found = True
            else:
                updated_items.append(item)
        if not found:
            raise KeyError(item_id)
        updated = ComplianceChecklist(
            checklist_id=checklist.checklist_id,
            title=checklist.title,
            items=updated_items,
            updated_at=datetime.now(UTC),
        )
        self._checklists[checklist_id] = updated
        self._repository.save(self._checklists)
        return updated
