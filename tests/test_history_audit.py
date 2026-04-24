from datetime import date, timedelta

from tradingcat.config import AppConfig, FutuConfig
from tradingcat.main import TradingCatApplication
from tradingcat.repositories.state import HistoryAuditRunRepository
from tradingcat.services.data_sync import HistoryAuditService


def _coverage(
    *,
    minimum_ratio: float = 1.0,
    missing_symbols: list[str] | None = None,
    reports: list[dict] | None = None,
) -> dict:
    missing = missing_symbols or []
    default_reports = reports if reports is not None else [
        {"symbol": "SPY", "market": "US", "coverage_ratio": 1.0, "missing_count": 0, "missing_preview": []},
    ]
    return {
        "instrument_count": len(default_reports),
        "complete_instruments": sum(1 for r in default_reports if r["missing_count"] == 0),
        "minimum_coverage_ratio": minimum_ratio,
        "missing_symbols": missing,
        "reports": default_reports,
    }


def test_capture_classifies_ok_when_full_coverage(tmp_path):
    service = HistoryAuditService(HistoryAuditRunRepository(tmp_path))
    run = service.capture(_coverage(), as_of=date(2026, 4, 19), window_days=90)
    assert run.status == "ok"
    assert run.minimum_coverage_ratio == 1.0
    assert run.missing_symbol_count == 0
    assert run.top_findings == []


def test_capture_classifies_drift_on_minor_gap(tmp_path):
    service = HistoryAuditService(HistoryAuditRunRepository(tmp_path))
    reports = [
        {"symbol": "AAPL", "market": "US", "coverage_ratio": 0.98, "missing_count": 2, "missing_preview": ["2026-03-01", "2026-03-02"]},
    ]
    run = service.capture(
        _coverage(minimum_ratio=0.98, missing_symbols=["AAPL"], reports=reports),
        as_of=date(2026, 4, 19),
    )
    assert run.status == "drift"
    assert run.missing_symbol_count == 1
    assert run.top_findings[0]["symbol"] == "AAPL"
    assert run.top_findings[0]["missing_count"] == 2


def test_capture_classifies_critical_on_wide_gaps(tmp_path):
    service = HistoryAuditService(HistoryAuditRunRepository(tmp_path))
    reports = [
        {"symbol": f"SYM{i}", "market": "US", "coverage_ratio": 0.5, "missing_count": 45, "missing_preview": []}
        for i in range(25)
    ]
    run = service.capture(
        _coverage(
            minimum_ratio=0.5,
            missing_symbols=[r["symbol"] for r in reports],
            reports=reports,
        ),
        as_of=date(2026, 4, 19),
    )
    assert run.status == "critical"
    assert run.missing_symbol_count == 25
    assert len(run.top_findings) == HistoryAuditService.TOP_FINDINGS_LIMIT


def test_capture_is_idempotent_per_day(tmp_path):
    service = HistoryAuditService(HistoryAuditRunRepository(tmp_path))
    first = service.capture(_coverage(), as_of=date(2026, 4, 19), notes=["first"])
    second = service.capture(_coverage(), as_of=date(2026, 4, 19), notes=["second"])
    runs = HistoryAuditService(HistoryAuditRunRepository(tmp_path)).list_runs()
    assert first.id == second.id
    assert len(runs) == 1
    assert runs[0].notes == ["second"]


def test_timeline_aggregates_status_counts(tmp_path):
    service = HistoryAuditService(HistoryAuditRunRepository(tmp_path))
    today = date.today()
    service.capture(_coverage(minimum_ratio=0.5, missing_symbols=["X"] * 25,
                              reports=[{"symbol": "X", "market": "US", "coverage_ratio": 0.5, "missing_count": 45, "missing_preview": []}]),
                    as_of=today - timedelta(days=3))
    service.capture(_coverage(minimum_ratio=0.98, missing_symbols=["Y"],
                              reports=[{"symbol": "Y", "market": "US", "coverage_ratio": 0.98, "missing_count": 1, "missing_preview": []}]),
                    as_of=today - timedelta(days=2))
    service.capture(_coverage(), as_of=today - timedelta(days=1))
    service.capture(_coverage(), as_of=today)
    timeline = service.timeline(window_days=7)
    summary = timeline["summary"]
    assert summary["audit_count"] == 4
    assert summary["ok_count"] == 2
    assert summary["drift_count"] == 1
    assert summary["critical_count"] == 1
    assert summary["latest_status"] == "ok"


def test_run_history_audit_through_app(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )
    payload = app.run_history_audit(window_days=30, as_of=date(2026, 4, 19))
    assert payload["status"] in {"ok", "drift", "critical"}
    assert payload["window_days"] == 30
    assert payload["as_of"] == "2026-04-19"

    timeline = app.history_audit_timeline(window_days=7)
    assert timeline["window_days"] == 7
    assert timeline["summary"]["audit_count"] >= 1


def test_scheduler_job_handler(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )
    detail = app.scheduler_runtime.run_history_audit_job()
    assert detail.startswith("History audit")
