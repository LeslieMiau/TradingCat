from tradingcat.config import AppConfig
from tradingcat.services.preflight import _redact_dsn, build_startup_preflight, summarize_validation_diagnostics


def test_diagnostics_summary_flags_disabled_futu():
    payload = summarize_validation_diagnostics(
        preflight={
            "futu": {"enabled": False},
            "checks": [{"name": "env_file", "ok": True}],
        },
        broker_validation={"checks": {"quote": {"status": "skipped"}, "trade": {"status": "skipped"}}},
    )

    assert payload["category"] == "futu_disabled"
    assert payload["severity"] == "warning"
    assert payload["ready"] is False
    assert any("TRADINGCAT_FUTU_ENABLED=true" in item for item in payload["next_actions"])


def test_diagnostics_summary_flags_sdk_missing():
    payload = summarize_validation_diagnostics(
        preflight={
            "futu": {"enabled": True},
            "checks": [
                {"name": "env_file", "ok": True},
                {"name": "futu_sdk", "ok": False, "detail": "missing"},
                {"name": "futu_environment", "ok": True, "detail": "SIMULATE"},
            ],
        },
        broker_validation={"checks": {"quote": {"status": "skipped"}, "trade": {"status": "skipped"}}},
    )

    assert payload["category"] == "sdk_missing"
    assert payload["severity"] == "error"
    assert payload["ready"] is False
    assert any("Install dependencies" in item for item in payload["next_actions"])


def test_diagnostics_summary_marks_ready_path():
    payload = summarize_validation_diagnostics(
        preflight={
            "futu": {"enabled": True},
            "checks": [
                {"name": "env_file", "ok": True},
                {"name": "futu_sdk", "ok": True, "detail": "installed"},
                {"name": "futu_environment", "ok": True, "detail": "SIMULATE"},
            ],
        },
        broker_validation={"checks": {"quote": {"status": "ok"}, "trade": {"status": "ok"}}},
        market_data={"symbols": ["SPY"]},
        execution_preview={"intent_count": 3, "manual_count": 1},
    )

    assert payload["category"] == "ready_for_validation"
    assert payload["severity"] == "info"
    assert payload["ready"] is True


def test_redact_dsn_hides_password():
    assert _redact_dsn("postgresql://alice:s3cr3t@db.internal/tradingcat") == "postgresql://alice:***@db.internal/tradingcat"
    assert _redact_dsn("postgresql:///tradingcat") == "postgresql:///tradingcat"


def test_build_startup_preflight_redacts_postgres_dsn(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGCAT_POSTGRES_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_POSTGRES_DSN", "postgresql://alice:s3cr3t@db.internal/tradingcat")
    monkeypatch.setenv("TRADINGCAT_DATA_DIR", str(tmp_path))

    payload = build_startup_preflight(AppConfig.from_env())

    assert payload["postgres"]["dsn"] == "postgresql://alice:***@db.internal/tradingcat"
