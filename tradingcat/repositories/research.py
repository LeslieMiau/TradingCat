from __future__ import annotations

import math
from pathlib import Path

from tradingcat.config import AppConfig
from tradingcat.domain.models import BacktestExperiment, DashboardScorecardSnapshot
from tradingcat.repositories.duckdb_store import DuckDbResearchStore
from tradingcat.repositories.json_store import JsonStore
from tradingcat.repositories.postgres_store import PostgresStore


def _sanitize_non_finite(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, list):
        return [_sanitize_non_finite(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize_non_finite(item)
            for key, item in value.items()
        }
    return value


class BacktestExperimentRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        if isinstance(config_or_data_dir, AppConfig) and config_or_data_dir.duckdb.enabled:
            self._store = DuckDbResearchStore(config_or_data_dir.duckdb.path, config_or_data_dir.duckdb.parquet_dir)
            self._bucket = "duckdb"
        elif isinstance(config_or_data_dir, AppConfig) and config_or_data_dir.postgres.enabled:
            self._store = PostgresStore(config_or_data_dir.postgres.dsn)
            self._bucket = "backtests"
        else:
            data_dir = config_or_data_dir.data_dir if isinstance(config_or_data_dir, AppConfig) else config_or_data_dir
            self._store = JsonStore(data_dir / "backtests.json")
            self._bucket = None

    def load(self) -> dict[str, BacktestExperiment]:
        if self._bucket == "duckdb":
            records = self._store.load()
        else:
            records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {
            record["id"]: BacktestExperiment.model_validate(_sanitize_non_finite(record))
            for record in records
        }

    def save(self, experiments: dict[str, BacktestExperiment]) -> None:
        payload = [_sanitize_non_finite(experiment.model_dump(mode="json")) for experiment in experiments.values()]
        if self._bucket == "duckdb":
            self._store.save(payload)
        elif self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class DashboardSnapshotRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        data_dir = config_or_data_dir.data_dir if isinstance(config_or_data_dir, AppConfig) else config_or_data_dir
        self._store = JsonStore(data_dir / "dashboard_snapshots.json")

    def load(self) -> dict[str, DashboardScorecardSnapshot]:
        records = self._store.load({})
        if not isinstance(records, dict):
            return {}
        return {
            key: DashboardScorecardSnapshot.model_validate(record)
            for key, record in records.items()
            if isinstance(record, dict)
        }

    def save(self, snapshots: dict[str, DashboardScorecardSnapshot]) -> None:
        payload = {
            key: snapshot.model_dump(mode="json")
            for key, snapshot in snapshots.items()
        }
        self._store.save(payload)

    def clear(self) -> None:
        self._store.save({})
