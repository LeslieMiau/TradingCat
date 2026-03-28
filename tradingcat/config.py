import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    cn_trade_market: str = "CN"
    probe_timeout_seconds: float = 0.2
    adapter_init_timeout_seconds: float = 3.0
    unlock_trade_password: str | None = None

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value <= 0 or value > 65535:
            raise ValueError("futu.port must be between 1 and 65535")
        return value

    @field_validator("probe_timeout_seconds", "adapter_init_timeout_seconds")
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout values must be positive")
        return value

    @property
    def adapter_init_timeout(self) -> float:
        return self.adapter_init_timeout_seconds

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "FutuConfig":
        env_values = dotenv_values or {}
        enabled_raw = _getenv("TRADINGCAT_FUTU_ENABLED", "false", env_values).strip().lower()
        adapter_timeout = _getenv(
            "TRADINGCAT_FUTU_ADAPTER_INIT_TIMEOUT_SECONDS",
            _getenv("TRADINGCAT_FUTU_ADAPTER_INIT_TIMEOUT", "3.0", env_values),
            env_values,
        )
        return cls(
            enabled=enabled_raw in {"1", "true", "yes", "on"},
            host=_getenv("TRADINGCAT_FUTU_HOST", "127.0.0.1", env_values),
            port=int(_getenv("TRADINGCAT_FUTU_PORT", "11111", env_values)),
            environment=_getenv("TRADINGCAT_FUTU_ENVIRONMENT", "SIMULATE", env_values).upper(),
            hk_trade_market=_getenv("TRADINGCAT_FUTU_HK_TRADE_MARKET", "HK", env_values).upper(),
            us_trade_market=_getenv("TRADINGCAT_FUTU_US_TRADE_MARKET", "US", env_values).upper(),
            cn_trade_market=_getenv("TRADINGCAT_FUTU_CN_TRADE_MARKET", "CN", env_values).upper(),
            probe_timeout_seconds=float(_getenv("TRADINGCAT_FUTU_PROBE_TIMEOUT_SECONDS", "0.2", env_values)),
            adapter_init_timeout_seconds=float(adapter_timeout),
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
    fallback_price_us_etf: float = 600.0
    fallback_price_us_stock: float = 300.0
    fallback_price_hk: float = 600.0
    fallback_price_cn_etf: float = 5.0
    fallback_price_cn_stock: float = 20.0

    @field_validator(
        "max_single_stock_weight",
        "max_single_etf_weight",
        "max_daily_option_premium_risk",
        "max_total_option_risk",
        "daily_stop_loss",
        "weekly_drawdown_limit",
        "half_risk_drawdown",
        "no_new_risk_drawdown",
        "fallback_price_us_etf",
        "fallback_price_us_stock",
        "fallback_price_hk",
        "fallback_price_cn_etf",
        "fallback_price_cn_stock",
    )
    @classmethod
    def validate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("risk values must be non-negative")
        return value


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
    approval_expiry_minutes: int = 60
    seed_demo_data: bool = False
    manual_order_requires_approval: bool = True
    algo_twap_slices: int = 5
    algo_ladder_levels: int = 5
    algo_ladder_price_start: float = 100.0
    algo_ladder_price_end: float = 90.0
    alpha_radar_symbols: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMD"])
    demo_history_days: int = 90
    demo_cash_ratio: float = 0.1
    demo_min_daily_return: float = -0.02
    demo_max_daily_return: float = 0.025
    demo_drawdown_ceiling: float = 0.04
    demo_weekly_pnl_multiplier: float = 3.0
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    duckdb: DuckDbConfig = Field(default_factory=DuckDbConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    futu: FutuConfig = Field(default_factory=FutuConfig)
    yfinance: YFinanceConfig = Field(default_factory=YFinanceConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    @field_validator("portfolio_value")
    @classmethod
    def positive_portfolio(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("portfolio_value must be positive")
        return value

    @field_validator("approval_expiry_minutes", "algo_twap_slices", "algo_ladder_levels", "demo_history_days")
    @classmethod
    def positive_integers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("configuration values must be positive")
        return value

    @field_validator(
        "algo_ladder_price_start",
        "algo_ladder_price_end",
        "demo_cash_ratio",
        "demo_min_daily_return",
        "demo_max_daily_return",
        "demo_drawdown_ceiling",
        "demo_weekly_pnl_multiplier",
    )
    @classmethod
    def validate_numeric_fields(cls, value: float) -> float:
        return value

    @classmethod
    def from_env(cls) -> "AppConfig":
        dotenv_values = _load_dotenv_values()
        smoke_symbols_raw = _getenv("TRADINGCAT_SMOKE_SYMBOLS", "", dotenv_values)
        alpha_radar_symbols_raw = _getenv(
            "TRADINGCAT_ALPHA_RADAR_SYMBOLS",
            "SPY,QQQ,NVDA,TSLA,AAPL,MSFT,AMD",
            dotenv_values,
        )
        seed_demo_data_raw = _getenv("TRADINGCAT_SEED_DEMO_DATA", "false", dotenv_values).strip().lower()
        manual_order_requires_approval_raw = _getenv(
            "TRADINGCAT_MANUAL_ORDER_REQUIRES_APPROVAL",
            "true",
            dotenv_values,
        ).strip().lower()
        return cls(
            portfolio_value=float(_getenv("TRADINGCAT_PORTFOLIO_VALUE", "1000000", dotenv_values)),
            base_currency=_getenv("TRADINGCAT_BASE_CURRENCY", "CNY", dotenv_values).upper(),
            data_dir=Path(_getenv("TRADINGCAT_DATA_DIR", "data", dotenv_values)),
            smoke_symbols=[item.strip() for item in smoke_symbols_raw.split(",") if item.strip()],
            approval_expiry_minutes=int(_getenv("TRADINGCAT_APPROVAL_EXPIRY_MINUTES", "60", dotenv_values)),
            seed_demo_data=seed_demo_data_raw in {"1", "true", "yes", "on"},
            manual_order_requires_approval=manual_order_requires_approval_raw in {"1", "true", "yes", "on"},
            algo_twap_slices=int(_getenv("TRADINGCAT_ALGO_TWAP_SLICES", "5", dotenv_values)),
            algo_ladder_levels=int(_getenv("TRADINGCAT_ALGO_LADDER_LEVELS", "5", dotenv_values)),
            algo_ladder_price_start=float(_getenv("TRADINGCAT_ALGO_LADDER_PRICE_START", "100.0", dotenv_values)),
            algo_ladder_price_end=float(_getenv("TRADINGCAT_ALGO_LADDER_PRICE_END", "90.0", dotenv_values)),
            alpha_radar_symbols=[item.strip().upper() for item in alpha_radar_symbols_raw.split(",") if item.strip()],
            demo_history_days=int(_getenv("TRADINGCAT_DEMO_HISTORY_DAYS", "90", dotenv_values)),
            demo_cash_ratio=float(_getenv("TRADINGCAT_DEMO_CASH_RATIO", "0.1", dotenv_values)),
            demo_min_daily_return=float(_getenv("TRADINGCAT_DEMO_MIN_DAILY_RETURN", "-0.02", dotenv_values)),
            demo_max_daily_return=float(_getenv("TRADINGCAT_DEMO_MAX_DAILY_RETURN", "0.025", dotenv_values)),
            demo_drawdown_ceiling=float(_getenv("TRADINGCAT_DEMO_DRAWDOWN_CEILING", "0.04", dotenv_values)),
            demo_weekly_pnl_multiplier=float(_getenv("TRADINGCAT_DEMO_WEEKLY_PNL_MULTIPLIER", "3.0", dotenv_values)),
            postgres=PostgresConfig.from_env(dotenv_values),
            duckdb=DuckDbConfig.from_env(dotenv_values),
            scheduler=SchedulerConfig.from_env(dotenv_values),
            futu=FutuConfig.from_env(dotenv_values),
            yfinance=YFinanceConfig.from_env(dotenv_values),
            risk=RiskConfig(),
        )
