from __future__ import annotations

import importlib.util
import os
import sys

from tradingcat.config import AppConfig
from tradingcat.repositories.duckdb_store import DuckDbStoreUnavailable, _load_duckdb
from tradingcat.repositories.postgres_store import PostgresStoreUnavailable, _load_psycopg
from tradingcat.services.scheduler import SchedulerBackendUnavailable, _load_apscheduler


def _redact_dsn(dsn: str) -> str:
    if "://" not in dsn:
        return dsn
    scheme, remainder = dsn.split("://", 1)
    if "@" not in remainder or ":" not in remainder.split("@", 1)[0]:
        return dsn
    credentials, suffix = remainder.split("@", 1)
    username = credentials.split(":", 1)[0]
    return f"{scheme}://{username}:***@{suffix}"


def build_startup_preflight(config: AppConfig) -> dict[str, object]:
    checks: list[dict[str, str | bool]] = []
    recommendations: list[str] = []

    checks.append(
        {
            "name": "python_version",
            "ok": sys.version_info >= (3, 12),
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }
    )

    data_dir_ok = True
    data_dir_detail = str(config.data_dir)
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        data_dir_ok = False
        data_dir_detail = str(exc)
    checks.append({"name": "data_dir", "ok": data_dir_ok, "detail": data_dir_detail})

    env_file_present = os.path.exists(".env")
    checks.append(
        {
            "name": "env_file",
            "ok": env_file_present,
            "detail": ".env present" if env_file_present else ".env not found in current working directory",
        }
    )

    futu_enabled = config.futu.enabled
    postgres_enabled = config.postgres.enabled

    checks.append(
        {
            "name": "postgres_enabled",
            "ok": True,
            "detail": "enabled" if postgres_enabled else "disabled",
        }
    )

    if postgres_enabled:
        try:
            psycopg = _load_psycopg()
            checks.append(
                {
                    "name": "postgres_driver",
                    "ok": True,
                    "detail": "psycopg importable",
                }
            )
            try:
                with psycopg.connect(config.postgres.dsn) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                checks.append(
                    {
                        "name": "postgres_connection",
                        "ok": True,
                        "detail": _redact_dsn(config.postgres.dsn),
                    }
                )
            except Exception as exc:
                checks.append(
                    {
                        "name": "postgres_connection",
                        "ok": False,
                        "detail": str(exc),
                    }
                )
                recommendations.append("Start local PostgreSQL and ensure TRADINGCAT_POSTGRES_DSN points to a reachable database.")
        except PostgresStoreUnavailable:
            checks.append(
                {
                    "name": "postgres_driver",
                    "ok": False,
                    "detail": "psycopg is not installed in this environment",
                }
            )
            recommendations.append("Install PostgreSQL support with: .venv/bin/python -m pip install -e .")
    else:
        recommendations.append("Set TRADINGCAT_POSTGRES_ENABLED=true to move local state and audit logs into PostgreSQL.")

    duckdb_enabled = config.duckdb.enabled
    checks.append(
        {
            "name": "duckdb_enabled",
            "ok": True,
            "detail": "enabled" if duckdb_enabled else "disabled",
        }
    )
    if duckdb_enabled:
        try:
            _load_duckdb()
            checks.append(
                {
                    "name": "duckdb_driver",
                    "ok": True,
                    "detail": "duckdb importable",
                }
            )
            config.duckdb.path.parent.mkdir(parents=True, exist_ok=True)
            config.duckdb.parquet_dir.mkdir(parents=True, exist_ok=True)
            checks.append(
                {
                    "name": "duckdb_paths",
                    "ok": True,
                    "detail": f"{config.duckdb.path} | {config.duckdb.parquet_dir}",
                }
            )
        except DuckDbStoreUnavailable:
            checks.append(
                {
                    "name": "duckdb_driver",
                    "ok": False,
                    "detail": "duckdb is not installed in this environment",
                }
            )
            recommendations.append("Install DuckDB support with: .venv/bin/python -m pip install -e .")
        except Exception as exc:
            checks.append(
                {
                    "name": "duckdb_paths",
                    "ok": False,
                    "detail": str(exc),
                }
            )
            recommendations.append("Ensure TRADINGCAT_DUCKDB_PATH and TRADINGCAT_PARQUET_DIR are writable local paths.")
    else:
        recommendations.append("Set TRADINGCAT_DUCKDB_ENABLED=true to persist research experiments in DuckDB and Parquet.")

    checks.append(
        {
            "name": "scheduler_backend",
            "ok": config.scheduler.backend in {"lightweight", "apscheduler"},
            "detail": config.scheduler.backend,
        }
    )
    checks.append(
        {
            "name": "scheduler_autostart",
            "ok": True,
            "detail": "enabled" if config.scheduler.autostart else "disabled",
        }
    )
    if config.scheduler.backend == "apscheduler":
        try:
            _load_apscheduler()
            checks.append(
                {
                    "name": "scheduler_driver",
                    "ok": True,
                    "detail": "apscheduler importable",
                }
            )
        except SchedulerBackendUnavailable:
            checks.append(
                {
                    "name": "scheduler_driver",
                    "ok": False,
                    "detail": "apscheduler is not installed in this environment",
                }
            )
            recommendations.append("Install APScheduler support with: .venv/bin/python -m pip install -e .")
    else:
        recommendations.append("Set TRADINGCAT_SCHEDULER_BACKEND=apscheduler to enable background job execution.")

    checks.append(
        {
            "name": "futu_enabled",
            "ok": True,
            "detail": "enabled" if futu_enabled else "disabled",
        }
    )

    if futu_enabled:
        sdk_available = importlib.util.find_spec("futu") is not None
        checks.append(
            {
                "name": "futu_sdk",
                "ok": sdk_available,
                "detail": "futu SDK importable" if sdk_available else "futu SDK is not installed in this environment",
            }
        )
        port_ok = 0 < config.futu.port < 65536
        checks.append(
            {
                "name": "futu_port",
                "ok": port_ok,
                "detail": str(config.futu.port),
            }
        )
        env_ok = config.futu.environment in {"SIMULATE", "REAL"}
        checks.append(
            {
                "name": "futu_environment",
                "ok": env_ok,
                "detail": config.futu.environment,
            }
        )
        if config.futu.environment == "REAL" and not config.futu.unlock_trade_password:
            recommendations.append("Set TRADINGCAT_FUTU_UNLOCK_TRADE_PASSWORD before attempting real trade operations.")
        if not sdk_available:
            recommendations.append("Install the Futu SDK with: .venv/bin/python -m pip install -e '.[dev,futu]'")
        recommendations.append("Ensure Futu OpenD is running locally and logged in before calling /broker/validate.")
    else:
        recommendations.append("Set TRADINGCAT_FUTU_ENABLED=true in .env when you are ready to validate OpenD.")

    if not env_file_present:
        recommendations.append("Create .env from .env.example before local startup.")

    healthy = all(bool(item["ok"]) for item in checks if item["name"] != "env_file")
    return {
        "healthy": healthy,
        "base_currency": config.base_currency,
        "portfolio_value": config.portfolio_value,
        "data_dir": str(config.data_dir),
        "postgres": {
            "enabled": config.postgres.enabled,
            "dsn": _redact_dsn(config.postgres.dsn),
        },
        "duckdb": {
            "enabled": config.duckdb.enabled,
            "path": str(config.duckdb.path),
            "parquet_dir": str(config.duckdb.parquet_dir),
        },
        "scheduler": {
            "backend": config.scheduler.backend,
            "autostart": config.scheduler.autostart,
        },
        "futu": {
            "enabled": config.futu.enabled,
            "host": config.futu.host,
            "port": config.futu.port,
            "environment": config.futu.environment,
        },
        "checks": checks,
        "recommendations": recommendations,
    }


