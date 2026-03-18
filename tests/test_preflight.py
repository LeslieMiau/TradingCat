from tradingcat.config import AppConfig, FutuConfig
from tradingcat.services.preflight import build_startup_preflight


def test_preflight_recommends_env_and_sdk_when_futu_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = build_startup_preflight(
        AppConfig(
            data_dir=tmp_path / "data",
            futu=FutuConfig(enabled=True, environment="REAL"),
        )
    )

    assert "checks" in payload
    assert any(check["name"] == "futu_sdk" for check in payload["checks"])
    assert any(".env" in item for item in payload["recommendations"])
    assert any("OpenD" in item for item in payload["recommendations"])


def test_preflight_passes_basic_local_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TRADINGCAT_FUTU_ENABLED=false\n", encoding="utf-8")
    payload = build_startup_preflight(AppConfig(data_dir=tmp_path / "data"))

    assert payload["healthy"] is True
    assert payload["futu"]["enabled"] is False
    assert payload["postgres"]["enabled"] is False
    assert payload["duckdb"]["enabled"] is False
    assert payload["scheduler"]["backend"] == "apscheduler"
    assert any(check["name"] == "postgres_enabled" for check in payload["checks"])
    assert any(check["name"] == "duckdb_enabled" for check in payload["checks"])
    assert any(check["name"] == "scheduler_driver" for check in payload["checks"])
