from datetime import date, datetime, timedelta, timezone

from tradingcat.adapters.broker import ManualExecutionAdapter, SimulatedBrokerAdapter
from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.config import AppConfig
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market, OrderSide
from tradingcat.domain.triggers import SmartOrder, TriggerCondition
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.state import ApprovalRepository, ExecutionStateRepository, OrderRepository
from tradingcat.services.approval import ApprovalService
from tradingcat.services.execution import ExecutionService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.rule_engine import RuleEngine, TriggerRepository


class RisingBarsAdapter(StaticMarketDataAdapter):
    def fetch_bars(self, instrument, start, end):
        current = start
        price = 100.0
        bars: list[Bar] = []
        while current <= end:
            price += 1.5
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=datetime.combine(current, datetime.min.time(), tzinfo=timezone.utc),
                    open=price - 0.5,
                    high=price + 0.5,
                    low=price - 1.0,
                    close=price,
                    volume=1_000_000,
                )
            )
            current += timedelta(days=1)
        return bars


class FallingBarsAdapter(StaticMarketDataAdapter):
    def fetch_bars(self, instrument, start, end):
        current = start
        price = 140.0
        bars: list[Bar] = []
        while current <= end:
            price -= 1.5
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=datetime.combine(current, datetime.min.time(), tzinfo=timezone.utc),
                    open=price + 0.5,
                    high=price + 1.0,
                    low=price - 0.5,
                    close=price,
                    volume=1_000_000,
                )
            )
            current += timedelta(days=1)
        return bars


def _build_rule_engine(tmp_path, adapter):
    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=adapter,
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    execution = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    engine = RuleEngine(
        config,
        TriggerRepository(config),
        market_data=market_data,
        execution=execution,
    )
    return engine, market_data, execution


def test_rule_engine_uses_real_rsi_for_uptrend(tmp_path):
    engine, market_data, execution = _build_rule_engine(tmp_path, RisingBarsAdapter())
    end = date.today()
    market_data.sync_history(symbols=["SPY"], start=end - timedelta(days=30), end=end)
    order = SmartOrder(
        account="total",
        symbol="SPY",
        market="US",
        side=OrderSide.BUY,
        quantity=1,
        trigger_conditions=[TriggerCondition(metric="RSI_14", operator=">", target_value=70)],
    )
    engine.register_order(order)

    rsi_value = engine._metric_value("RSI_14", "SPY", Market.US, 100.0)
    result = engine.evaluate_all()

    assert rsi_value > 70
    assert rsi_value != 30.0
    assert result["triggered"] == 1
    order = engine.list_orders()[0]
    assert order.status == "TRIGGERED"
    assert order.evaluation_summary["all_conditions_met"] is True
    assert order.evaluation_summary["conditions"][0]["metric"] == "RSI_14"
    report = execution.list_orders()[0]
    context = execution.resolve_intent_context(report.order_intent_id)
    assert context["trigger_context"]["conditions"][0]["metric"] == "RSI_14"


def test_rule_engine_keeps_order_pending_when_rsi_is_oversold(tmp_path, caplog):
    engine, market_data, _ = _build_rule_engine(tmp_path, FallingBarsAdapter())
    end = date.today()
    market_data.sync_history(symbols=["SPY"], start=end - timedelta(days=30), end=end)
    order = SmartOrder(
        account="total",
        symbol="SPY",
        market="US",
        side=OrderSide.BUY,
        quantity=1,
        trigger_conditions=[TriggerCondition(metric="RSI_14", operator=">", target_value=70)],
    )
    engine.register_order(order)

    rsi_value = engine._metric_value("RSI_14", "SPY", Market.US, 100.0)
    with caplog.at_level("INFO"):
        result = engine.evaluate_all()

    assert rsi_value < 30
    assert result["triggered"] == 0
    assert engine.list_orders()[0].status == "PENDING"
    assert engine.list_orders()[0].evaluation_summary["conditions"][0]["passed"] is False
    assert result["results"][0]["reasons"][0]["reason_type"] == "indicator_not_met"
    assert any(record.metric == "RSI_14" and record.value == rsi_value for record in caplog.records)


def test_rule_engine_uses_real_sma_for_uptrend(tmp_path):
    engine, market_data, execution = _build_rule_engine(tmp_path, RisingBarsAdapter())
    end = date.today()
    market_data.sync_history(symbols=["SPY"], start=end - timedelta(days=30), end=end)
    order = SmartOrder(
        account="total",
        symbol="SPY",
        market="US",
        side=OrderSide.BUY,
        quantity=1,
        trigger_conditions=[TriggerCondition(metric="SMA_10", operator=">", target_value=120)],
    )
    engine.register_order(order)

    sma_value = engine._metric_value("SMA_10", "SPY", Market.US, 100.0)
    result = engine.evaluate_all()

    assert sma_value > 120
    assert sma_value != 95.0
    assert result["triggered"] == 1
    order = engine.list_orders()[0]
    assert order.status == "TRIGGERED"
    assert order.evaluation_summary["conditions"][0]["metric"] == "SMA_10"
    report = execution.list_orders()[0]
    context = execution.resolve_intent_context(report.order_intent_id)
    assert context["trigger_context"]["conditions"][0]["metric"] == "SMA_10"


def test_rule_engine_logs_real_sma_when_condition_is_not_met(tmp_path, caplog):
    engine, market_data, _ = _build_rule_engine(tmp_path, FallingBarsAdapter())
    end = date.today()
    market_data.sync_history(symbols=["SPY"], start=end - timedelta(days=30), end=end)
    order = SmartOrder(
        account="total",
        symbol="SPY",
        market="US",
        side=OrderSide.BUY,
        quantity=1,
        trigger_conditions=[TriggerCondition(metric="SMA_10", operator=">", target_value=120)],
    )
    engine.register_order(order)

    sma_value = engine._metric_value("SMA_10", "SPY", Market.US, 100.0)
    with caplog.at_level("INFO"):
        result = engine.evaluate_all()

    assert sma_value < 120
    assert result["triggered"] == 0
    assert engine.list_orders()[0].status == "PENDING"
    assert engine.list_orders()[0].evaluation_summary["conditions"][0]["passed"] is False
    assert result["results"][0]["reasons"][0]["reason_type"] == "indicator_not_met"
    assert any(record.metric == "SMA_10" and record.value == sma_value for record in caplog.records)


def test_rule_engine_marks_indicator_data_missing_when_history_is_unavailable(tmp_path):
    engine, _, _ = _build_rule_engine(tmp_path, StaticMarketDataAdapter())
    order = SmartOrder(
        account="total",
        symbol="UNKNOWN",
        market="US",
        side=OrderSide.BUY,
        quantity=1,
        trigger_conditions=[TriggerCondition(metric="RSI_14", operator=">", target_value=60)],
    )
    engine.register_order(order)

    result = engine.evaluate_all()

    assert result["triggered"] == 0
    assert result["results"][0]["reasons"][0]["reason_type"] == "data_missing"
    assert "needs 15 closes" in result["results"][0]["reasons"][0]["reason"]
