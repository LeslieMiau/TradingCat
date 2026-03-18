from datetime import date

from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.config import AppConfig, DuckDbConfig
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.state import HistorySyncRunRepository
from tradingcat.services.data_sync import HistorySyncService
from tradingcat.services.market_data import MarketDataService


def test_market_data_service_syncs_and_reads_history_json(tmp_path):
    service = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )

    sync = service.sync_history(symbols=["SPY"], start=date(2026, 3, 1), end=date(2026, 3, 3))
    bars = service.get_bars("SPY", date(2026, 3, 1), date(2026, 3, 3))
    actions = service.get_corporate_actions("SPY", date(2026, 3, 1), date(2026, 3, 3))

    assert sync["instrument_count"] == 1
    assert sync["reports"][0]["bar_count"] == 3
    assert len(service.list_instruments()) >= 4
    assert len(bars) == 3
    assert actions == []


def test_market_data_service_exports_duckdb_parquet(tmp_path):
    config = AppConfig(
        data_dir=tmp_path,
        duckdb=DuckDbConfig(
            enabled=True,
            path=tmp_path / "research.duckdb",
            parquet_dir=tmp_path / "parquet",
        ),
    )
    service = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )

    service.sync_history(symbols=["0700"], start=date(2026, 3, 5), end=date(2026, 3, 6))
    bars = service.get_bars("0700", date(2026, 3, 5), date(2026, 3, 6))

    assert len(bars) == 2
    assert (tmp_path / "parquet" / "instruments.parquet").exists()
    assert (tmp_path / "parquet" / "price_bars.parquet").exists()
    assert (tmp_path / "parquet" / "corporate_actions.parquet").exists()


def test_market_data_service_summarizes_history_coverage(tmp_path):
    service = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )

    service.sync_history(symbols=["SPY"], start=date(2026, 3, 2), end=date(2026, 3, 6))
    coverage = service.summarize_history_coverage(symbols=["SPY"], start=date(2026, 3, 2), end=date(2026, 3, 6))

    assert coverage["instrument_count"] == 1
    assert coverage["expected_trading_days"] == 5
    assert coverage["complete_instruments"] == 1
    assert coverage["reports"][0]["coverage_ratio"] == 1.0


def test_market_data_service_repairs_missing_history(tmp_path):
    service = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )

    repaired = service.repair_history_gaps(symbols=["SPY"], start=date(2026, 3, 2), end=date(2026, 3, 6))

    assert repaired["repair_count"] == 1
    assert repaired["repaired_symbols"] == ["SPY"]


def test_market_data_service_sync_history_tolerates_symbol_failures(tmp_path):
    class PartialFailureAdapter(StaticMarketDataAdapter):
        def fetch_bars(self, instrument, start, end):
            if instrument.symbol == "QQQ":
                raise RuntimeError("quote permission missing")
            return super().fetch_bars(instrument, start, end)

    service = MarketDataService(
        adapter=PartialFailureAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )

    sync = service.sync_history(symbols=["SPY", "QQQ"], start=date(2026, 3, 2), end=date(2026, 3, 3))

    assert len(sync["reports"]) == 1
    assert sync["reports"][0]["symbol"] == "SPY"
    assert sync["failure_count"] == 1
    assert sync["failures"][0]["symbol"] == "QQQ"


def test_market_data_service_coverage_uses_observed_market_days(tmp_path):
    class HolidayAwareAdapter(StaticMarketDataAdapter):
        def fetch_bars(self, instrument, start, end):
            bars = super().fetch_bars(instrument, start, end)
            skipped = {"2026-02-17", "2026-02-18", "2026-02-19"}
            return [bar for bar in bars if bar.timestamp.date().isoformat() not in skipped]

    service = MarketDataService(
        adapter=HolidayAwareAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )

    service.sync_history(symbols=["0700"], start=date(2026, 2, 1), end=date(2026, 3, 8))
    coverage = service.summarize_history_coverage(symbols=["0700"], start=date(2026, 2, 1), end=date(2026, 3, 8))

    assert coverage["complete_instruments"] == 1
    assert coverage["reports"][0]["coverage_ratio"] == 1.0
    assert coverage["reports"][0]["missing_count"] == 0


def test_market_data_service_syncs_and_reads_fx_rates(tmp_path):
    service = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )

    synced = service.sync_fx_rates(
        base_currency="CNY",
        quote_currencies=["USD", "HKD"],
        start=date(2026, 3, 2),
        end=date(2026, 3, 6),
    )
    rates = service.get_fx_rates("CNY", "USD", date(2026, 3, 2), date(2026, 3, 6))

    assert synced["rate_count"] == 2
    assert len(rates) == 1
    assert rates[0].base_currency == "CNY"
    assert rates[0].quote_currency == "USD"


def test_history_sync_service_records_runs_and_repair_plan(tmp_path):
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    history_sync = HistorySyncService(HistorySyncRunRepository(tmp_path))

    sync = market_data.sync_history(symbols=["SPY"], start=date(2026, 3, 2), end=date(2026, 3, 6))
    coverage = market_data.summarize_history_coverage(symbols=["SPY"], start=date(2026, 3, 2), end=date(2026, 3, 6))
    run = history_sync.record_run(
        sync_result=sync,
        coverage_result=coverage,
        symbols=["SPY"],
        include_corporate_actions=True,
    )

    summary = history_sync.summary()
    repair = history_sync.repair_plan(coverage)

    assert run.status == "ok"
    assert summary["count"] == 1
    assert summary["healthy"] is True
    assert repair["repair_count"] == 0
