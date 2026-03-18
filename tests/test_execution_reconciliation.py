from tradingcat.adapters.broker import ManualExecutionAdapter, SimulatedBrokerAdapter
from tradingcat.domain.models import AssetClass, Instrument, ManualFill, Market, OrderIntent, OrderSide
from tradingcat.repositories.state import ApprovalRepository, ExecutionStateRepository, OrderRepository
from tradingcat.services.approval import ApprovalService
from tradingcat.services.execution import ExecutionService


def test_execution_reconcile_deduplicates_repeated_fills(tmp_path):
    service = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    intent = OrderIntent(
        signal_id="sig-1",
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        quantity=10,
    )

    service.submit(intent)
    first = service.reconcile_live_state()
    second = service.reconcile_live_state()

    assert first.fill_updates >= 1
    assert second.duplicate_fills >= 1
    assert second.fill_updates == 0
    assert service.order_state_summary()["submitted"] >= 1


def test_execution_quality_summary_tracks_threshold_breaches(tmp_path):
    service = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    intent = OrderIntent(
        signal_id="sig-quality",
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        quantity=10,
    )

    service.register_expected_prices([intent], {"SPY": 100.0})
    service.reconcile_manual_fill(
        ManualFill(
            order_intent_id=intent.id,
            broker_order_id="manual-quality",
            filled_quantity=10.0,
            average_price=100.5,
            notes="seed fill",
        )
    )

    summary = service.execution_quality_summary()

    assert summary["filled_samples"] == 1
    assert summary["equity_breaches"] == 1
    assert summary["within_limits"] is False


def test_execution_authorization_summary_marks_pending_and_auto_orders(tmp_path):
    service = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    auto_intent = OrderIntent(
        signal_id="auto",
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        quantity=1,
    )
    manual_intent = OrderIntent(
        signal_id="manual",
        instrument=Instrument(symbol="510300", market=Market.CN, asset_class=AssetClass.ETF, currency="CNY"),
        side=OrderSide.BUY,
        quantity=100,
        requires_approval=True,
    )

    service.submit(auto_intent)
    service.submit(manual_intent)
    summary = service.authorization_summary()

    assert summary["order_count"] == 2
    assert summary["authorized_count"] == 2
    assert summary["unauthorized_count"] == 0
