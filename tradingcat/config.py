import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


def _csv_values(raw: str, *, upper: bool = False) -> list[str]:
    values = []
    for item in raw.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        values.append(cleaned.upper() if upper else cleaned)
    return values


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
        enabled_raw = _getenv("TRADINGCAT_YFINANCE_ENABLED", "true", env_values).strip().lower()
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


class MarketAwarenessConfig(BaseModel):
    short_trend_window: int = 20
    medium_trend_window: int = 50
    long_trend_window: int = 200
    us_benchmark_symbols: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "VTI"])
    hk_benchmark_symbols: list[str] = Field(default_factory=lambda: ["0700", "9988"])
    cn_benchmark_symbols: list[str] = Field(default_factory=lambda: ["510300", "159915"])
    cn_observation_index_symbols: list[str] = Field(default_factory=lambda: ["SH000001", "SZ399001", "SZ399006"])
    cross_asset_reference_symbols: list[str] = Field(default_factory=lambda: ["TLT", "IEF", "GLD", "GSG"])
    breadth_support_ratio: float = 0.55
    breadth_caution_ratio: float = 0.45
    drawdown_caution_threshold: float = -0.05
    drawdown_risk_off_threshold: float = -0.10
    volatility_caution_threshold: float = 0.02
    volatility_stress_threshold: float = 0.03
    momentum_support_threshold: float = 0.03
    momentum_warning_threshold: float = -0.03
    trend_weight: float = 0.35
    breadth_weight: float = 0.20
    momentum_weight: float = 0.20
    drawdown_weight: float = 0.10
    volatility_weight: float = 0.10
    overlay_weight: float = 0.05
    news_cache_ttl_seconds: int = 900
    news_timeout_seconds: float = 3.0
    participate_probability_threshold: float = 0.65
    selective_probability_threshold: float = 0.55
    participate_odds_threshold: float = 1.5
    selective_odds_threshold: float = 1.2

    @field_validator("short_trend_window", "medium_trend_window", "long_trend_window")
    @classmethod
    def validate_positive_windows(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("market awareness windows must be positive")
        return value

    @field_validator(
        "breadth_support_ratio",
        "breadth_caution_ratio",
        "volatility_caution_threshold",
        "volatility_stress_threshold",
        "trend_weight",
        "breadth_weight",
        "momentum_weight",
        "drawdown_weight",
        "volatility_weight",
        "overlay_weight",
    )
    @classmethod
    def validate_zero_to_one(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("market awareness ratio/weight values must be between 0 and 1")
        return value

    @field_validator("participate_probability_threshold", "selective_probability_threshold")
    @classmethod
    def validate_probability_thresholds(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("market awareness participation probabilities must be between 0 and 1")
        return value

    @field_validator("participate_odds_threshold", "selective_odds_threshold")
    @classmethod
    def validate_positive_odds_thresholds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("market awareness odds thresholds must be positive")
        return value

    @field_validator("news_cache_ttl_seconds")
    @classmethod
    def validate_positive_cache_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("market awareness news cache ttl must be positive")
        return value

    @field_validator("news_timeout_seconds")
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("market awareness news timeout must be positive")
        return value

    @field_validator("drawdown_caution_threshold", "drawdown_risk_off_threshold", "momentum_warning_threshold")
    @classmethod
    def validate_non_positive_threshold(cls, value: float) -> float:
        if value > 0:
            raise ValueError("market awareness drawdown and warning thresholds must be non-positive")
        return value

    @field_validator("momentum_support_threshold")
    @classmethod
    def validate_non_negative_threshold(cls, value: float) -> float:
        if value < 0:
            raise ValueError("market awareness support thresholds must be non-negative")
        return value

    @field_validator(
        "us_benchmark_symbols",
        "hk_benchmark_symbols",
        "cn_benchmark_symbols",
        "cn_observation_index_symbols",
        "cross_asset_reference_symbols",
    )
    @classmethod
    def validate_non_empty_symbol_lists(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value if item.strip()]
        if not normalized:
            raise ValueError("market awareness symbol lists must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "MarketAwarenessConfig":
        if not (self.short_trend_window < self.medium_trend_window < self.long_trend_window):
            raise ValueError("market awareness windows must increase from short to long")
        if self.breadth_support_ratio <= self.breadth_caution_ratio:
            raise ValueError("breadth support ratio must be above the caution ratio")
        if self.drawdown_caution_threshold <= self.drawdown_risk_off_threshold:
            raise ValueError("drawdown caution threshold must be less severe than risk-off threshold")
        if self.volatility_caution_threshold >= self.volatility_stress_threshold:
            raise ValueError("volatility caution threshold must be below the stress threshold")
        if self.momentum_support_threshold <= self.momentum_warning_threshold:
            raise ValueError("momentum support threshold must be above the warning threshold")
        if self.selective_probability_threshold > self.participate_probability_threshold:
            raise ValueError("selective probability threshold must not exceed participate probability threshold")
        if self.selective_odds_threshold > self.participate_odds_threshold:
            raise ValueError("selective odds threshold must not exceed participate odds threshold")
        return self

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "MarketAwarenessConfig":
        env_values = dotenv_values or {}
        return cls(
            short_trend_window=int(_getenv("TRADINGCAT_MARKET_AWARENESS_SHORT_TREND_WINDOW", "20", env_values)),
            medium_trend_window=int(_getenv("TRADINGCAT_MARKET_AWARENESS_MEDIUM_TREND_WINDOW", "50", env_values)),
            long_trend_window=int(_getenv("TRADINGCAT_MARKET_AWARENESS_LONG_TREND_WINDOW", "200", env_values)),
            us_benchmark_symbols=_csv_values(
                _getenv("TRADINGCAT_MARKET_AWARENESS_US_BENCHMARKS", "SPY,QQQ,VTI", env_values),
                upper=True,
            ),
            hk_benchmark_symbols=_csv_values(
                _getenv("TRADINGCAT_MARKET_AWARENESS_HK_BENCHMARKS", "0700,9988", env_values),
                upper=True,
            ),
            cn_benchmark_symbols=_csv_values(
                _getenv("TRADINGCAT_MARKET_AWARENESS_CN_BENCHMARKS", "510300,159915", env_values),
                upper=True,
            ),
            cn_observation_index_symbols=_csv_values(
                _getenv("TRADINGCAT_MARKET_AWARENESS_CN_OBSERVATION_INDICES", "SH000001,SZ399001,SZ399006", env_values),
                upper=True,
            ),
            cross_asset_reference_symbols=_csv_values(
                _getenv("TRADINGCAT_MARKET_AWARENESS_CROSS_ASSET_REFERENCES", "TLT,IEF,GLD,GSG", env_values),
                upper=True,
            ),
            breadth_support_ratio=float(_getenv("TRADINGCAT_MARKET_AWARENESS_BREADTH_SUPPORT_RATIO", "0.55", env_values)),
            breadth_caution_ratio=float(_getenv("TRADINGCAT_MARKET_AWARENESS_BREADTH_CAUTION_RATIO", "0.45", env_values)),
            drawdown_caution_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_DRAWDOWN_CAUTION_THRESHOLD", "-0.05", env_values)
            ),
            drawdown_risk_off_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_DRAWDOWN_RISK_OFF_THRESHOLD", "-0.10", env_values)
            ),
            volatility_caution_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_VOLATILITY_CAUTION_THRESHOLD", "0.02", env_values)
            ),
            volatility_stress_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_VOLATILITY_STRESS_THRESHOLD", "0.03", env_values)
            ),
            momentum_support_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_MOMENTUM_SUPPORT_THRESHOLD", "0.03", env_values)
            ),
            momentum_warning_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_MOMENTUM_WARNING_THRESHOLD", "-0.03", env_values)
            ),
            trend_weight=float(_getenv("TRADINGCAT_MARKET_AWARENESS_TREND_WEIGHT", "0.35", env_values)),
            breadth_weight=float(_getenv("TRADINGCAT_MARKET_AWARENESS_BREADTH_WEIGHT", "0.20", env_values)),
            momentum_weight=float(_getenv("TRADINGCAT_MARKET_AWARENESS_MOMENTUM_WEIGHT", "0.20", env_values)),
            drawdown_weight=float(_getenv("TRADINGCAT_MARKET_AWARENESS_DRAWDOWN_WEIGHT", "0.10", env_values)),
            volatility_weight=float(_getenv("TRADINGCAT_MARKET_AWARENESS_VOLATILITY_WEIGHT", "0.10", env_values)),
            overlay_weight=float(_getenv("TRADINGCAT_MARKET_AWARENESS_OVERLAY_WEIGHT", "0.05", env_values)),
            news_cache_ttl_seconds=int(_getenv("TRADINGCAT_MARKET_AWARENESS_NEWS_CACHE_TTL_SECONDS", "900", env_values)),
            news_timeout_seconds=float(_getenv("TRADINGCAT_MARKET_AWARENESS_NEWS_TIMEOUT_SECONDS", "3.0", env_values)),
            participate_probability_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_PARTICIPATE_PROBABILITY_THRESHOLD", "0.65", env_values)
            ),
            selective_probability_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_SELECTIVE_PROBABILITY_THRESHOLD", "0.55", env_values)
            ),
            participate_odds_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_PARTICIPATE_ODDS_THRESHOLD", "1.5", env_values)
            ),
            selective_odds_threshold=float(
                _getenv("TRADINGCAT_MARKET_AWARENESS_SELECTIVE_ODDS_THRESHOLD", "1.2", env_values)
            ),
        )


