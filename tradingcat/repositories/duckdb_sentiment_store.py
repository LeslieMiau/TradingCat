"""DuckDB persistence for market sentiment history.

Stores hourly sentiment snapshots so the UI can render 30-day sparklines.
Table: ``market_sentiment_history`` with one row per (timestamp, market, indicator_key).

Follows the same pattern as ``DuckDbResearchStore`` — optional dependency,
never raises on failure, returns empty results when DuckDB is unavailable.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from tradingcat.repositories.duckdb_store import DuckDbStoreUnavailable, _load_duckdb


logger = logging.getLogger(__name__)


class DuckDbSentimentStore:
    """Append-only store for per-indicator sentiment history readings."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._duckdb = _load_duckdb()
        self._ensure_schema()

    def _connect(self):
        return self._duckdb.connect(str(self._db_path))

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_sentiment_history (
                    ts TIMESTAMP NOT NULL,
                    market TEXT NOT NULL,
                    indicator_key TEXT NOT NULL,
                    value DOUBLE,
                    score DOUBLE NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    composite_score DOUBLE NOT NULL DEFAULT 0,
                    risk_switch TEXT NOT NULL DEFAULT 'unknown',
                    PRIMARY KEY (ts, market, indicator_key)
                )
                """
            )

    def persist_snapshot(self, snapshot_dict: dict[str, Any]) -> int:
        """Persist a MarketSentimentSnapshot (as dict) into history.

        Returns the number of rows inserted.
        """
        ts = datetime.now(UTC)
        composite_score = snapshot_dict.get("composite_score", 0.0)
        risk_switch = snapshot_dict.get("risk_switch", "unknown")
        views = snapshot_dict.get("views", [])

        rows_inserted = 0
        with self._connect() as conn:
            for view in views:
                market = view.get("market", "unknown")
                for ind in view.get("indicators", []):
                    try:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO market_sentiment_history
                                (ts, market, indicator_key, value, score, status,
                                 composite_score, risk_switch)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                ts,
                                str(market),
                                str(ind.get("key", "")),
                                ind.get("value"),
                                float(ind.get("score", 0.0)),
                                str(ind.get("status", "unknown")),
                                float(composite_score),
                                str(risk_switch),
                            ),
                        )
                        rows_inserted += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "sentiment history: failed to insert %s/%s: %s",
                            market, ind.get("key"), exc,
                        )
        return rows_inserted

    def load_history(
        self,
        *,
        market: str | None = None,
        indicator_key: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Load recent indicator history, ordered by timestamp ascending.

        Returns a list of dicts with ts, market, indicator_key, value, score,
        status, composite_score, risk_switch.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        clauses = ["ts >= ?"]
        params: list[Any] = [cutoff]

        if market is not None:
            clauses.append("market = ?")
            params.append(str(market))
        if indicator_key is not None:
            clauses.append("indicator_key = ?")
            params.append(str(indicator_key))

        where = " AND ".join(clauses)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ts, market, indicator_key, value, score, status,
                       composite_score, risk_switch
                FROM market_sentiment_history
                WHERE {where}
                ORDER BY ts ASC
                """,
                params,
            ).fetchall()

        return [
            {
                "ts": row[0].isoformat() if isinstance(row[0], datetime) else str(row[0]),
                "market": row[1],
                "indicator_key": row[2],
                "value": row[3],
                "score": row[4],
                "status": row[5],
                "composite_score": row[6],
                "risk_switch": row[7],
            }
            for row in rows
        ]

    def prune(self, *, keep_days: int = 90) -> int:
        """Delete rows older than keep_days. Returns rows deleted."""
        cutoff = datetime.now(UTC) - timedelta(days=keep_days)
        with self._connect() as conn:
            before = conn.execute("SELECT count(*) FROM market_sentiment_history").fetchone()[0]
            conn.execute("DELETE FROM market_sentiment_history WHERE ts < ?", (cutoff,))
            after = conn.execute("SELECT count(*) FROM market_sentiment_history").fetchone()[0]
        return before - after
