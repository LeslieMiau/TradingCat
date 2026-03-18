from tradingcat.domain.models import PortfolioReconciliationSummary, ReconciliationSummary
from tradingcat.repositories.state import AlertRepository
from tradingcat.services.alerts import AlertService


def test_alert_service_records_actionable_alerts(tmp_path):
    service = AlertService(AlertRepository(tmp_path))

    alerts = service.evaluate(
        broker_status={"backend": "futu", "healthy": False, "detail": "Trade context unhealthy"},
        broker_validation={"checks": {"quote": {"status": "ok"}, "trade": {"status": "failed", "detail": "unlock failed"}}},
        market_data_smoke_test={"failed_symbols": {"0700": "permission denied"}},
        execution_reconciliation=ReconciliationSummary(
            fill_updates=1,
            duplicate_fills=2,
            unmatched_broker_orders=1,
            state_counts={"submitted": 1},
        ),
        portfolio_reconciliation=PortfolioReconciliationSummary(
            broker_cash=900000,
            snapshot_cash=1000000,
            cash_difference=-100000,
            broker_position_count=1,
            snapshot_position_count=0,
            missing_symbols=[],
            unexpected_symbols=["SPY"],
        ),
    )

    assert len(alerts) >= 5
    summary = service.latest_summary()
    assert summary["count"] == len(alerts)
    assert summary["latest"] is not None
