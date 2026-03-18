from tradingcat.config import AppConfig, FutuConfig
from tradingcat.main import TradingCatApplication


def test_runtime_recovery_rebuilds_runtime_components(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    original_market_history = app.market_history
    original_execution = app.execution

    result = app.recover_runtime()

    assert result["attempted"] is True
    assert result["attempt"].trigger == "manual"
    assert app.market_history is not original_market_history
    assert app.execution is not original_execution
    assert result["after"]["live_broker_adapter"] == "SimulatedBrokerAdapter"
    assert app.recovery.summary()["count"] == 1
