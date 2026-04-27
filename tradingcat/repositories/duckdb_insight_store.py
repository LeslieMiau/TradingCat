"""DuckDB-backed persistence for Insight entries and user feedback.

Schema is minimal: one row per Insight, JSON columns for ``subjects`` and
``causal_chain`` so detectors can attach arbitrary evidence payloads without
schema migrations. ``insight_feedback`` records every user action (dismiss /
ack / acted) for future learning loops in v2.

This module is optional — callers should use ``InsightStore`` facade which
falls back to an in-memory dict when DuckDB is unavailable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tradingcat.domain.models import (
    Insight,
    InsightEvidence,
    InsightKind,
    InsightSeverity,
    InsightUserAction,
)
from tradingcat.repositories.duckdb_store import _load_duckdb


class DuckDbInsightStore:
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
                CREATE TABLE IF NOT EXISTS insights (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    subjects_json TEXT NOT NULL,
                    causal_chain_json TEXT NOT NULL,
                    confidence DOUBLE NOT NULL,
                    triggered_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    user_action TEXT NOT NULL DEFAULT 'pending',
                    dismissed_reason TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS insight_feedback (
                    id TEXT PRIMARY KEY,
                    insight_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    note TEXT,
                    recorded_at TIMESTAMP NOT NULL
                )
                """
            )

    def upsert(self, insight: Insight) -> None:
        payload = (
            insight.id,
            insight.kind.value,
            insight.severity.value,
            insight.headline,
            json.dumps(insight.subjects, ensure_ascii=False),
            json.dumps(
                [evidence.model_dump(mode="json") for evidence in insight.causal_chain],
                ensure_ascii=False,
            ),
            float(insight.confidence),
            insight.triggered_at,
            insight.expires_at,
            insight.user_action.value,
            insight.dismissed_reason,
        )
        with self._connect() as conn:
            conn.execute("DELETE FROM insights WHERE id = ?", [insight.id])
            conn.execute(
                """
                INSERT INTO insights
                    (id, kind, severity, headline, subjects_json, causal_chain_json,
                     confidence, triggered_at, expires_at, user_action, dismissed_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )

    def list(
        self,
        *,
        include_dismissed: bool = False,
        kinds: list[InsightKind] | None = None,
        now: datetime | None = None,
    ) -> list[Insight]:
        clauses: list[str] = []
        params: list = []
        if not include_dismissed:
            clauses.append("user_action != 'dismissed'")
        if kinds:
            placeholders = ",".join(["?"] * len(kinds))
            clauses.append(f"kind IN ({placeholders})")
            params.extend(kind.value for kind in kinds)
        cutoff = now or datetime.now(timezone.utc)
        clauses.append("expires_at > ?")
        params.append(cutoff)
        where = " AND ".join(clauses) if clauses else "1=1"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, kind, severity, headline, subjects_json, causal_chain_json,
                       confidence, triggered_at, expires_at, user_action, dismissed_reason
                FROM insights
                WHERE {where}
                ORDER BY
                    CASE severity WHEN 'urgent' THEN 0 WHEN 'notable' THEN 1 ELSE 2 END,
                    triggered_at DESC
                """,
                params,
            ).fetchall()
        return [self._row_to_insight(row) for row in rows]

    def get(self, insight_id: str) -> Insight | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, kind, severity, headline, subjects_json, causal_chain_json,
                       confidence, triggered_at, expires_at, user_action, dismissed_reason
                FROM insights WHERE id = ?
                """,
                [insight_id],
            ).fetchone()
        return self._row_to_insight(row) if row else None

    def update_user_action(
        self,
        insight_id: str,
        action: InsightUserAction,
        *,
        reason: str | None = None,
    ) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE insights SET user_action = ?, dismissed_reason = ? WHERE id = ?",
                [action.value, reason, insight_id],
            )
            updated = cursor.fetchall()
            # DuckDB's UPDATE rowcount isn't always reliable across versions;
            # confirm by re-reading.
            if self.get(insight_id) is None:
                return False
            self._record_feedback(conn, insight_id, action, reason)
            _ = updated
        return True

    def _record_feedback(self, conn, insight_id: str, action: InsightUserAction, note: str | None) -> None:
        feedback_id = f"{insight_id}:{action.value}:{datetime.now(timezone.utc).isoformat()}"
        conn.execute(
            """
            INSERT INTO insight_feedback (id, insight_id, action, note, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [feedback_id, insight_id, action.value, note, datetime.now(timezone.utc)],
        )

    def expire_stale(self, *, now: datetime | None = None) -> int:
        cutoff = now or datetime.now(timezone.utc)
        with self._connect() as conn:
            before = conn.execute(
                "SELECT COUNT(*) FROM insights WHERE expires_at <= ? AND user_action = 'pending'",
                [cutoff],
            ).fetchone()[0]
            conn.execute(
                "DELETE FROM insights WHERE expires_at <= ? AND user_action = 'pending'",
                [cutoff],
            )
        return int(before)

    def _row_to_insight(self, row) -> Insight:
        causal_chain_raw = json.loads(row[5])
        return Insight(
            id=row[0],
            kind=InsightKind(row[1]),
            severity=InsightSeverity(row[2]),
            headline=row[3],
            subjects=json.loads(row[4]),
            causal_chain=[InsightEvidence.model_validate(item) for item in causal_chain_raw],
            confidence=float(row[6]),
            triggered_at=row[7],
            expires_at=row[8],
            user_action=InsightUserAction(row[9]),
            dismissed_reason=row[10],
        )
