import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _candidate_env_files() -> list[Path]:
    cwd_env = Path.cwd() / ".env"
    package_env = Path(__file__).resolve().parents[1] / ".env"
    if cwd_env == package_env:
        return [cwd_env]
    return [cwd_env, package_env]


def _load_dotenv_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for env_file in _candidate_env_files():
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in values:
                continue
            values[key] = value.strip().strip("'").strip('"')
    return values


def _getenv(name: str, default: str, dotenv_values: dict[str, str]) -> str:
    return os.getenv(name, dotenv_values.get(name, default))


class FutuConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 11111
    environment: str = "SIMULATE"
    hk_trade_market: str = "HK"
    us_trade_market: str = "US"
    unlock_trade_password: str | None = None

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "FutuConfig":
        env_values = dotenv_values or {}
        enabled_raw = _getenv("TRADINGCAT_FUTU_ENABLED", "false", env_values).strip().lower()
        return cls(
            enabled=enabled_raw in {"1", "true", "yes", "on"},
            host=_getenv("TRADINGCAT_FUTU_HOST", "127.0.0.1", env_values),
            port=int(_getenv("TRADINGCAT_FUTU_PORT", "11111", env_values)),
            environment=_getenv("TRADINGCAT_FUTU_ENVIRONMENT", "SIMULATE", env_values).upper(),
            hk_trade_market=_getenv("TRADINGCAT_FUTU_HK_TRADE_MARKET", "HK", env_values).upper(),
            us_trade_market=_getenv("TRADINGCAT_FUTU_US_TRADE_MARKET", "US", env_values).upper(),
            unlock_trade_password=os.getenv(
                "TRADINGCAT_FUTU_UNLOCK_TRADE_PASSWORD",
                env_values.get("TRADINGCAT_FUTU_UNLOCK_TRADE_PASSWORD"),
            ),
        )


class RiskConfig(BaseModel):
    max_single_stock_weight: float = 0.08
    max_single_etf_weight: float = 0.20
    max_daily_option_premium_risk: float = 0.02
    max_total_option_risk: float = 0.05
    daily_stop_loss: float = 0.02
    weekly_drawdown_limit: float = 0.04
    half_risk_drawdown: float = 0.10
    no_new_risk_drawdown: float = 0.15


class PostgresConfig(BaseModel):
    enabled: bool = False
    dsn: str = "postgresql:///tradingcat"

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "PostgresConfig":
        env_values = dotenv_values or {}
        enabled_raw = _getenv("TRADINGCAT_POSTGRES_ENABLED", "false", env_values).strip().lower()
        return cls(
            enabled=enabled_raw in {"1", "true", "yes", "on"},
            dsn=_getenv("TRADINGCAT_POSTGRES_DSN", "postgresql:///tradingcat", env_values),
        )


class YFinanceConfig(BaseModel):
    enabled: bool = False

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "YFinanceConfig":
        env_values = dotenv_values or {}
        enabled_raw = _getenv("TRADINGCAT_YFINANCE_ENABLED", "false", env_values).strip().lower()
        return cls(enabled=enabled_raw in {"1", "true", "yes", "on"})


class DuckDbConfig(BaseModel):
    enabled: bool = False
    path: Path = Path("data") / "research.duckdb"
    parquet_dir: Path = Path("data") / "parquet"

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "DuckDbConfig":
        env_values = dotenv_values or {}
        enabled_raw = _getenv("TRADINGCAT_DUCKDB_ENABLED", "false", env_values).strip().lower()
        return cls(
            enabled=enabled_raw in {"1", "true", "yes", "on"},
            path=Path(_getenv("TRADINGCAT_DUCKDB_PATH", "data/research.duckdb", env_values)),
            parquet_dir=Path(_getenv("TRADINGCAT_PARQUET_DIR", "data/parquet", env_values)),
        )


class SchedulerConfig(BaseModel):
    backend: Literal["lightweight", "apscheduler"] = "apscheduler"
    autostart: bool = True

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "SchedulerConfig":
        env_values = dotenv_values or {}
        autostart_raw = _getenv("TRADINGCAT_SCHEDULER_AUTOSTART", "true", env_values).strip().lower()
        return cls(
            backend=_getenv("TRADINGCAT_SCHEDULER_BACKEND", "apscheduler", env_values).strip().lower(),
            autostart=autostart_raw in {"1", "true", "yes", "on"},
        )


class AppConfig(BaseModel):
    portfolio_value: float = 1_000_000.0
    base_currency: str = "CNY"
    data_dir: Path = Path("data")
    smoke_symbols: list[str] = Field(default_factory=list)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    duckdb: DuckDbConfig = Field(default_factory=DuckDbConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    futu: FutuConfig = Field(default_factory=FutuConfig)
    yfinance: YFinanceConfig = Field(default_factory=YFinanceConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        dotenv_values = _load_dotenv_values()
        smoke_symbols_raw = _getenv("TRADINGCAT_SMOKE_SYMBOLS", "", dotenv_values)
        return cls(
            portfolio_value=float(_getenv("TRADINGCAT_PORTFOLIO_VALUE", "1000000", dotenv_values)),
            base_currency=_getenv("TRADINGCAT_BASE_CURRENCY", "CNY", dotenv_values).upper(),
            data_dir=Path(_getenv("TRADINGCAT_DATA_DIR", "data", dotenv_values)),
            smoke_symbols=[item.strip() for item in smoke_symbols_raw.split(",") if item.strip()],
            postgres=PostgresConfig.from_env(dotenv_values),
            duckdb=DuckDbConfig.from_env(dotenv_values),
            scheduler=SchedulerConfig.from_env(dotenv_values),
            futu=FutuConfig.from_env(dotenv_values),
            yfinance=YFinanceConfig.from_env(dotenv_values),
        )
