from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Request

from tradingcat.api.schemas import FxSyncPayload, HistoryRepairPayload, HistorySyncPayload, MarketDataSmokePayload
from tradingcat.domain.models import Market
from tradingcat.routes.common import get_app_state, split_csv_param


router = APIRouter()


@router.post("/market-data/smoke-test")
def market_data_smoke_test(request: Request, payload: MarketDataSmokePayload):
    return get_app_state(request).run_market_data_smoke_test(
        symbols=payload.symbols,
        include_bars=payload.include_bars,
        include_option_chain=payload.include_option_chain,
    )


@router.get("/data/instruments")
def data_instruments(request: Request):
    return get_app_state(request).market_history.list_instruments()


@router.post("/data/history/sync")
def data_history_sync(request: Request, payload: HistorySyncPayload):
    return get_app_state(request).sync_market_history(
        symbols=payload.symbols,
        start=payload.start,
        end=payload.end,
        include_corporate_actions=payload.include_corporate_actions,
    )


@router.get("/data/history/bars")
async def data_history_bars(request: Request, symbol: str, start: date, end: date):
    return await get_app_state(request).market_history.get_bars_async(symbol, start, end)


@router.get("/data/history/coverage")
def data_history_coverage(request: Request, symbols: str | None = None, start: date | None = None, end: date | None = None):
    return get_app_state(request).market_history.summarize_history_coverage(split_csv_param(symbols), start, end)


@router.get("/data/history/sync-runs")
def data_history_sync_runs(request: Request):
    return get_app_state(request).history_sync.list_runs()


@router.get("/data/history/sync-status")
def data_history_sync_status(request: Request):
    return get_app_state(request).history_sync.summary()


@router.get("/data/history/repair-plan")
def data_history_repair_plan(request: Request, symbols: str | None = None, start: date | None = None, end: date | None = None):
    return get_app_state(request).history_sync_repair_plan(split_csv_param(symbols), start, end)


@router.post("/data/history/repair")
def data_history_repair(request: Request, payload: HistoryRepairPayload):
    return get_app_state(request).repair_market_history_gaps(
        symbols=payload.symbols,
        start=payload.start,
        end=payload.end,
        include_corporate_actions=payload.include_corporate_actions,
    )


@router.post("/data/fx/sync")
def data_fx_sync(request: Request, payload: FxSyncPayload):
    return get_app_state(request).market_history.sync_fx_rates(
        base_currency=payload.base_currency,
        quote_currencies=payload.quote_currencies,
        start=payload.start,
        end=payload.end,
    )


@router.get("/data/fx/rates")
def data_fx_rates(request: Request, base_currency: str, quote_currency: str, start: date, end: date):
    return get_app_state(request).market_history.get_fx_rates(base_currency, quote_currency, start, end)


@router.get("/data/quality")
def data_quality(request: Request, lookback_days: int = 30):
    return get_app_state(request).data_quality_summary(lookback_days)


@router.get("/data/history/corporate-actions")
def data_history_corporate_actions(request: Request, symbol: str, start: date, end: date):
    return get_app_state(request).market_history.get_corporate_actions(symbol, start, end)


@router.get("/market-sessions")
def market_sessions(request: Request):
    app = get_app_state(request)
    now = datetime.now(UTC)
    return {
        market.value: app.market_calendar.get_session(market, now=now).model_dump(mode="json")
        for market in (Market.US, Market.HK, Market.CN)
    }
