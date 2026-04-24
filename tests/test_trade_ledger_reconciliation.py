from datetime import UTC, date, datetime, timedelta

from tradingcat.config import AppConfig, FutuConfig
from tradingcat.domain.models import (
    AssetClass,
    ExecutionReport,
    Market,
    OrderSide,
    OrderStatus,
    TradeLedgerEntry,
)
from tradingcat.main import TradingCatApplication
from tradingcat.repositories.state import TradeLedgerReconciliationRunRepository
from tradingcat.services.trade_ledger_reconciliation import (
    TradeLedgerReconciliationService,
)


def _fill(
    *,
    order_intent_id: str,
    broker_order_id: str = "",
    fill_id: str = "",
    filled_quantity: float = 100.0,
    average_price: float = 10.0,
    timestamp: datetime | None = None,
    status: OrderStatus = OrderStatus.FILLED,
    market: Market = Market.US,
) -> ExecutionReport:
    return ExecutionReport(
        order_intent_id=order_intent_id,
        broker_order_id=broker_order_id or f"BRK-{order_intent_id}",
        fill_id=fill_id or f"FIL-{order_intent_id}",
        status=status,
        filled_quantity=filled_quantity,
        average_price=average_price,
        timestamp=timestamp or datetime(2026, 4, 20, 14, 30, tzinfo=UTC),
        market=market,
    )


def _ledger_entry(
    *,
    order_intent_id: str,
    broker_order_id: str = "",
    fill_id: str = "",
    quantity: float = 100.0,
    price: float = 10.0,
    trade_dt: datetime | None = None,
    market: Market = Market.US,
) -> TradeLedgerEntry:
    ts = trade_dt or datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    gross = round(quantity * price, 6)
    return TradeLedgerEntry(
        order_intent_id=order_intent_id,
        broker_order_id=broker_order_id or f"BRK-{order_intent_id}",
        fill_id=fill_id or f"FIL-{order_intent_id}",
        trade_date=ts.date(),
        trade_datetime=ts,
        symbol="SPY",
        market=market,
        asset_class=AssetClass.STOCK,
        side=OrderSide.BUY,
        currency="USD",
        quantity=quantity,
        price=price,
        gross_amount=gross,
        net_amount=-gross,
    )


def _make_service(
    tmp_path,
    *,
    reports: list[ExecutionReport] | None = None,
    entries: list[TradeLedgerEntry] | None = None,
) -> TradeLedgerReconciliationService:
    reports_list = list(reports or [])
    entries_list = list(entries or [])

    def _list_orders() -> list[ExecutionReport]:
        return list(reports_list)

    def _build_entries(*, start=None, end=None, market=None) -> list[TradeLedgerEntry]:
        out = []
        for entry in entries_list:
            if start and entry.trade_date < start:
                continue
            if end and entry.trade_date > end:
                continue
            if market and entry.market != market:
                continue
            out.append(entry)
        return out

    return TradeLedgerReconciliationService(
        TradeLedgerReconciliationRunRepository(tmp_path),
        list_orders=_list_orders,
        build_ledger_entries=_build_entries,
    )


def test_capture_classifies_ok_when_every_fill_matches(tmp_path):
    report = _fill(order_intent_id="intent-1")
    entry = _ledger_entry(order_intent_id="intent-1")
    service = _make_service(tmp_path, reports=[report], entries=[entry])

    run = service.capture(as_of=date(2026, 4, 20))

    assert run.status == "ok"
    assert run.broker_fill_count == 1
    assert run.ledger_entry_count == 1
    assert run.missing_ledger_count == 0
    assert run.missing_broker_count == 0
    assert run.amount_drift_count == 0
    assert run.top_findings == []


def test_capture_flags_drift_when_ledger_missing_one_entry(tmp_path):
    report = _fill(order_intent_id="intent-1")
    service = _make_service(tmp_path, reports=[report], entries=[])

    run = service.capture(as_of=date(2026, 4, 20))

    assert run.status == "drift"
    assert run.missing_ledger_count == 1
    assert run.top_findings[0]["kind"] == "missing_ledger_entry"
    assert run.top_findings[0]["order_intent_id"] == "intent-1"


def test_capture_classifies_critical_on_large_amount_drift(tmp_path):
    report = _fill(order_intent_id="intent-1", filled_quantity=100, average_price=10.0)
    # Ledger gross diverges by 5% — beyond 1% critical threshold.
    entry = _ledger_entry(order_intent_id="intent-1", quantity=100, price=10.5)
    service = _make_service(tmp_path, reports=[report], entries=[entry])

    run = service.capture(as_of=date(2026, 4, 20))

    assert run.status == "critical"
    assert run.amount_drift_count == 1
    assert run.max_amount_drift_pct > 0.01
    top = run.top_findings[0]
    assert top["kind"] == "amount_drift"
    assert top["broker_gross"] == 1000.0
    assert top["ledger_gross"] == 1050.0


