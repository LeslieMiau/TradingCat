from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/alerts")


@router.get("")
def alerts(request: Request):
    return get_app_state(request).alerts.list_alerts()


@router.get("/summary")
def alerts_summary(request: Request):
    return get_app_state(request).alerts.latest_summary()


@router.post("/evaluate")
def alerts_evaluate(request: Request):
    app = get_app_state(request)
    broker_status_payload = app.broker_status()
    broker_validation = app.broker_validation()
    market_data = app.run_market_data_smoke_test()
    execution_reconciliation = app.execution.reconcile_live_state()
    portfolio_reconciliation = app.portfolio.reconcile_with_broker(app._live_broker)
    return app.alerts.evaluate(
        broker_status_payload,
        broker_validation,
        market_data,
        execution_reconciliation,
        portfolio_reconciliation,
    )

