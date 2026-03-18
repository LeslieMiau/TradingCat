from datetime import date

from tradingcat.config import AppConfig, DuckDbConfig
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.services.research import ResearchService
from tradingcat.strategies.simple import EtfRotationStrategy


def test_duckdb_research_repository_persists_and_exports_parquet(tmp_path):
    config = AppConfig(
        data_dir=tmp_path,
        duckdb=DuckDbConfig(
            enabled=True,
            path=tmp_path / "research.duckdb",
            parquet_dir=tmp_path / "parquet",
        ),
    )
    repository = BacktestExperimentRepository(config)
    service = ResearchService(repository)

    strategy = EtfRotationStrategy()
    signals = strategy.generate_signals(date(2026, 3, 8))
    experiment = service.run_experiment(strategy.strategy_id, date(2026, 3, 8), signals)

    reloaded = BacktestExperimentRepository(config).load()

    assert experiment.id in reloaded
    assert reloaded[experiment.id].metrics.annualized_return == experiment.metrics.annualized_return
    assert reloaded[experiment.id].window_count == experiment.window_count
    assert (tmp_path / "research.duckdb").exists()
    assert (tmp_path / "parquet" / "backtest_experiments.parquet").exists()
