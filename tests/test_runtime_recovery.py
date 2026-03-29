from datetime import date

from tradingcat.config import AppConfig, FutuConfig
from tradingcat.domain.models import Signal
from tradingcat.main import TradingCatApplication


def test_runtime_recovery_rebuilds_runtime_components(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    original_runtime = app.runtime
    original_market_history = app.market_history
    original_execution = app.execution

    result = app.recover_runtime()

    assert result["attempted"] is True
    assert result["attempt"].trigger == "manual"
    assert app.runtime is not original_runtime
    assert app.market_history is not original_market_history
    assert app.execution is not original_execution
    assert result["after"]["live_broker_adapter"] == "SimulatedBrokerAdapter"
    assert app.recovery.summary()["count"] == 1


def test_application_runtime_container_exposes_runtime_services(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )

    assert app.runtime is not None
    assert app.market_history is app.runtime.market_history
    assert app.execution is app.runtime.execution
    assert app.research is app.runtime.research


def test_application_strategy_registry_is_stable_within_runtime(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )

    first = app.strategy_by_id("strategy_a_etf_rotation")
    second = app.strategy_by_id("strategy_a_etf_rotation")

    assert first is second
    assert app.runtime is not None
    assert app.runtime.strategy_registry.get("strategy_a_etf_rotation") is first
    assert any(strategy is first for strategy in app.research_strategies)


def test_application_strategy_signal_provider_uses_registry_instances(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )

    etf_strategy = app.strategy_by_id("strategy_a_etf_rotation")
    signal_map = app.strategy_signal_map(date(2026, 3, 8))

    assert app.runtime is not None
    assert app.runtime.strategy_signal_provider.execution_signals_for_strategy(etf_strategy, date(2026, 3, 8))
    assert "strategy_a_etf_rotation" in signal_map


def test_runtime_recovery_rebuilds_strategy_registry(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    original_strategy = app.strategy_by_id("strategy_a_etf_rotation")

    app.recover_runtime()

    recovered_strategy = app.strategy_by_id("strategy_a_etf_rotation")

    assert recovered_strategy is not original_strategy


def test_data_quality_queries_follow_recovered_strategy_registry(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    app.recover_runtime()
    recovered_strategy = app.strategy_by_id("strategy_a_etf_rotation")
    template_signal = recovered_strategy.generate_signals(date(2026, 3, 8))[0]

    def generate_unique_signals(as_of: date) -> list[Signal]:
        return [
            template_signal.model_copy(
                update={
                    "instrument": template_signal.instrument.model_copy(update={"symbol": "ZZTOP"}),
                }
            )
        ]

    recovered_strategy.generate_signals = generate_unique_signals  # type: ignore[method-assign]

    assert "ZZTOP" in app._repair_priority_symbols(as_of=date(2026, 3, 8))
