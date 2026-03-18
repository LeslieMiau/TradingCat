from pathlib import Path

from tradingcat.config import AppConfig


def test_app_config_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGCAT_PORTFOLIO_VALUE", "250000")
    monkeypatch.setenv("TRADINGCAT_BASE_CURRENCY", "usd")
    monkeypatch.setenv("TRADINGCAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADINGCAT_FUTU_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_FUTU_ENVIRONMENT", "real")
    monkeypatch.setenv("TRADINGCAT_FUTU_PORT", "22222")
    monkeypatch.setenv("TRADINGCAT_POSTGRES_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_POSTGRES_DSN", "postgresql:///tradingcat_test")
    monkeypatch.setenv("TRADINGCAT_DUCKDB_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_DUCKDB_PATH", str(tmp_path / "research.duckdb"))
    monkeypatch.setenv("TRADINGCAT_PARQUET_DIR", str(tmp_path / "parquet"))
    monkeypatch.setenv("TRADINGCAT_SCHEDULER_BACKEND", "lightweight")
    monkeypatch.setenv("TRADINGCAT_SCHEDULER_AUTOSTART", "false")

    config = AppConfig.from_env()

    assert config.portfolio_value == 250000
    assert config.base_currency == "USD"
    assert config.data_dir == tmp_path
    assert config.futu.enabled is True
    assert config.futu.environment == "REAL"
    assert config.futu.port == 22222
    assert config.postgres.enabled is True
    assert config.postgres.dsn == "postgresql:///tradingcat_test"
    assert config.duckdb.enabled is True
    assert config.duckdb.path == tmp_path / "research.duckdb"
    assert config.duckdb.parquet_dir == tmp_path / "parquet"
    assert config.scheduler.backend == "lightweight"
    assert config.scheduler.autostart is False


def test_app_config_loads_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TRADINGCAT_PORTFOLIO_VALUE=750000",
                "TRADINGCAT_BASE_CURRENCY=hkd",
                "TRADINGCAT_DATA_DIR=runtime-data",
                "TRADINGCAT_FUTU_ENABLED=true",
                "TRADINGCAT_FUTU_PORT=33333",
                "TRADINGCAT_POSTGRES_ENABLED=true",
                "TRADINGCAT_POSTGRES_DSN=postgresql:///tradingcat_dotenv",
                "TRADINGCAT_DUCKDB_ENABLED=true",
                "TRADINGCAT_DUCKDB_PATH=runtime-data/research.duckdb",
                "TRADINGCAT_PARQUET_DIR=runtime-data/parquet",
                "TRADINGCAT_SCHEDULER_BACKEND=apscheduler",
                "TRADINGCAT_SCHEDULER_AUTOSTART=true",
                "TRADINGCAT_SMOKE_SYMBOLS=0700, AAPL",
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env()

    assert config.portfolio_value == 750000
    assert config.base_currency == "HKD"
    assert config.data_dir == Path("runtime-data")
    assert config.futu.enabled is True
    assert config.futu.port == 33333
    assert config.postgres.enabled is True
    assert config.postgres.dsn == "postgresql:///tradingcat_dotenv"
    assert config.duckdb.enabled is True
    assert config.duckdb.path == Path("runtime-data/research.duckdb")
    assert config.duckdb.parquet_dir == Path("runtime-data/parquet")
    assert config.scheduler.backend == "apscheduler"
    assert config.scheduler.autostart is True
    assert config.smoke_symbols == ["0700", "AAPL"]