def test_capture_classifies_critical_on_many_incidents(tmp_path):
    reports = [_fill(order_intent_id=f"intent-{i}") for i in range(5)]
    service = _make_service(tmp_path, reports=reports, entries=[])

    run = service.capture(as_of=date(2026, 4, 20))

    assert run.status == "critical"
    assert run.missing_ledger_count == 5


def test_capture_only_considers_fills_on_as_of_date(tmp_path):
    today_report = _fill(
        order_intent_id="today",
        timestamp=datetime(2026, 4, 20, 14, 30, tzinfo=UTC),
    )
    yesterday_report = _fill(
        order_intent_id="yesterday",
        timestamp=datetime(2026, 4, 19, 14, 30, tzinfo=UTC),
    )
    entry = _ledger_entry(
        order_intent_id="today",
        trade_dt=datetime(2026, 4, 20, 14, 30, tzinfo=UTC),
    )
    service = _make_service(
        tmp_path, reports=[today_report, yesterday_report], entries=[entry]
    )

    run = service.capture(as_of=date(2026, 4, 20))

    assert run.broker_fill_count == 1
    assert run.status == "ok"


def test_capture_ignores_non_filled_reports(tmp_path):
    submitted = _fill(order_intent_id="sub", status=OrderStatus.SUBMITTED)
    service = _make_service(tmp_path, reports=[submitted], entries=[])

    run = service.capture(as_of=date(2026, 4, 20))

    assert run.broker_fill_count == 0
    assert run.status == "ok"


def test_capture_is_idempotent_per_day(tmp_path):
    report = _fill(order_intent_id="intent-1")
    entry = _ledger_entry(order_intent_id="intent-1")
    service = _make_service(tmp_path, reports=[report], entries=[entry])

    first = service.capture(as_of=date(2026, 4, 20), notes=["first"])
    second = service.capture(as_of=date(2026, 4, 20), notes=["second"])

    reloaded = _make_service(tmp_path, reports=[report], entries=[entry])
    runs = reloaded.list_runs()

    assert first.id == second.id
    assert len(runs) == 1
    assert runs[0].notes == ["second"]


def test_timeline_aggregates_status_counts(tmp_path):
    today = date.today()
    two_days_ago = today - timedelta(days=2)
    yesterday = today - timedelta(days=1)

    report_ok_old = _fill(
        order_intent_id="old",
        timestamp=datetime(two_days_ago.year, two_days_ago.month, two_days_ago.day, 14, 30, tzinfo=UTC),
    )
    entry_ok_old = _ledger_entry(
        order_intent_id="old",
        trade_dt=datetime(two_days_ago.year, two_days_ago.month, two_days_ago.day, 14, 30, tzinfo=UTC),
    )
    report_drift = _fill(
        order_intent_id="drift",
        timestamp=datetime(yesterday.year, yesterday.month, yesterday.day, 14, 30, tzinfo=UTC),
    )
    report_ok_today = _fill(
        order_intent_id="today",
        timestamp=datetime(today.year, today.month, today.day, 14, 30, tzinfo=UTC),
    )
    entry_ok_today = _ledger_entry(
        order_intent_id="today",
        trade_dt=datetime(today.year, today.month, today.day, 14, 30, tzinfo=UTC),
    )

    service_ok_old = _make_service(
        tmp_path, reports=[report_ok_old], entries=[entry_ok_old]
    )
    service_ok_old.capture(as_of=two_days_ago)

    # Ledger is silently dropping the yesterday fill → drift.
    service_drift = _make_service(tmp_path, reports=[report_drift], entries=[])
    service_drift.capture(as_of=yesterday)

    service_ok_today = _make_service(
        tmp_path, reports=[report_ok_today], entries=[entry_ok_today]
    )
    service_ok_today.capture(as_of=today)

    timeline = service_ok_today.timeline(window_days=7)
    summary = timeline["summary"]
    assert summary["run_count"] == 3
    assert summary["ok_count"] >= 1
    assert summary["drift_count"] >= 1
    assert summary["latest_status"] == "ok"


def test_application_exposes_reconciliation_service(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )
    payload = app.run_trade_ledger_reconciliation(as_of=date(2026, 4, 20))
    assert payload["status"] in {"ok", "drift", "critical"}
    assert payload["as_of"] == "2026-04-20"

    timeline = app.trade_ledger_reconciliation_timeline(window_days=7)
    assert timeline["window_days"] == 7
    assert timeline["summary"]["run_count"] >= 1


def test_scheduler_job_handler_runs(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )
    detail = app.scheduler_runtime.run_trade_ledger_reconciliation_job()
    assert detail.startswith("Trade ledger reconciliation")