def summarize_validation_diagnostics(
    preflight: dict[str, object],
    broker_validation: dict[str, object],
    market_data: dict[str, object] | None = None,
    execution_preview: dict[str, object] | None = None,
    market_data_error: str | None = None,
    execution_preview_error: str | None = None,
) -> dict[str, object]:
    category = "ready_for_validation"
    severity = "info"
    ready = True
    findings: list[str] = []
    next_actions: list[str] = []

    futu_enabled = bool(preflight["futu"]["enabled"])  # type: ignore[index]
    checks = {item["name"]: item for item in preflight["checks"]}  # type: ignore[index]

    if not futu_enabled:
        category = "futu_disabled"
        severity = "warning"
        ready = False
        findings.append("Futu integration is disabled, so all broker checks will remain simulated.")
        next_actions.append("Set TRADINGCAT_FUTU_ENABLED=true in .env before validating OpenD.")
    elif not checks.get("futu_sdk", {}).get("ok", False):
        category = "sdk_missing"
        severity = "error"
        ready = False
        findings.append("The futu SDK is not importable in the current Python environment.")
        next_actions.append("Install dependencies with: .venv/bin/python -m pip install -e '.[dev,futu]'")
    elif not checks.get("futu_environment", {}).get("ok", True):
        category = "config_invalid"
        severity = "error"
        ready = False
        findings.append(f"Invalid TRADINGCAT_FUTU_ENVIRONMENT value: {checks['futu_environment']['detail']}")
        next_actions.append("Set TRADINGCAT_FUTU_ENVIRONMENT to SIMULATE or REAL.")
    else:
        broker_checks = broker_validation.get("checks", {})
        quote_status = broker_checks.get("quote", {}).get("status")
        trade_status = broker_checks.get("trade", {}).get("status")
        if quote_status == "failed" and trade_status == "failed":
            category = "opend_unreachable"
            severity = "error"
            ready = False
            findings.append("Both quote and trade validation failed, which usually means OpenD is unavailable or not logged in.")
            next_actions.append("Start OpenD locally, confirm login, then rerun ./scripts/validate_broker.sh.")
        elif quote_status == "failed":
            category = "quote_channel_failed"
            severity = "error"
            ready = False
            findings.append("Trade validation passed or was skipped, but quote validation failed.")
            next_actions.append("检查行情权限和 OpenD 行情连接。")
        elif trade_status == "failed":
            category = "trade_channel_failed"
            severity = "error"
            ready = False
            findings.append("Quote validation passed or was skipped, but trade validation failed.")
            next_actions.append("检查交易权限、交易解锁状态和账户环境。")

        if market_data_error:
            category = "market_data_mapping_failed" if category == "ready_for_validation" else category
            severity = "error"
            ready = False
            findings.append(f"Market data smoke test failed: {market_data_error}")
            next_actions.append("Inspect quote permissions and Futu market data field mappings.")
        elif market_data is not None:
            failed_symbols = market_data.get("failed_symbols", {})
            successful_symbols = market_data.get("successful_symbols", [])
            findings.append(f"Market data smoke test returned {len(successful_symbols)} successful symbols.")
            if failed_symbols:
                category = "quote_channel_failed" if category == "ready_for_validation" else category
                severity = "error"
                ready = False
                findings.append(f"Market data smoke test had {len(failed_symbols)} failed symbol checks.")
                next_actions.append("检查失败标的的行情权限，或缩小冒烟测试股票池范围。")

        if execution_preview_error:
            category = "risk_or_preview_failed" if category == "ready_for_validation" else category
            severity = "error"
            ready = False
            findings.append(f"Execution preview failed: {execution_preview_error}")
            next_actions.append("Inspect risk-state inputs and signal generation before enabling execution.")
        elif execution_preview is not None:
            findings.append(
                f"Execution preview produced {execution_preview.get('intent_count', 0)} order intents "
                f"({execution_preview.get('manual_count', 0)} manual approvals)."
            )

    if checks.get("env_file", {}).get("ok") is False:
        findings.append("The project is running without a local .env file.")
        next_actions.append("Create .env from .env.example so local configuration is explicit.")

    if category == "ready_for_validation":
        next_actions.append("If you are using OpenD, proceed with simulated order placement and cancellation checks.")

    return {
        "category": category,
        "severity": severity,
        "ready": ready,
        "findings": findings,
        "next_actions": next_actions,
    }
