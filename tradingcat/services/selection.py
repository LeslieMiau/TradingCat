from __future__ import annotations

from tradingcat.domain.models import StrategySelectionRecord
from tradingcat.repositories.state import StrategySelectionRepository


class StrategySelectionService:
    def __init__(self, repository: StrategySelectionRepository) -> None:
        self._repository = repository
        self._records = repository.load()

    def list_records(self) -> list[StrategySelectionRecord]:
        return sorted(self._records.values(), key=lambda item: (item.reviewed_at, item.strategy_id), reverse=True)

    def summary(self) -> dict[str, object]:
        records = self.list_records()
        return {
            "count": len(records),
            "active": [record.strategy_id for record in records if record.decision == "active"],
            "paper_only": [record.strategy_id for record in records if record.decision == "paper_only"],
            "rejected": [record.strategy_id for record in records if record.decision == "rejected"],
            "latest_reviewed_at": records[0].reviewed_at if records else None,
        }

    def active_strategy_ids(self) -> list[str]:
        return list(self.summary()["active"])

    def review(self, recommendation_report: dict[str, object]) -> dict[str, object]:
        as_of = recommendation_report["as_of"]
        accepted = set(recommendation_report.get("accepted_strategy_ids", []))
        updated: list[StrategySelectionRecord] = []
        for recommendation in recommendation_report.get("recommendations", []):
            strategy_id = str(recommendation["strategy_id"])
            recommended_action = str(recommendation["action"])
            if recommended_action == "keep" and strategy_id in accepted:
                decision = "active"
                selected = True
            elif recommended_action == "paper_only":
                decision = "paper_only"
                selected = False
            else:
                decision = "rejected"
                selected = False
            record = StrategySelectionRecord(
                as_of=as_of,
                strategy_id=strategy_id,
                recommended_action=recommended_action,
                selected_for_next_phase=selected,
                decision=decision,
                reasons=[str(item) for item in recommendation.get("reasons", [])],
                metrics=dict(recommendation.get("metrics", {})),
                capacity_tier=str(recommendation.get("capacity_tier", "unknown")),
                max_selected_correlation=float(recommendation.get("max_selected_correlation", 0.0)),
            )
            self._records[strategy_id] = record
            updated.append(record)
        self._repository.save(self._records)
        return {
            "updated": updated,
            "summary": self.summary(),
            "next_actions": recommendation_report.get("next_actions", []),
        }

    def clear(self) -> None:
        self._records = {}
        self._repository.save(self._records)
