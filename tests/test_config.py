from pathlib import Path

from tradingcat.config import AppConfig


def test_app_config_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGCAT_PORTFOLIO_VALUE", "250000")
    monkeypatch.setenv("TRADINGCAT_BASE_CURRENCY", "usd")
    monkeypatch.setenv("TRADINGCAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADINGCAT_FUTU_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_FUTU_ENVIRONMENT", "real")
    monkeypatch.setenv("TRADINGCAT_FUTU_PORT", "22222")
    monkeypatch.setenv("TRADINGCAT_BAOSTOCK_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_BAOSTOCK_ADJUSTFLAG", "3")
    monkeypatch.setenv("TRADINGCAT_POSTGRES_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_POSTGRES_DSN", "postgresql:///tradingcat_test")
    monkeypatch.setenv("TRADINGCAT_DUCKDB_ENABLED", "true")
    monkeypatch.setenv("TRADINGCAT_DUCKDB_PATH", str(tmp_path / "research.duckdb"))
    monkeypatch.setenv("TRADINGCAT_PARQUET_DIR", str(tmp_path / "parquet"))
    monkeypatch.setenv("TRADINGCAT_SCHEDULER_BACKEND", "lightweight")
    monkeypatch.setenv("TRADINGCAT_SCHEDULER_AUTOSTART", "false")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_US_BENCHMARKS", "SPY, DIA")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_CROSS_ASSET_REFERENCES", "TLT, GLD")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_SHORT_TREND_WINDOW", "15")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_BREADTH_SUPPORT_RATIO", "0.6")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_VOLATILITY_STRESS_THRESHOLD", "0.04")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_OVERLAY_WEIGHT", "0.08")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_CN_OBSERVATION_INDICES", "SH000001,SZ399001,SZ399006")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_NEWS_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_NEWS_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_PARTICIPATE_PROBABILITY_THRESHOLD", "0.7")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_SELECTIVE_PROBABILITY_THRESHOLD", "0.58")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_PARTICIPATE_ODDS_THRESHOLD", "1.6")
    monkeypatch.setenv("TRADINGCAT_MARKET_AWARENESS_SELECTIVE_ODDS_THRESHOLD", "1.25")

    config = AppConfig.from_env()

    assert config.portfolio_value == 250000
    assert config.base_currency == "USD"
    assert config.data_dir == tmp_path
    assert config.futu.enabled is True
    assert config.futu.environment == "REAL"
    assert config.futu.port == 22222
    assert config.baostock.enabled is True
    assert config.baostock.adjustflag == "3"
    assert config.postgres.enabled is True
    assert config.postgres.dsn == "postgresql:///tradingcat_test"
    assert config.duckdb.enabled is True
    assert config.duckdb.path == tmp_path / "research.duckdb"
    assert config.duckdb.parquet_dir == tmp_path / "parquet"
    assert config.scheduler.backend == "lightweight"
    assert config.scheduler.autostart is False
    assert config.market_awareness.us_benchmark_symbols == ["SPY", "DIA"]
    assert config.market_awareness.cross_asset_reference_symbols == ["TLT", "GLD"]
    assert config.market_awareness.short_trend_window == 15
    assert config.market_awareness.breadth_support_ratio == 0.6
    assert config.market_awareness.volatility_stress_threshold == 0.04
    assert config.market_awareness.overlay_weight == 0.08
    assert config.market_awareness.cn_observation_index_symbols == ["SH000001", "SZ399001", "SZ399006"]
    assert config.market_awareness.news_cache_ttl_seconds == 300
    assert config.market_awareness.news_timeout_seconds == 4.5
    assert config.market_awareness.participate_probability_threshold == 0.7
    assert config.market_awareness.selective_probability_threshold == 0.58
    assert config.market_awareness.participate_odds_threshold == 1.6
    assert config.market_awareness.selective_odds_threshold == 1.25


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


def test_app_config_market_awareness_defaults():
    config = AppConfig()

    assert config.market_awareness.short_trend_window == 20
    assert config.market_awareness.medium_trend_window == 50
    assert config.market_awareness.long_trend_window == 200
    assert config.market_awareness.us_benchmark_symbols == ["SPY", "QQQ", "VTI"]
    assert config.market_awareness.hk_benchmark_symbols == ["0700", "9988"]
    assert config.market_awareness.cn_benchmark_symbols == ["510300", "159915"]
    assert config.market_awareness.cn_observation_index_symbols == ["SH000001", "SZ399001", "SZ399006"]
    assert config.market_awareness.cross_asset_reference_symbols == ["TLT", "IEF", "GLD", "GSG"]
    assert config.market_awareness.breadth_support_ratio > config.market_awareness.breadth_caution_ratio
    assert config.market_awareness.news_cache_ttl_seconds == 900
    assert config.market_awareness.news_timeout_seconds == 3.0
    assert config.market_awareness.participate_probability_threshold == 0.65
    assert config.market_awareness.selective_probability_threshold == 0.55
    assert config.market_awareness.participate_odds_threshold == 1.5
    assert config.market_awareness.selective_odds_threshold == 1.2
