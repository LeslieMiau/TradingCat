from __future__ import annotations

from datetime import date

from tradingcat.domain.models import BacktestExperiment, DashboardScorecardSnapshot
from tradingcat.repositories.research import DashboardSnapshotRepository


class DashboardSnapshotService:
    def __init__(
        self,
        repository: DashboardSnapshotRepository,
        *,
        strategy_signal_provider_getter,
        strategy_analysis_getter,
        experiments_getter,
    ) -> None:
        self._repository = repository
        self._strategy_signal_provider_getter = strategy_signal_provider_getter
        self._strategy_analysis_getter = strategy_analysis_getter
        self._experiments_getter = experiments_getter

    def load(self, as_of: date) -> dict[str, object]:
        snapshots = self._repository.load()
        available = [
            snapshot
            for snapshot in snapshots.values()
            if snapshot.as_of <= as_of
        ]
        if not available:
            return self._missing_snapshot(as_of)
        snapshot = max(available, key=lambda item: (item.as_of, item.generated_at))
        status = snapshot.snapshot_status
        reason = snapshot.snapshot_reason
        if snapshot.as_of != as_of and status == "ready":
            status = "stale"
            reason = reason or f"Using the latest persisted research snapshot from {snapshot.as_of.isoformat()}."
        return self._snapshot_payload(
            snapshot,
            snapshot_status=status,
            snapshot_reason=reason,
        )

    def refresh(self, as_of: date) -> dict[str, object]:
        provider = self._strategy_signal_provider_getter()
        strategy_signals = provider.strategy_signal_map(as_of, local_history_only=True)
        experiments = self._latest_experiments(as_of, strategy_ids=list(strategy_signals))
        scorecard = self._strategy_analysis_getter().reporting.build_profit_scorecard_from_experiments(
            as_of,
            strategy_signals,
            experiments,
        )
        missing_strategy_ids = sorted(set(strategy_signals) - set(experiments))
        status = "ready"
        reason = None
        if not scorecard.get("rows"):
            status = "missing"
            reason = "当前还没有可用的持久化研究评分卡。"
        elif missing_strategy_ids:
            status = "stale"
            preview = ", ".join(missing_strategy_ids[:5])
            reason = f"Missing persisted experiments for: {preview}."
        snapshot = DashboardScorecardSnapshot(
            as_of=as_of,
            snapshot_status=status,
            snapshot_reason=reason,
            portfolio_passed=bool(scorecard.get("portfolio_passed", False)),
            portfolio_metrics=dict(scorecard.get("portfolio_metrics", {})),
            accepted_strategy_ids=[str(item) for item in scorecard.get("accepted_strategy_ids", [])],
            blocked_strategy_ids=[str(item) for item in scorecard.get("blocked_strategy_ids", [])],
            blocked_count=int(scorecard.get("blocked_count", 0)),
            deploy_candidate_count=int(scorecard.get("deploy_candidate_count", 0)),
            paper_only_count=int(scorecard.get("paper_only_count", 0)),
            rejected_count=int(scorecard.get("rejected_count", 0)),
            rows=[dict(row) for row in scorecard.get("rows", [])],
            top_candidates=[dict(row) for row in scorecard.get("rows", [])[:5]],
            correlation_matrix=dict(scorecard.get("correlation_matrix", {})),
            reject_summary=[dict(item) for item in scorecard.get("reject_summary", [])],
            verdict_groups=[dict(item) for item in scorecard.get("verdict_groups", [])],
            next_actions=[str(item) for item in scorecard.get("next_actions", [])],
        )
        self._save_snapshot(snapshot)
        return self._snapshot_payload(snapshot)

    def save_scorecard(
        self,
        as_of: date,
        scorecard: dict[str, object],
        *,
        snapshot_reason: str | None = None,
    ) -> dict[str, object]:
        snapshot = DashboardScorecardSnapshot(
            as_of=as_of,
            snapshot_status="ready" if bool(scorecard.get("rows")) else "missing",
            snapshot_reason=snapshot_reason if scorecard.get("rows") else "尚未持久化任何候选评分卡行。",
            portfolio_passed=bool(scorecard.get("portfolio_passed", False)),
            portfolio_metrics=dict(scorecard.get("portfolio_metrics", {})),
            accepted_strategy_ids=[str(item) for item in scorecard.get("accepted_strategy_ids", [])],
            blocked_strategy_ids=[str(item) for item in scorecard.get("blocked_strategy_ids", [])],
            blocked_count=int(scorecard.get("blocked_count", 0)),
            deploy_candidate_count=int(scorecard.get("deploy_candidate_count", 0)),
            paper_only_count=int(scorecard.get("paper_only_count", 0)),
            rejected_count=int(scorecard.get("rejected_count", 0)),
            rows=[dict(row) for row in scorecard.get("rows", [])],
            top_candidates=[dict(row) for row in scorecard.get("top_candidates", scorecard.get("rows", [])[:5])],
            correlation_matrix=dict(scorecard.get("correlation_matrix", {})),
            reject_summary=[dict(item) for item in scorecard.get("reject_summary", [])],
            verdict_groups=[dict(item) for item in scorecard.get("verdict_groups", [])],
            next_actions=[str(item) for item in scorecard.get("next_actions", [])],
        )
        self._save_snapshot(snapshot)
        return self._snapshot_payload(snapshot)

    def clear(self) -> None:
        self._repository.clear()

    def _latest_experiments(self, as_of: date, *, strategy_ids: list[str]) -> dict[str, BacktestExperiment]:
        allowed = set(strategy_ids)
        latest: dict[str, BacktestExperiment] = {}
        for experiment in self._experiments_getter():
            if experiment.strategy_id not in allowed or experiment.as_of > as_of:
                continue
            previous = latest.get(experiment.strategy_id)
            if previous is None or (experiment.as_of, experiment.started_at) > (previous.as_of, previous.started_at):
                latest[experiment.strategy_id] = experiment
        return latest

    def _save_snapshot(self, snapshot: DashboardScorecardSnapshot) -> None:
        snapshots = self._repository.load()
        snapshots[snapshot.as_of.isoformat()] = snapshot
        self._repository.save(snapshots)

    def _missing_snapshot(self, as_of: date) -> dict[str, object]:
        return {
            "as_of": as_of.isoformat(),
            "snapshot_status": "missing",
            "snapshot_reason": "当前还没有可用的持久化 dashboard 快照，请先运行 /research/candidates/scorecard 或 /research/report/run。",
            "snapshot_as_of": None,
            "snapshot_generated_at": None,
            "portfolio_passed": False,
            "portfolio_metrics": {},
            "accepted_strategy_ids": [],
            "blocked_strategy_ids": [],
            "blocked_count": 0,
            "deploy_candidate_count": 0,
            "paper_only_count": 0,
            "rejected_count": 0,
            "rows": [],
            "top_candidates": [],
            "correlation_matrix": {},
            "reject_summary": [],
            "verdict_groups": [],
            "next_actions": [],
        }

    def _snapshot_payload(
        self,
        snapshot: DashboardScorecardSnapshot,
        *,
        snapshot_status: str | None = None,
        snapshot_reason: str | None = None,
    ) -> dict[str, object]:
        payload = snapshot.model_dump(mode="json")
        payload["snapshot_status"] = snapshot_status or snapshot.snapshot_status
        payload["snapshot_reason"] = snapshot_reason if snapshot_reason is not None else snapshot.snapshot_reason
        payload["snapshot_as_of"] = payload["as_of"]
        payload["snapshot_generated_at"] = payload["generated_at"]
        return payload
