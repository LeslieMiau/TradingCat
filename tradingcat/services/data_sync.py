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
        sync_reports = sync_result.get("reports", []) if isinstance(sync_result, dict) else []
        failure_reports = sync_result.get("failures", []) if isinstance(sync_result, dict) else []
        missing_symbols = [str(report["symbol"]) for report in reports if float(report.get("coverage_ratio", 0.0)) < 0.95]
        minimum_coverage_ratio = min((float(report.get("coverage_ratio", 0.0)) for report in reports), default=1.0)
        complete_instruments = int(coverage_result.get("complete_instruments", 0))
        instrument_count = int(sync_result.get("instrument_count", 0))
        successful_symbols = [str(report["symbol"]) for report in sync_reports]
        failed_symbols = [str(report["symbol"]) for report in failure_reports]
        status = "ok"
        if instrument_count == 0:
            status = "failed"
        elif missing_symbols or failed_symbols:
            status = "partial"
        run = HistorySyncRun(
            start=sync_result["start"],
            end=sync_result["end"],
            instrument_count=instrument_count,
            complete_instruments=complete_instruments,
            minimum_coverage_ratio=round(minimum_coverage_ratio, 4),
            include_corporate_actions=include_corporate_actions,
            symbols=list(symbols or []),
            successful_symbols=successful_symbols,
            failed_symbols=failed_symbols,
            missing_symbols=missing_symbols,
            failed_symbol_count=len(failed_symbols),
            missing_symbol_count=len(missing_symbols),
            symbol_stats=self._symbol_stats(sync_reports, failure_reports, reports),
            status=status,
            notes=self._notes(status, missing_symbols, failed_symbols, complete_instruments, instrument_count),
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

    def _notes(self, status: str, missing_symbols: list[str], failed_symbols: list[str], complete: int, instrument_count: int) -> list[str]:
        if status == "failed":
            return ["History sync did not touch any instruments."]
        notes = [f"Covered {complete}/{instrument_count} instruments at >=95% ratio."]
        if missing_symbols:
            notes.append(f"Repair needed for: {', '.join(missing_symbols[:5])}.")
        if failed_symbols:
            notes.append(f"Sync failed for: {', '.join(failed_symbols[:5])}.")
        return notes

    def _symbol_stats(
        self,
        sync_reports: list[dict[str, object]],
        failure_reports: list[dict[str, object]],
        coverage_reports: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        sync_by_symbol = {str(report["symbol"]): report for report in sync_reports}
        failure_by_symbol = {str(report["symbol"]): report for report in failure_reports}
        coverage_by_symbol = {str(report["symbol"]): report for report in coverage_reports}
        symbols = sorted(set(sync_by_symbol) | set(failure_by_symbol) | set(coverage_by_symbol))
        rows: list[dict[str, object]] = []
        for symbol in symbols:
            sync_report = sync_by_symbol.get(symbol, {})
            failure_report = failure_by_symbol.get(symbol, {})
            coverage_report = coverage_by_symbol.get(symbol, {})
            if failure_report:
                status = "failed"
            elif float(coverage_report.get("coverage_ratio", 1.0)) < 0.95 or int(coverage_report.get("missing_count", 0)) > 0:
                status = "missing"
            else:
                status = "ok"
            rows.append(
                {
                    "symbol": symbol,
                    "status": status,
                    "bar_count": int(sync_report.get("bar_count", coverage_report.get("bar_count", 0))),
                    "coverage_ratio": round(float(coverage_report.get("coverage_ratio", 0.0)), 4),
                    "missing_count": int(coverage_report.get("missing_count", 0)),
                    "error": failure_report.get("error"),
                }
            )
        return rows
