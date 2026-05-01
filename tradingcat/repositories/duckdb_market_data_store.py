from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from tradingcat.repositories.duckdb_store import _load_duckdb


class DuckDbMarketDataStore:
    def __init__(self, db_path: Path, parquet_dir: Path) -> None:
        self._db_path = db_path
        self._parquet_dir = parquet_dir
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._parquet_dir.mkdir(parents=True, exist_ok=True)
        self._duckdb = _load_duckdb()
        self._ensure_schema()

    def _connect(self):
        return self._duckdb.connect(str(self._db_path))

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS instruments (
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    name TEXT,
                    lot_size DOUBLE DEFAULT 1,
                    enabled BOOLEAN DEFAULT TRUE,
                    tradable BOOLEAN DEFAULT TRUE,
                    liquidity_bucket TEXT DEFAULT 'medium',
                    avg_daily_dollar_volume_m DOUBLE,
                    tags_json TEXT DEFAULT '[]',
                    exchange TEXT,
                    sector TEXT,
                    industry TEXT,
                    data_source TEXT,
                    quote_permission TEXT,
                    st_status TEXT,
                    limit_up DOUBLE,
                    limit_down DOUBLE,
                    suspended BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (symbol, market)
                )
                """
            )
            self._ensure_columns(
                conn,
                "instruments",
                {
                    "lot_size": "DOUBLE DEFAULT 1",
                    "enabled": "BOOLEAN DEFAULT TRUE",
                    "tradable": "BOOLEAN DEFAULT TRUE",
                    "liquidity_bucket": "TEXT DEFAULT 'medium'",
                    "avg_daily_dollar_volume_m": "DOUBLE",
                    "tags_json": "TEXT DEFAULT '[]'",
                    "exchange": "TEXT",
                    "sector": "TEXT",
                    "industry": "TEXT",
                    "data_source": "TEXT",
                    "quote_permission": "TEXT",
                    "st_status": "TEXT",
                    "limit_up": "DOUBLE",
                    "limit_down": "DOUBLE",
                    "suspended": "BOOLEAN DEFAULT FALSE",
                },
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS price_bars (
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    name TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    open DOUBLE NOT NULL,
                    high DOUBLE NOT NULL,
                    low DOUBLE NOT NULL,
                    close DOUBLE NOT NULL,
                    volume DOUBLE NOT NULL,
                    source TEXT DEFAULT 'unknown',
                    quality TEXT DEFAULT 'unknown',
                    fetched_at TIMESTAMP,
                    PRIMARY KEY (symbol, market, timestamp)
                )
                """
            )
            self._ensure_columns(
                conn,
                "price_bars",
                {
                    "source": "TEXT DEFAULT 'unknown'",
                    "quality": "TEXT DEFAULT 'unknown'",
                    "fetched_at": "TIMESTAMP",
                },
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS corporate_actions (
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    effective_date DATE NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (symbol, market, effective_date, payload_json)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fx_rates (
                    base_currency TEXT NOT NULL,
                    quote_currency TEXT NOT NULL,
                    effective_date DATE NOT NULL,
                    rate DOUBLE NOT NULL,
                    source TEXT DEFAULT 'unknown',
                    quality TEXT DEFAULT 'unknown',
                    fetched_at TIMESTAMP,
                    PRIMARY KEY (base_currency, quote_currency, effective_date)
                )
                """
            )
            self._ensure_columns(
                conn,
                "fx_rates",
                {
                    "source": "TEXT DEFAULT 'unknown'",
                    "quality": "TEXT DEFAULT 'unknown'",
                    "fetched_at": "TIMESTAMP",
                },
            )

    @staticmethod
    def _ensure_columns(conn, table: str, columns: dict[str, str]) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def load_instruments(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, market, asset_class, currency, name,
                    lot_size, enabled, tradable, liquidity_bucket, avg_daily_dollar_volume_m, tags_json,
                    exchange, sector, industry, data_source, quote_permission, st_status, limit_up, limit_down, suspended
                FROM instruments
                ORDER BY market, symbol
                """
            ).fetchall()
        return [
            {
                "symbol": row[0],
                "market": row[1],
                "asset_class": row[2],
                "currency": row[3],
                "name": row[4],
                "lot_size": row[5] if row[5] is not None else 1.0,
                "enabled": bool(row[6]) if row[6] is not None else True,
                "tradable": bool(row[7]) if row[7] is not None else True,
                "liquidity_bucket": row[8] or "medium",
                "avg_daily_dollar_volume_m": row[9],
                "tags": json.loads(row[10] or "[]"),
                "exchange": row[11],
                "sector": row[12],
                "industry": row[13],
                "data_source": row[14],
                "quote_permission": row[15],
                "st_status": row[16],
                "limit_up": row[17],
                "limit_down": row[18],
                "suspended": bool(row[19]) if row[19] is not None else False,
            }
            for row in rows
        ]

    def save_instruments(self, instruments: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            for instrument in instruments:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO instruments (
                        symbol, market, asset_class, currency, name,
                        lot_size, enabled, tradable, liquidity_bucket,
                        avg_daily_dollar_volume_m, tags_json,
                        exchange, sector, industry, data_source, quote_permission,
                        st_status, limit_up, limit_down, suspended
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        instrument["symbol"],
                        instrument["market"],
                        instrument["asset_class"],
                        instrument["currency"],
                        instrument.get("name"),
                        instrument.get("lot_size", 1.0),
                        bool(instrument.get("enabled", True)),
                        bool(instrument.get("tradable", True)),
                        instrument.get("liquidity_bucket", "medium"),
                        instrument.get("avg_daily_dollar_volume_m"),
                        json.dumps(instrument.get("tags", []), ensure_ascii=True),
                        instrument.get("exchange"),
                        instrument.get("sector"),
                        instrument.get("industry"),
                        instrument.get("data_source"),
                        instrument.get("quote_permission"),
                        instrument.get("st_status"),
                        instrument.get("limit_up"),
                        instrument.get("limit_down"),
                        bool(instrument.get("suspended", False)),
                    ),
                )
            self._export(conn)

    def save_bars(self, instrument: dict[str, Any], bars: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            for bar in bars:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO price_bars (
                        symbol, market, asset_class, currency, name, timestamp,
                        open, high, low, close, volume, source, quality, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        instrument["symbol"],
                        instrument["market"],
                        instrument["asset_class"],
                        instrument["currency"],
                        instrument.get("name"),
                        bar["timestamp"],
                        bar["open"],
                        bar["high"],
                        bar["low"],
                        bar["close"],
                        bar["volume"],
                        bar.get("source", "unknown"),
                        bar.get("quality", "unknown"),
                        bar.get("fetched_at"),
                    ),
                )
            self._export(conn)

    def load_bars(self, symbol: str, market: str, start: date, end: date) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, market, asset_class, currency, name, timestamp,
                    open, high, low, close, volume, source, quality, fetched_at
                FROM price_bars
                WHERE symbol = ? AND market = ? AND DATE(timestamp) BETWEEN ? AND ?
                ORDER BY timestamp
                """,
                (symbol, market, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            {
                "instrument": {
                    "symbol": row[0],
                    "market": row[1],
                    "asset_class": row[2],
                    "currency": row[3],
                    "name": row[4],
                },
                "timestamp": row[5],
                "open": row[6],
                "high": row[7],
                "low": row[8],
                "close": row[9],
                "volume": row[10],
                "source": row[11] or "unknown",
                "quality": row[12] or "unknown",
                "fetched_at": row[13],
            }
            for row in rows
        ]

    def save_corporate_actions(self, instrument: dict[str, Any], actions: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            for action in actions:
                effective_date = str(
                    action.get("ex_div_date") or action.get("record_date") or action.get("effective_date") or date.today()
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO corporate_actions (symbol, market, effective_date, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        instrument["symbol"],
                        instrument["market"],
                        effective_date,
                        json.dumps(action, ensure_ascii=True, sort_keys=True),
                    ),
                )
            self._export(conn)

    def load_corporate_actions(self, symbol: str, market: str, start: date, end: date) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM corporate_actions
                WHERE symbol = ? AND market = ? AND effective_date BETWEEN ? AND ?
                ORDER BY effective_date
                """,
                (symbol, market, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_fx_rates(self, rates: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            for rate in rates:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fx_rates (
                        base_currency, quote_currency, effective_date, rate, source, quality, fetched_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rate["base_currency"],
                        rate["quote_currency"],
                        rate["date"],
                        rate["rate"],
                        rate.get("source", "unknown"),
                        rate.get("quality", "unknown"),
                        rate.get("fetched_at"),
                    ),
                )
            self._export(conn)

    def load_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT base_currency, quote_currency, effective_date, rate, source, quality, fetched_at
                FROM fx_rates
                WHERE base_currency = ? AND quote_currency = ? AND effective_date BETWEEN ? AND ?
                ORDER BY effective_date
                """,
                (base_currency, quote_currency, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            {
                "base_currency": row[0],
                "quote_currency": row[1],
                "date": row[2],
                "rate": row[3],
                "source": row[4] or "unknown",
                "quality": row[5] or "unknown",
                "fetched_at": row[6],
            }
            for row in rows
        ]

    def clear_all(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM price_bars")
            conn.execute("DELETE FROM corporate_actions")
            conn.execute("DELETE FROM fx_rates")
            conn.execute("DELETE FROM instruments")
            self._export(conn)

    def _export(self, conn) -> None:
        conn.execute(
            f"""
            COPY (SELECT * FROM instruments ORDER BY market, symbol)
            TO '{(self._parquet_dir / "instruments.parquet").as_posix()}'
            (FORMAT PARQUET)
            """
        )
        conn.execute(
            f"""
            COPY (SELECT * FROM price_bars ORDER BY market, symbol, timestamp)
            TO '{(self._parquet_dir / "price_bars.parquet").as_posix()}'
            (FORMAT PARQUET)
            """
        )
        conn.execute(
            f"""
            COPY (SELECT * FROM corporate_actions ORDER BY market, symbol, effective_date)
            TO '{(self._parquet_dir / "corporate_actions.parquet").as_posix()}'
            (FORMAT PARQUET)
            """
        )
        conn.execute(
            f"""
            COPY (SELECT * FROM fx_rates ORDER BY base_currency, quote_currency, effective_date)
            TO '{(self._parquet_dir / "fx_rates.parquet").as_posix()}'
            (FORMAT PARQUET)
            """
        )
