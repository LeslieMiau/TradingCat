from tradingcat.adapters.broker import ManualExecutionAdapter, SimulatedBrokerAdapter
from tradingcat.domain.models import (
    AssetClass,
    ExecutionReport,
    Instrument,
    ManualFill,
    Market,
    OrderIntent,
    OrderSide,
    OrderStatus,
    Position,
)
from tradingcat.repositories.state import ApprovalRepository, ExecutionStateRepository, OrderRepository
from tradingcat.services.approval import ApprovalService
from tradingcat.services.execution import ExecutionService
from tradingcat.services.reconciliation import ReconciliationService
from tradingcat.services.order_state_machine import OrderStateMachine


class _FakeBroker:
    """Minimal broker double that lets tests script the fills stream."""

    def __init__(self, orders: list[ExecutionReport], fills: list[ExecutionReport]) -> None:
        self._orders = list(orders)
        self._fills = list(fills)

    def get_orders(self) -> list[ExecutionReport]:
        return list(self._orders)

    def get_positions(self) -> list[Position]:
        return []

    def get_cash(self) -> float:
        return 0.0

    def get_cash_by_market(self) -> dict[Market, float]:
        return {}

    def place_order(self, intent: OrderIntent) -> ExecutionReport:  # pragma: no cover - unused
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> ExecutionReport:  # pragma: no cover - unused
        raise NotImplementedError

    def reconcile_fills(self) -> list[ExecutionReport]:
        return list(self._fills)


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
    assert summary["stock_samples"] == 0
    assert summary["etf_samples"] == 1
    assert summary["equity_breaches"] == 1
    assert summary["etf_breaches"] == 1
    assert summary["within_limits"] is False
    assert summary["samples"][0]["reference_source"] == "market_quote"
    assert summary["asset_class_summary"]["etf"]["severity"] == "warning"
    assert summary["asset_class_summary"]["option"]["severity"] == "insufficient_data"


def test_execution_quality_summary_groups_samples_by_asset_class(tmp_path):
    service = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    stock_intent = OrderIntent(
        signal_id="sig-stock-quality",
        instrument=Instrument(symbol="MSFT", market=Market.US, asset_class=AssetClass.STOCK, currency="USD"),
        side=OrderSide.BUY,
        quantity=5,
    )
    etf_intent = OrderIntent(
        signal_id="sig-etf-quality",
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        quantity=5,
    )

    service.register_expected_prices([stock_intent, etf_intent], {"MSFT": 100.0, "SPY": 200.0})
    service.reconcile_manual_fill(
        ManualFill(
            order_intent_id=stock_intent.id,
            broker_order_id="manual-stock-quality",
            filled_quantity=5.0,
            average_price=100.1,
        )
    )
    service.reconcile_manual_fill(
        ManualFill(
            order_intent_id=etf_intent.id,
            broker_order_id="manual-etf-quality",
            filled_quantity=5.0,
            average_price=200.8,
        )
    )

    summary = service.execution_quality_summary()

    assert summary["stock_samples"] == 1
    assert summary["etf_samples"] == 1
    assert summary["asset_class_summary"]["stock"]["sample_count"] == 1
    assert summary["asset_class_summary"]["stock"]["severity"] == "info"
    assert summary["asset_class_summary"]["etf"]["sample_count"] == 1
    assert summary["asset_class_summary"]["etf"]["severity"] == "warning"
    assert summary["asset_class_summary"]["option"]["message"] == "No filled option samples available yet."


def test_transaction_cost_summary_exposes_sample_breakdown_and_direction(tmp_path):
    service = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    buy_intent = OrderIntent(
        signal_id="sig-buy-tca",
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        quantity=2,
    )
    sell_intent = OrderIntent(
        signal_id="sig-sell-tca",
        instrument=Instrument(symbol="MSFT", market=Market.US, asset_class=AssetClass.STOCK, currency="USD"),
        side=OrderSide.SELL,
        quantity=3,
    )

    service.register_expected_prices([buy_intent, sell_intent], {"SPY": 200.0, "MSFT": 100.0})
    service.reconcile_manual_fill(
        ManualFill(
            order_intent_id=buy_intent.id,
            broker_order_id="manual-buy-tca",
            filled_quantity=2.0,
            average_price=200.4,
        )
    )
    service.reconcile_manual_fill(
        ManualFill(
            order_intent_id=sell_intent.id,
            broker_order_id="manual-sell-tca",
            filled_quantity=3.0,
            average_price=99.8,
        )
    )

    summary = service.transaction_cost_summary()

    assert summary["sample_count"] == 2
    assert summary["filled_quantity"] == 5.0
    assert summary["direction_summary"]["buy"]["sample_count"] == 1
    assert summary["direction_summary"]["sell"]["sample_count"] == 1
    assert summary["samples"][0]["expected_price"] in {100.0, 200.0}
    assert summary["samples"][0]["realized_price"] in {99.8, 200.4}
    assert {sample["direction"] for sample in summary["samples"]} == {"buy", "sell"}


