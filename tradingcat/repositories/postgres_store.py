from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class PostgresStoreUnavailable(RuntimeError):
    pass


def _load_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise PostgresStoreUnavailable("psycopg is not installed") from exc
    return psycopg


class PostgresStore:
    def __init__(self, dsn: str, connector: Callable[[str], Any] | None = None) -> None:
        self._dsn = dsn
        if connector is None:
            psycopg = _load_psycopg()
            connector = psycopg.connect
        self._connector = connector
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._connector(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS state_buckets (
                        bucket TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id BIGSERIAL PRIMARY KEY,
                        bucket TEXT NOT NULL,
                        action TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

    def load(self, bucket: str, default: Any) -> Any:
        with self._connector(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM state_buckets WHERE bucket = %s", (bucket,))
                row = cur.fetchone()
        return default if row is None else row[0]

    def save(self, bucket: str, payload: Any) -> None:
        serialized = json.dumps(payload, ensure_ascii=True)
        with self._connector(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO state_buckets (bucket, payload, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (bucket)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                    """,
                    (bucket, serialized),
                )
                cur.execute(
                    """
                    INSERT INTO audit_log (bucket, action, payload)
                    VALUES (%s, %s, %s::jsonb)
                    """,
                    (bucket, "save", serialized),
                )

    def append_audit(self, bucket: str, action: str, payload: Any) -> None:
        serialized = json.dumps(payload, ensure_ascii=True)
        with self._connector(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_log (bucket, action, payload)
                    VALUES (%s, %s, %s::jsonb)
                    """,
                    (bucket, action, serialized),
                )

    def list_audit(self, bucket: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connector(self._dsn) as conn:
            with conn.cursor() as cur:
                if bucket is None:
                    cur.execute(
                        """
                        SELECT bucket, action, payload
                        FROM audit_log
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT bucket, action, payload
                        FROM audit_log
                        WHERE bucket = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (bucket, limit),
                    )
                rows = cur.fetchall() or []
        return [
            {
                "bucket": row[0],
                "action": row[1],
                "payload": row[2],
            }
            for row in rows
        ]
