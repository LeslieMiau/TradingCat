from __future__ import annotations

from datetime import date

from tradingcat.domain.models import HistorySyncRun
from tradingcat.repositories.state import HistorySyncRunRepository


class HistorySyncService:
    def __init__(self, repository: HistorySyncRunRepository) -> None:
        self._repository = repository
        self._runs = repository.load()

    def record_run(
        self,
        *,
        sync_result: dict[str, object],
        coverage_result: dict[str, object],
        symbols: list[str] | None,
        include_corporate_actions: bool,
    ) -> HistorySyncRun:
        reports = coverage_result.get("reports", []) if isinstance(coverage_result, dict) else []
        missing_symbols = [str(report["symbol"]) for report in reports if float(report.get("coverage_ratio", 0.0)) < 0.95]
        minimum_coverage_ratio = min((float(report.get("coverage_ratio", 0.0)) for report in reports), default=1.0)
        complete_instruments = int(coverage_result.get("complete_instruments", 0))
        instrument_count = int(sync_result.get("instrument_count", 0))
        status = "ok"
        if instrument_count == 0:
            status = "failed"
        elif missing_symbols:
            status = "partial"
        run = HistorySyncRun(
            start=sync_result["start"],
            end=sync_result["end"],
            instrument_count=instrument_count,
            complete_instruments=complete_instruments,
            minimum_coverage_ratio=round(minimum_coverage_ratio, 4),
            include_corporate_actions=include_corporate_actions,
            symbols=list(symbols or []),
            missing_symbols=missing_symbols,
            status=status,
            notes=self._notes(status, missing_symbols, complete_instruments, instrument_count),
        )
        self._runs[run.id] = run
        self._repository.save(self._runs)
        return run

    def list_runs(self) -> list[HistorySyncRun]:
        return sorted(self._runs.values(), key=lambda item: item.started_at, reverse=True)

    def summary(self) -> dict[str, object]:
        runs = self.list_runs()
        latest = runs[0] if runs else None
        return {
            "count": len(runs),
            "latest": latest,
            "healthy": bool(latest is not None and latest.status != "failed" and latest.minimum_coverage_ratio >= 0.95),
            "stale": self._is_stale(latest),
        }

    def repair_plan(self, coverage_result: dict[str, object]) -> dict[str, object]:
        reports = coverage_result.get("reports", []) if isinstance(coverage_result, dict) else []
        repairs = []
        for report in reports:
            if float(report.get("coverage_ratio", 0.0)) >= 0.95:
                continue
            repairs.append(
                {
                    "symbol": report["symbol"],
                    "market": report["market"],
                    "missing_count": report["missing_count"],
                    "missing_preview": report["missing_preview"],
                    "suggested_start": report["missing_preview"][0] if report["missing_preview"] else coverage_result.get("start"),
                    "suggested_end": report["missing_preview"][-1] if report["missing_preview"] else coverage_result.get("end"),
                }
            )
        return {
            "start": coverage_result.get("start"),
            "end": coverage_result.get("end"),
            "repair_count": len(repairs),
            "repairs": repairs,
            "next_actions": [
                "Run POST /data/history/sync for the missing symbols and date window.",
                "Recheck GET /data/history/coverage after the repair sync completes.",
            ]
            if repairs
            else ["No repair sync is needed for the current history window."],
        }

    def clear(self) -> None:
        self._runs = {}
        self._repository.save(self._runs)

    def _is_stale(self, latest: HistorySyncRun | None) -> bool:
        if latest is None:
            return True
        return (date.today() - latest.started_at.date()).days > 3

    def _notes(self, status: str, missing_symbols: list[str], complete: int, instrument_count: int) -> list[str]:
        if status == "failed":
            return ["History sync did not touch any instruments."]
        notes = [f"Covered {complete}/{instrument_count} instruments at >=95% ratio."]
        if missing_symbols:
            notes.append(f"Repair needed for: {', '.join(missing_symbols[:5])}.")
        return notes
