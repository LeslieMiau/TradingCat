from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from tradingcat.config import AppConfig
from tradingcat.domain.models import Bar, FxRate, Instrument
from tradingcat.repositories.duckdb_market_data_store import DuckDbMarketDataStore
from tradingcat.repositories.json_store import JsonStore


class InstrumentCatalogRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        if isinstance(config_or_data_dir, AppConfig) and config_or_data_dir.duckdb.enabled:
            self._store = DuckDbMarketDataStore(config_or_data_dir.duckdb.path, config_or_data_dir.duckdb.parquet_dir)
            self._bucket = "duckdb"
            self._version_path = config_or_data_dir.duckdb.path
        else:
            data_dir = config_or_data_dir.data_dir if isinstance(config_or_data_dir, AppConfig) else config_or_data_dir
            self._store = JsonStore(data_dir / "instruments.json")
            self._bucket = None
            self._version_path = data_dir / "instruments.json"

    def load(self) -> dict[str, Instrument]:
        records = self._store.load_instruments() if self._bucket == "duckdb" else self._store.load([])
        return {self._key(Instrument.model_validate(record)): Instrument.model_validate(record) for record in records}

    def save(self, instruments: dict[str, Instrument]) -> None:
        payload = [instrument.model_dump(mode="json") for instrument in instruments.values()]
        if self._bucket == "duckdb":
            self._store.save_instruments(payload)
        else:
            self._store.save(payload)

    def clear(self) -> None:
        if self._bucket == "duckdb":
            self._store.clear_all()
        else:
            self._store.save([])

    def version_token(self) -> tuple[int, int] | None:
        if not self._version_path.exists():
            return None
        stat = self._version_path.stat()
        return stat.st_mtime_ns, stat.st_size

    def _key(self, instrument: Instrument) -> str:
        return f"{instrument.market.value}:{instrument.symbol}"


class HistoricalMarketDataRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        if isinstance(config_or_data_dir, AppConfig) and config_or_data_dir.duckdb.enabled:
            self._store = DuckDbMarketDataStore(config_or_data_dir.duckdb.path, config_or_data_dir.duckdb.parquet_dir)
            self._bucket = "duckdb"
        else:
            data_dir = config_or_data_dir.data_dir if isinstance(config_or_data_dir, AppConfig) else config_or_data_dir
            self._bars_store = JsonStore(data_dir / "price_bars.json")
            self._actions_store = JsonStore(data_dir / "corporate_actions.json")
            self._fx_store = JsonStore(data_dir / "fx_rates.json")
            self._bucket = None

    def save_bars(self, instrument: Instrument, bars: list[Bar]) -> None:
        payload = [bar.model_dump(mode="json") for bar in bars]
        if self._bucket == "duckdb":
            self._store.save_bars(instrument.model_dump(mode="json"), payload)
            return

        records = self._bars_store.load({})
        key = self._instrument_key(instrument)
        merged = {row["timestamp"]: row for row in records.get(key, [])}
        for row in payload:
            merged[row["timestamp"]] = row
        records[key] = sorted(merged.values(), key=lambda item: item["timestamp"])
        self._bars_store.save(records)

    def load_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        if self._bucket == "duckdb":
            records = self._store.load_bars(instrument.symbol, instrument.market.value, start, end)
        else:
            records = self._bars_store.load({}).get(self._instrument_key(instrument), [])
            records = [
                row
                for row in records
                if start.isoformat() <= str(row["timestamp"]).split("T", 1)[0] <= end.isoformat()
            ]
        return [Bar.model_validate(record) for record in records]

    def save_corporate_actions(self, instrument: Instrument, actions: list[dict[str, Any]]) -> None:
        if self._bucket == "duckdb":
            self._store.save_corporate_actions(instrument.model_dump(mode="json"), actions)
            return

        records = self._actions_store.load({})
        key = self._instrument_key(instrument)
        merged = {self._action_key(row): row for row in records.get(key, [])}
        for row in actions:
            merged[self._action_key(row)] = row
        records[key] = sorted(merged.values(), key=self._action_sort_key)
        self._actions_store.save(records)

    def load_corporate_actions(self, instrument: Instrument, start: date, end: date) -> list[dict[str, Any]]:
        if self._bucket == "duckdb":
            return self._store.load_corporate_actions(instrument.symbol, instrument.market.value, start, end)
        records = self._actions_store.load({}).get(self._instrument_key(instrument), [])
        return [
            row
            for row in records
            if start.isoformat() <= self._action_sort_key(row) <= end.isoformat()
        ]

    def save_fx_rates(self, rates: list[FxRate]) -> None:
        payload = [rate.model_dump(mode="json") for rate in rates]
        if self._bucket == "duckdb":
            self._store.save_fx_rates(payload)
            return
        records = self._fx_store.load({})
        for row in payload:
            key = self._fx_key(row["base_currency"], row["quote_currency"])
            merged = {item["date"]: item for item in records.get(key, [])}
            merged[row["date"]] = row
            records[key] = sorted(merged.values(), key=lambda item: item["date"])
        self._fx_store.save(records)

    def load_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        if self._bucket == "duckdb":
            records = self._store.load_fx_rates(base_currency, quote_currency, start, end)
        else:
            records = self._fx_store.load({}).get(self._fx_key(base_currency, quote_currency), [])
            records = [row for row in records if start.isoformat() <= str(row["date"]) <= end.isoformat()]
        return [FxRate.model_validate(record) for record in records]

    def clear(self) -> None:
        if self._bucket == "duckdb":
            self._store.clear_all()
            return
        self._bars_store.save({})
        self._actions_store.save({})
        self._fx_store.save({})

    def _instrument_key(self, instrument: Instrument) -> str:
        return f"{instrument.market.value}:{instrument.symbol}"

    def _action_key(self, row: dict[str, Any]) -> str:
        return json.dumps(row, sort_keys=True, ensure_ascii=True)

    def _action_sort_key(self, row: dict[str, Any]) -> str:
        return str(row.get("ex_div_date") or row.get("record_date") or row.get("effective_date") or "0000-00-00")

    def _fx_key(self, base_currency: str, quote_currency: str) -> str:
        return f"{base_currency.upper()}/{quote_currency.upper()}"
