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


def test_research_queries_follow_recovered_strategy_registry(tmp_path):
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

    detail = app.research_facade.strategy_detail("strategy_a_etf_rotation", date(2026, 3, 8))

    assert detail["signals"][0]["symbol"] == "ZZTOP"


def test_research_readiness_uses_experiment_inspection_instead_of_full_reporting(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    original = app.strategy_analysis.summarize_strategy_report
    try:
        app.strategy_analysis.summarize_strategy_report = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("full report should not run"))  # type: ignore[method-assign]

        summary = app.research_readiness_summary(date(2026, 3, 8))

        assert "strategies" in summary
        assert summary["report_status"] in {"ready", "blocked"}
    finally:
        app.strategy_analysis.summarize_strategy_report = original


def test_research_readiness_limits_gate_to_default_execution_strategies(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    provider = app.strategy_signal_provider
    original_map = provider.strategy_signal_map
    original_inspect = app.research.experiment_service.inspect_strategy_readiness
    captured: dict[str, object] = {}
    try:
        def fake_signal_map(as_of: date, *, strategy_ids=None, local_history_only: bool = False):
            captured["strategy_ids"] = list(strategy_ids or [])
            captured["local_history_only"] = local_history_only
            return {strategy_id: [] for strategy_id in list(strategy_ids or [])}

        provider.strategy_signal_map = fake_signal_map  # type: ignore[method-assign]
        app.research.experiment_service.inspect_strategy_readiness = lambda strategy_id, as_of, signals, strategy=None: {
            "strategy_id": strategy_id,
            "data_source": "historical",
            "data_ready": True,
            "promotion_blocked": False,
            "blocking_reasons": [],
            "minimum_coverage_ratio": 1.0,
            "validation_status": "ready",
        }  # type: ignore[method-assign]

        summary = app.research_readiness_summary(date(2026, 3, 8))

        assert captured["strategy_ids"] == [
            "strategy_a_etf_rotation",
            "strategy_b_equity_momentum",
            "strategy_c_option_overlay",
        ]
        assert captured["local_history_only"] is True
        assert summary["blocked_count"] == 0
        assert len(summary["strategies"]) == 3
    finally:
        provider.strategy_signal_map = original_map  # type: ignore[method-assign]
        app.research.experiment_service.inspect_strategy_readiness = original_inspect  # type: ignore[method-assign]


def test_research_readiness_avoids_remote_market_data_fetches(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    original_fetch_bars = app.market_history.fetch_bars
    original_sync_fx_rates = app.market_history.sync_fx_rates
    original_fetch_corporate_actions = app.market_history._adapter.fetch_corporate_actions
    try:
        app.market_history.fetch_bars = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("readiness should not fetch bars"))  # type: ignore[method-assign]
        app.market_history.sync_fx_rates = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("readiness should not sync fx"))  # type: ignore[method-assign]
        app.market_history._adapter.fetch_corporate_actions = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("readiness should not fetch corporate actions"))  # type: ignore[method-assign]

        summary = app.research_readiness_summary(date(2026, 3, 8))

        assert "strategies" in summary
        assert summary["report_status"] in {"ready", "blocked"}
    finally:
        app.market_history.fetch_bars = original_fetch_bars
        app.market_history.sync_fx_rates = original_sync_fx_rates
        app.market_history._adapter.fetch_corporate_actions = original_fetch_corporate_actions


def test_base_validation_snapshot_reuses_cached_preflight_snapshot(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    app.startup_preflight_summary(date(2026, 3, 8))
    original = app.readiness_queries.startup_preflight_summary
    try:
        app.readiness_queries.startup_preflight_summary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should reuse cached preflight"))  # type: ignore[method-assign]

        snapshot = app._base_validation_snapshot(date(2026, 3, 8))

        assert "preflight" in snapshot
        assert snapshot["preflight"]["research_readiness"]["as_of"] == date(2026, 3, 8)
    finally:
        app.readiness_queries.startup_preflight_summary = original