def test_execution_price_context_persists_expected_and_realized_price(tmp_path):
    service = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    intent = OrderIntent(
        signal_id="sig-price-context",
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        quantity=10,
    )

    service.register_expected_prices([intent], {"SPY": {"price": 100.0, "source": "execution_preview_quote"}})
    service.reconcile_manual_fill(
        ManualFill(
            order_intent_id=intent.id,
            broker_order_id="manual-price-context",
            filled_quantity=10.0,
            average_price=100.5,
            notes="seed fill",
        )
    )

    context = service.resolve_price_context(intent.id)

    assert context["expected_price"] == 100.0
    assert context["realized_price"] == 100.5
    assert context["reference_source"] == "execution_preview_quote"


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
    rows = {row["order_intent_id"]: row for row in summary["orders"]}

    assert summary["order_count"] == 2
    assert summary["authorized_count"] == 2
    assert summary["unauthorized_count"] == 0
    assert rows[auto_intent.id]["authorization_mode"] == "risk_approved"
    assert rows[auto_intent.id]["final_authorization_mode"] == "risk_approved"
    assert rows[manual_intent.id]["authorization_mode"] == "manual_pending"
    assert rows[manual_intent.id]["final_authorization_mode"] == "manual_pending"
    assert rows[manual_intent.id]["approval_request_id"] is not None


def test_execution_authorization_summary_links_external_fill_source_and_final_mode(tmp_path):
    service = ExecutionService(
        live_broker=SimulatedBrokerAdapter(),
        manual_broker=ManualExecutionAdapter(),
        approvals=ApprovalService(ApprovalRepository(tmp_path)),
        repository=OrderRepository(tmp_path),
        state_repository=ExecutionStateRepository(tmp_path),
    )
    manual_intent = OrderIntent(
        signal_id="manual-external-fill",
        instrument=Instrument(symbol="510300", market=Market.CN, asset_class=AssetClass.ETF, currency="CNY"),
        side=OrderSide.BUY,
        quantity=100,
        requires_approval=True,
    )

    service.submit(manual_intent)
    service.reconcile_manual_fill(
        ManualFill(
            order_intent_id=manual_intent.id,
            broker_order_id="import-cn-fill",
            external_source="broker_statement",
            filled_quantity=100.0,
            average_price=3.21,
        )
    )

    summary = service.authorization_summary()
    row = next(item for item in summary["orders"] if item["order_intent_id"] == manual_intent.id)

    assert row["approval_request_id"] is not None
    assert row["approval_status"] == "external_fill"
    assert row["authorization_mode"] == "manual_pending"
    assert row["final_authorization_mode"] == "manual_fill_external"
    assert row["external_source"] == "broker_statement"


def test_fill_fingerprint_prefers_fill_id_over_composite():
    service = ReconciliationService(OrderStateMachine())

    same_composite_a = ExecutionReport(
        order_intent_id="oi-1",
        broker_order_id="ord-1",
        fill_id="deal-A",
        status=OrderStatus.FILLED,
        filled_quantity=100.0,
        average_price=50.0,
    )
    same_composite_b = ExecutionReport(
        order_intent_id="oi-1",
        broker_order_id="ord-1",
        fill_id="deal-B",
        status=OrderStatus.FILLED,
        filled_quantity=100.0,
        average_price=50.0,
    )

    assert service.fill_fingerprint(same_composite_a) != service.fill_fingerprint(same_composite_b)
    assert service.fill_fingerprint(same_composite_a) == "fill:deal-A"

    no_id = ExecutionReport(
        order_intent_id="oi-2",
        broker_order_id="ord-2",
        status=OrderStatus.FILLED,
        filled_quantity=100.0,
        average_price=50.0,
    )
    assert "fill:" not in service.fill_fingerprint(no_id)


def test_reconcile_live_state_counts_distinct_fill_ids_with_same_qty_price():
    state_machine = OrderStateMachine()
    service = ReconciliationService(state_machine)

    order_report = ExecutionReport(
        order_intent_id="oi-1",
        broker_order_id="ord-1",
        status=OrderStatus.SUBMITTED,
        filled_quantity=0.0,
    )
    fill_one = ExecutionReport(
        order_intent_id="oi-1",
        broker_order_id="ord-1",
        fill_id="deal-A",
        status=OrderStatus.FILLED,
        filled_quantity=100.0,
        average_price=50.0,
    )
    fill_two = ExecutionReport(
        order_intent_id="oi-1",
        broker_order_id="ord-1",
        fill_id="deal-B",
        status=OrderStatus.FILLED,
        filled_quantity=100.0,
        average_price=50.0,
    )

    broker = _FakeBroker(orders=[order_report], fills=[fill_one, fill_two])
    summary, _, fingerprints = service.reconcile_live_state(
        live_broker=broker,
        orders={"oi-1": order_report},
        fill_fingerprints=set(),
    )

    assert summary.fill_updates == 2, "two distinct fill_ids should both be applied"
    assert summary.duplicate_fills == 0
    assert {"fill:deal-A", "fill:deal-B"} <= fingerprints


def test_reconcile_live_state_deduplicates_replayed_fill_id():
    state_machine = OrderStateMachine()
    service = ReconciliationService(state_machine)

    order_report = ExecutionReport(
        order_intent_id="oi-1",
        broker_order_id="ord-1",
        status=OrderStatus.SUBMITTED,
    )
    deal = ExecutionReport(
        order_intent_id="oi-1",
        broker_order_id="ord-1",
        fill_id="deal-A",
        status=OrderStatus.FILLED,
        filled_quantity=100.0,
        average_price=50.0,
    )

    broker = _FakeBroker(orders=[order_report], fills=[deal, deal])
    summary, _, fingerprints = service.reconcile_live_state(
        live_broker=broker,
        orders={"oi-1": order_report},
        fill_fingerprints=set(),
    )

    assert summary.fill_updates == 1
    assert summary.duplicate_fills == 1
    assert fingerprints == {"fill:deal-A"}