class MarketSentimentConfig(BaseModel):
    """Market sentiment ingestion + scoring knobs.

    The sentiment layer lives alongside `MarketAwarenessConfig` but is fully
    optional: setting `enabled=False` should make `MarketSentimentService`
    return an empty snapshot without hitting any network.

    Round 1 wires US (VIX + VXN + CNN F&G). HK/CN defaults are defined here so
    future rounds don't need a config migration.
    """

    enabled: bool = True
    cache_ttl_seconds: int = 600
    negative_cache_ttl_seconds: int = 60
    http_timeout_seconds: float = 5.0
    http_retries: int = 2
    http_backoff_seconds: float = 0.5
    http_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    # US
    us_vix_symbol: str = "^VIX"
    us_vxn_symbol: str = "^VXN"
    vol_stale_after_days: int = 5
    cnn_enabled: bool = True
    cnn_fear_greed_url: str = (
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    )

    # HK (Round 3)
    hk_hsiv_symbol: str = "^HSIV"
    hk_fallback_symbols: list[str] = Field(default_factory=lambda: ["0700", "2800"])
    hk_southbound_enabled: bool = False

    # CN (Round 2)
    cn_backend: Literal["eastmoney_http", "akshare", "disabled"] = "eastmoney_http"
    cn_turnover_universe_size: int = 500
    cn_northbound_window_days: int = 5

    # Composite weights — must sum to 1 within tolerance.
    composite_weight_us: float = 0.45
    composite_weight_cn: float = 0.30
    composite_weight_hk: float = 0.25

    # Risk switch decision thresholds on composite score (range [-1, +1]).
    risk_switch_on_threshold: float = 0.30
    risk_switch_off_threshold: float = -0.30

    @field_validator("cache_ttl_seconds", "negative_cache_ttl_seconds", "http_retries", "vol_stale_after_days")
    @classmethod
    def _non_negative_ints(cls, value: int) -> int:
        if value < 0:
            raise ValueError("market sentiment int config values must be non-negative")
        return value

    @field_validator("http_timeout_seconds", "http_backoff_seconds")
    @classmethod
    def _non_negative_floats(cls, value: float) -> float:
        if value < 0:
            raise ValueError("market sentiment float config values must be non-negative")
        return value

    @field_validator("composite_weight_us", "composite_weight_cn", "composite_weight_hk")
    @classmethod
    def _zero_to_one_weight(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("composite weight must be between 0 and 1 inclusive")
        return value

    @field_validator("risk_switch_on_threshold", "risk_switch_off_threshold")
    @classmethod
    def _threshold_in_range(cls, value: float) -> float:
        if value < -1 or value > 1:
            raise ValueError("risk switch thresholds must be within [-1, +1]")
        return value

    @field_validator("cn_backend")
    @classmethod
    def _normalise_cn_backend(cls, value: str) -> str:
        normalised = str(value).strip().lower()
        if normalised not in {"eastmoney_http", "akshare", "disabled"}:
            raise ValueError(
                "cn_backend must be one of: eastmoney_http, akshare, disabled"
            )
        return normalised

    @model_validator(mode="after")
    def _validate_weights_and_thresholds(self) -> "MarketSentimentConfig":
        total = self.composite_weight_us + self.composite_weight_cn + self.composite_weight_hk
        if not 0.99 <= total <= 1.01:
            raise ValueError(
                f"composite weights must sum to ~1.0 (got {total:.4f})"
            )
        if self.risk_switch_on_threshold <= self.risk_switch_off_threshold:
            raise ValueError(
                "risk_switch_on_threshold must be greater than risk_switch_off_threshold"
            )
        return self

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str] | None = None) -> "MarketSentimentConfig":
        env_values = dotenv_values or {}

        def _bool(key: str, default: str) -> bool:
            return _getenv(key, default, env_values).strip().lower() in {"1", "true", "yes", "on"}

        hk_fallback_raw = _getenv(
            "TRADINGCAT_MARKET_SENTIMENT_HK_FALLBACK_SYMBOLS",
            "0700,2800",
            env_values,
        )
        hk_fallback = _csv_values(hk_fallback_raw) or ["0700", "2800"]

        return cls(
            enabled=_bool("TRADINGCAT_MARKET_SENTIMENT_ENABLED", "true"),
            cache_ttl_seconds=int(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_CACHE_TTL_SECONDS", "600", env_values)
            ),
            negative_cache_ttl_seconds=int(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_NEGATIVE_CACHE_TTL_SECONDS", "60", env_values)
            ),
            http_timeout_seconds=float(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_HTTP_TIMEOUT_SECONDS", "5.0", env_values)
            ),
            http_retries=int(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_HTTP_RETRIES", "2", env_values)
            ),
            http_backoff_seconds=float(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_HTTP_BACKOFF_SECONDS", "0.5", env_values)
            ),
            us_vix_symbol=_getenv(
                "TRADINGCAT_MARKET_SENTIMENT_US_VIX_SYMBOL", "^VIX", env_values
            ).strip(),
            us_vxn_symbol=_getenv(
                "TRADINGCAT_MARKET_SENTIMENT_US_VXN_SYMBOL", "^VXN", env_values
            ).strip(),
            vol_stale_after_days=int(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_VOL_STALE_AFTER_DAYS", "5", env_values)
            ),
            cnn_enabled=_bool("TRADINGCAT_MARKET_SENTIMENT_CNN_ENABLED", "true"),
            cnn_fear_greed_url=_getenv(
                "TRADINGCAT_MARKET_SENTIMENT_CNN_URL",
                "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                env_values,
            ),
            hk_hsiv_symbol=_getenv(
                "TRADINGCAT_MARKET_SENTIMENT_HK_HSIV_SYMBOL", "^HSIV", env_values
            ).strip(),
            hk_fallback_symbols=hk_fallback,
            hk_southbound_enabled=_bool(
                "TRADINGCAT_MARKET_SENTIMENT_HK_SOUTHBOUND_ENABLED", "false"
            ),
            cn_backend=_getenv(
                "TRADINGCAT_MARKET_SENTIMENT_CN_BACKEND", "eastmoney_http", env_values
            ).strip().lower(),
            cn_turnover_universe_size=int(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_CN_TURNOVER_UNIVERSE_SIZE", "500", env_values)
            ),
            cn_northbound_window_days=int(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_CN_NORTHBOUND_WINDOW_DAYS", "5", env_values)
            ),
            composite_weight_us=float(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_COMPOSITE_WEIGHT_US", "0.45", env_values)
            ),
            composite_weight_cn=float(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_COMPOSITE_WEIGHT_CN", "0.30", env_values)
            ),
            composite_weight_hk=float(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_COMPOSITE_WEIGHT_HK", "0.25", env_values)
            ),
            risk_switch_on_threshold=float(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_RISK_SWITCH_ON_THRESHOLD", "0.30", env_values)
            ),
            risk_switch_off_threshold=float(
                _getenv("TRADINGCAT_MARKET_SENTIMENT_RISK_SWITCH_OFF_THRESHOLD", "-0.30", env_values)
            ),
        )


