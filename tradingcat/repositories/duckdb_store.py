from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DuckDbStoreUnavailable(RuntimeError):
    pass


def _load_duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise DuckDbStoreUnavailable("duckdb is not installed") from exc
    return duckdb


class DuckDbResearchStore:
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
                CREATE TABLE IF NOT EXISTS backtest_experiments (
                    id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    as_of DATE NOT NULL,
                    signal_count INTEGER NOT NULL,
                    gross_return DOUBLE NOT NULL,
                    net_return DOUBLE NOT NULL,
                    turnover DOUBLE NOT NULL,
                    max_drawdown DOUBLE NOT NULL,
                    annualized_return DOUBLE NOT NULL DEFAULT 0,
                    volatility DOUBLE NOT NULL DEFAULT 0,
                    sharpe DOUBLE NOT NULL DEFAULT 0,
                    calmar DOUBLE NOT NULL DEFAULT 0,
                    sample_months INTEGER NOT NULL DEFAULT 0,
                    sample_start DATE NOT NULL DEFAULT DATE '2018-01-01',
                    window_count INTEGER NOT NULL DEFAULT 0,
                    passed_validation BOOLEAN NOT NULL DEFAULT FALSE,
                    assumptions_json TEXT NOT NULL
                )
                """
            )
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS annualized_return DOUBLE DEFAULT 0")
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS volatility DOUBLE DEFAULT 0")
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS sharpe DOUBLE DEFAULT 0")
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS calmar DOUBLE DEFAULT 0")
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS sample_months INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS sample_start DATE DEFAULT DATE '2018-01-01'")
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS window_count INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE backtest_experiments ADD COLUMN IF NOT EXISTS passed_validation BOOLEAN DEFAULT FALSE")

    def load(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    strategy_id,
                    started_at,
                    as_of,
                    signal_count,
                    gross_return,
                    net_return,
                    turnover,
                    max_drawdown,
                    annualized_return,
                    volatility,
                    sharpe,
                    calmar,
                    sample_months,
                    sample_start,
                    window_count,
                    passed_validation,
                    assumptions_json
                FROM backtest_experiments
                ORDER BY started_at DESC
                """
            ).fetchall()
        return [
            {
                "id": row[0],
                "strategy_id": row[1],
                "started_at": row[2],
                "as_of": row[3],
                "signal_count": row[4],
                "metrics": {
                    "gross_return": row[5],
                    "net_return": row[6],
                    "turnover": row[7],
                    "max_drawdown": row[8],
                    "annualized_return": row[9],
                    "volatility": row[10],
                    "sharpe": row[11],
                    "calmar": row[12],
                    "sample_months": row[13],
                },
                "sample_start": row[14],
                "window_count": row[15],
                "passed_validation": row[16],
                "assumptions": json.loads(row[17]),
            }
            for row in rows
        ]

    def save(self, experiments: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM backtest_experiments")
            for experiment in experiments:
                conn.execute(
                    """
                    INSERT INTO backtest_experiments (
                        id, strategy_id, started_at, as_of, signal_count,
                        gross_return, net_return, turnover, max_drawdown,
                        annualized_return, volatility, sharpe, calmar, sample_months,
                        sample_start, window_count, passed_validation, assumptions_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        experiment["id"],
                        experiment["strategy_id"],
                        experiment["started_at"],
                        experiment["as_of"],
                        experiment["signal_count"],
                        experiment["metrics"]["gross_return"],
                        experiment["metrics"]["net_return"],
                        experiment["metrics"]["turnover"],
                        experiment["metrics"]["max_drawdown"],
                        experiment["metrics"].get("annualized_return", 0.0),
                        experiment["metrics"].get("volatility", 0.0),
                        experiment["metrics"].get("sharpe", 0.0),
                        experiment["metrics"].get("calmar", 0.0),
                        experiment["metrics"].get("sample_months", 0),
                        experiment.get("sample_start", "2018-01-01"),
                        experiment.get("window_count", 0),
                        experiment.get("passed_validation", False),
                        json.dumps(experiment["assumptions"], ensure_ascii=True),
                    ),
                )
            conn.execute(
                f"""
                COPY (
                    SELECT * FROM backtest_experiments ORDER BY started_at DESC
                ) TO '{(self._parquet_dir / "backtest_experiments.parquet").as_posix()}'
                (FORMAT PARQUET)
                """
            )
