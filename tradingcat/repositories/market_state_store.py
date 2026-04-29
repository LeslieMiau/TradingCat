from __future__ import annotations

import json
import logging
from datetime import date, datetime
from threading import RLock

from tradingcat.config import AppConfig
from tradingcat.domain.models import Market, MarketStateSnapshot
from tradingcat.repositories.json_store import JsonStore


logger = logging.getLogger(__name__)


class _DuckDbMarketStateStore:
    def __init__(self, config: AppConfig) -> None:
        from tradingcat.repositories.duckdb_store import _load_duckdb

        self._db_path = config.duckdb.path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._duckdb = _load_duckdb()
        self._ensure_schema()

    def _connect(self):
        return self._duckdb.connect(str(self._db_path))

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_state_snapshots (
                    market TEXT NOT NULL,
                    session_date DATE NOT NULL,
                    observed_at TIMESTAMP NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (market, session_date, observed_at)
                )
                """
            )

    def upsert(self, snapshot: MarketStateSnapshot) -> None:
        payload = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM market_state_snapshots
                WHERE market = ? AND session_date = ? AND observed_at = ?
                """,
                [snapshot.market.value, snapshot.session_date, snapshot.observed_at],
            )
            conn.execute(
                """
                INSERT INTO market_state_snapshots
                    (market, session_date, observed_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                [snapshot.market.value, snapshot.session_date, snapshot.observed_at, payload],
            )

    def list(self, *, market: Market, session_date: date) -> list[MarketStateSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM market_state_snapshots
                WHERE market = ? AND session_date = ?
                ORDER BY observed_at ASC
                """,
                [market.value, session_date],
            ).fetchall()
        return [MarketStateSnapshot.model_validate(json.loads(row[0])) for row in rows]

    def latest_any(self, *, market: Market) -> MarketStateSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM market_state_snapshots
                WHERE market = ?
                ORDER BY observed_at DESC
                LIMIT 1
                """,
                [market.value],
            ).fetchone()
        return MarketStateSnapshot.model_validate(json.loads(row[0])) if row else None


class MarketStateStore:
    def __init__(self, config: AppConfig) -> None:
        self._duckdb_store: _DuckDbMarketStateStore | None = None
        self._memory: dict[str, dict] = {}
        self._memory_lock = RLock()
        self._json_store = JsonStore(config.data_dir / "market_state_snapshots.json")
        if config.duckdb.enabled:
            try:
                self._duckdb_store = _DuckDbMarketStateStore(config)
                logger.info("market state store: DuckDB initialized at %s", config.duckdb.path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("market state store: DuckDB unavailable (%s); using JSON fallback", exc)

    @property
    def backend(self) -> str:
        return "duckdb" if self._duckdb_store else "json"

    def upsert(self, snapshot: MarketStateSnapshot) -> None:
        if self._duckdb_store is not None:
            try:
                self._duckdb_store.upsert(snapshot)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("market state store: duckdb upsert failed (%s); using JSON fallback", exc)
        records = self._load_json_records()
        records[self._key(snapshot.market, snapshot.session_date, snapshot.observed_at)] = snapshot.model_dump(mode="json")
        self._save_json_records(records)

    def list(self, *, market: Market, session_date: date) -> list[MarketStateSnapshot]:
        if self._duckdb_store is not None:
            try:
                return self._duckdb_store.list(market=market, session_date=session_date)
            except Exception as exc:  # noqa: BLE001
                logger.warning("market state store: duckdb list failed (%s); using JSON fallback", exc)
        rows = []
        for payload in self._load_json_records().values():
            if payload.get("market") == market.value and payload.get("session_date") == session_date.isoformat():
                rows.append(MarketStateSnapshot.model_validate(payload))
        return sorted(rows, key=lambda item: item.observed_at)

    def latest(self, *, market: Market, session_date: date) -> MarketStateSnapshot | None:
        rows = self.list(market=market, session_date=session_date)
        return rows[-1] if rows else None

    def latest_any(self, *, market: Market) -> MarketStateSnapshot | None:
        if self._duckdb_store is not None:
            try:
                return self._duckdb_store.latest_any(market=market)
            except Exception as exc:  # noqa: BLE001
                logger.warning("market state store: duckdb latest_any failed (%s); using JSON fallback", exc)
        rows = []
        for payload in self._load_json_records().values():
            if payload.get("market") == market.value:
                rows.append(MarketStateSnapshot.model_validate(payload))
        return max(rows, key=lambda item: item.observed_at) if rows else None

    def _load_json_records(self) -> dict[str, dict]:
        with self._memory_lock:
            records = self._json_store.load({})
            if isinstance(records, dict):
                self._memory = records
            return dict(self._memory)

    def _save_json_records(self, records: dict[str, dict]) -> None:
        with self._memory_lock:
            self._memory = dict(records)
            self._json_store.save(records)

    @staticmethod
    def _key(market: Market, session_date: date, observed_at: datetime) -> str:
        return f"{market.value}:{session_date.isoformat()}:{observed_at.isoformat()}"