class NotifierConfig(BaseModel):
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: list[str] = Field(default_factory=list)
    min_severity: str = "error"
    dispatch_cooldown_seconds: int = 900

    @classmethod
    def from_env(cls, dotenv_values: dict[str, str]) -> "NotifierConfig":
        to_raw = _getenv("TRADINGCAT_ALERT_EMAIL_TO", "", dotenv_values)
        return cls(
            telegram_bot_token=_getenv("TRADINGCAT_ALERT_TELEGRAM_BOT_TOKEN", "", dotenv_values),
            telegram_chat_id=_getenv("TRADINGCAT_ALERT_TELEGRAM_CHAT_ID", "", dotenv_values),
            smtp_host=_getenv("TRADINGCAT_ALERT_SMTP_HOST", "", dotenv_values),
            smtp_port=int(_getenv("TRADINGCAT_ALERT_SMTP_PORT", "587", dotenv_values)),
            smtp_username=_getenv("TRADINGCAT_ALERT_SMTP_USERNAME", "", dotenv_values),
            smtp_password=_getenv("TRADINGCAT_ALERT_SMTP_PASSWORD", "", dotenv_values),
            email_from=_getenv("TRADINGCAT_ALERT_EMAIL_FROM", "", dotenv_values),
            email_to=[addr.strip() for addr in to_raw.split(",") if addr.strip()],
            min_severity=_getenv("TRADINGCAT_ALERT_MIN_SEVERITY", "error", dotenv_values).strip().lower(),
            dispatch_cooldown_seconds=int(_getenv("TRADINGCAT_ALERT_COOLDOWN_SECONDS", "900", dotenv_values)),
        )


class AppConfig(BaseModel):
    portfolio_value: float = 1_000_000.0
    base_currency: str = "CNY"
    data_dir: Path = Path("data")
    smoke_symbols: list[str] = Field(default_factory=list)
    approval_expiry_minutes: int = 60
    intraday_risk_tick_seconds: int = 60
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
    market_awareness: MarketAwarenessConfig = Field(default_factory=MarketAwarenessConfig)
    market_sentiment: MarketSentimentConfig = Field(default_factory=MarketSentimentConfig)
    notifier: NotifierConfig = Field(default_factory=NotifierConfig)

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
            intraday_risk_tick_seconds=int(_getenv("TRADINGCAT_INTRADAY_RISK_TICK_SECONDS", "60", dotenv_values)),
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
            market_awareness=MarketAwarenessConfig.from_env(dotenv_values),
            market_sentiment=MarketSentimentConfig.from_env(dotenv_values),
            notifier=NotifierConfig.from_env(dotenv_values),
        )
