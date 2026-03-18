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
                    PRIMARY KEY (symbol, market)
                )
                """
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
                    PRIMARY KEY (symbol, market, timestamp)
                )
                """
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
                    PRIMARY KEY (base_currency, quote_currency, effective_date)
                )
                """
            )

    def load_instruments(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, market, asset_class, currency, name
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
            }
            for row in rows
        ]

    def save_instruments(self, instruments: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            for instrument in instruments:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO instruments (symbol, market, asset_class, currency, name)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        instrument["symbol"],
                        instrument["market"],
                        instrument["asset_class"],
                        instrument["currency"],
                        instrument.get("name"),
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
                        open, high, low, close, volume
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
            self._export(conn)

    def load_bars(self, symbol: str, market: str, start: date, end: date) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, market, asset_class, currency, name, timestamp, open, high, low, close, volume
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
                    INSERT OR REPLACE INTO fx_rates (base_currency, quote_currency, effective_date, rate)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        rate["base_currency"],
                        rate["quote_currency"],
                        rate["date"],
                        rate["rate"],
                    ),
                )
            self._export(conn)

    def load_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT base_currency, quote_currency, effective_date, rate
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
