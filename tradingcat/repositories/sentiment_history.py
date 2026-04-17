"""Repository facade for market sentiment history persistence.

Wraps `DuckDbSentimentStore` with graceful degradation: when DuckDB is
unavailable (not installed, disabled, or DB error), all methods are no-ops
that return empty results. This keeps the sentiment layer fully functional
even without the optional persistence backend.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tradingcat.config import AppConfig


logger = logging.getLogger(__name__)


class MarketSentimentHistoryRepository:
    """Read/write sentiment history with DuckDB backend (optional).

    Construction never raises. If DuckDB is unavailable, the repository
    operates in no-op mode.
    """

    def __init__(self, config: AppConfig) -> None:
        self._store = None
        if config.duckdb.enabled:
            try:
                from tradingcat.repositories.duckdb_sentiment_store import (
                    DuckDbSentimentStore,
                )

                self._store = DuckDbSentimentStore(db_path=config.duckdb.path)
                logger.info("sentiment history: DuckDB store initialized at %s", config.duckdb.path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("sentiment history: DuckDB unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._store is not None

    def persist_snapshot(self, snapshot_dict: dict[str, Any]) -> int:
        """Persist a snapshot. Returns row count, or 0 if unavailable."""
        if self._store is None:
            return 0
        try:
            return self._store.persist_snapshot(snapshot_dict)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment history: persist failed: %s", exc)
            return 0

    def load_history(
        self,
        *,
        market: str | None = None,
        indicator_key: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Load recent history. Returns empty list if unavailable."""
        if self._store is None:
            return []
        try:
            return self._store.load_history(
                market=market, indicator_key=indicator_key, days=days
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment history: load failed: %s", exc)
            return []

    def prune(self, *, keep_days: int = 90) -> int:
        """Prune old rows. Returns rows deleted, or 0 if unavailable."""
        if self._store is None:
            return 0
        try:
            return self._store.prune(keep_days=keep_days)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment history: prune failed: %s", exc)
            return 0
