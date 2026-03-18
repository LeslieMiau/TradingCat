from __future__ import annotations

from tradingcat.domain.models import StrategyAllocationRecord
from tradingcat.repositories.state import StrategyAllocationRepository


class StrategyAllocationService:
    _CAPACITY_FACTOR = {
        "high": 1.0,
        "medium": 0.75,
        "limited": 0.35,
        "unknown": 0.6,
    }

    def __init__(self, repository: StrategyAllocationRepository) -> None:
        self._repository = repository
        self._records = repository.load()

    def list_records(self) -> list[StrategyAllocationRecord]:
        return sorted(self._records.values(), key=lambda item: (item.reviewed_at, item.strategy_id), reverse=True)

    def summary(self) -> dict[str, object]:
        records = self.list_records()
        active = [record for record in records if record.decision == "active"]
        paper_only = [record for record in records if record.decision == "paper_only"]
        market_weights: dict[str, float] = {}
        for record in active:
            for market, weight in record.market_distribution.items():
                market_weights[market] = round(market_weights.get(market, 0.0) + record.target_weight * float(weight), 6)
        return {
            "count": len(records),
            "active": [record.model_dump(mode="json") for record in active],
            "paper_only": [record.model_dump(mode="json") for record in paper_only],
            "rejected": [record.model_dump(mode="json") for record in records if record.decision == "rejected"],
            "total_target_weight": round(sum(record.target_weight for record in active), 6),
            "market_weights": market_weights,
            "latest_reviewed_at": records[0].reviewed_at if records else None,
        }

    def active_strategy_ids(self) -> list[str]:
        return [record.strategy_id for record in self.list_records() if record.decision == "active" and record.target_weight > 0]

    def review(self, recommendation_report: dict[str, object]) -> dict[str, object]:
        recommendations = list(recommendation_report.get("recommendations", []))
        scored: list[tuple[dict[str, object], float]] = []
        for recommendation in recommendations:
            action = str(recommendation.get("action", "drop"))
            if action != "keep":
                continue
            scored.append((recommendation, self._score(recommendation)))

        score_total = sum(score for _, score in scored) or 1.0
        updated: list[StrategyAllocationRecord] = []
        as_of = recommendation_report["as_of"]

        for recommendation in recommendations:
            strategy_id = str(recommendation["strategy_id"])
            action = str(recommendation.get("action", "drop"))
            score = self._score(recommendation) if action == "keep" else 0.0
            target_weight = round(score / score_total, 6) if action == "keep" else 0.0
            shadow_weight = 0.05 if action == "paper_only" else 0.0
            decision = {
                "keep": "active",
                "paper_only": "paper_only",
            }.get(action, "rejected")
            record = StrategyAllocationRecord(
                as_of=as_of,
                strategy_id=strategy_id,
                decision=decision,
                target_weight=target_weight,
                shadow_weight=shadow_weight,
                score=round(score, 6),
                capacity_tier=str(recommendation.get("capacity_tier", "unknown")),
                market_distribution={
                    str(key): float(value)
                    for key, value in dict(recommendation.get("market_distribution", {})).items()
                },
                reasons=[str(item) for item in recommendation.get("reasons", [])],
            )
            self._records[strategy_id] = record
            updated.append(record)

        self._repository.save(self._records)
        summary = self.summary()
        return {
            "updated": updated,
            "summary": summary,
            "next_actions": self._next_actions(summary),
        }

    def clear(self) -> None:
        self._records = {}
        self._repository.save(self._records)

    def _score(self, recommendation: dict[str, object]) -> float:
        metrics = recommendation.get("metrics", {})
        sharpe = max(0.0, float(metrics.get("sharpe", 0.0)))
        calmar = max(0.0, float(metrics.get("calmar", 0.0)))
        turnover_penalty = min(1.0, max(0.0, float(metrics.get("turnover", 0.0)) / 4.0))
        correlation_penalty = min(1.0, max(0.0, float(recommendation.get("max_selected_correlation", 0.0))))
        capacity_factor = self._CAPACITY_FACTOR.get(str(recommendation.get("capacity_tier", "unknown")), 0.6)
        base_score = (0.65 * sharpe) + (0.35 * calmar)
        score = base_score * capacity_factor * (1.0 - 0.4 * turnover_penalty) * (1.0 - 0.5 * correlation_penalty)
        return max(round(score, 6), 0.000001)

    def _next_actions(self, summary: dict[str, object]) -> list[str]:
        actions: list[str] = []
        if not summary["active"]:
            actions.append("No active strategy allocation is ready; keep the portfolio in paper-trading mode.")
        if summary["paper_only"]:
            actions.append("Keep paper-only strategies outside live capital but continue collecting evidence.")
        if len(summary["market_weights"]) > 1:
            actions.append("Use market_weights as the first-pass budget split before instrument-level rebalancing.")
        return actions or ["Current active strategy allocations can be used for the next rebalance review."]
