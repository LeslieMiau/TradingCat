from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request, Query

from tradingcat.api.schemas import AssetCorrelationPayload, ResearchNewsSummaryPayload
from tradingcat.api.view_models import MarketAwarenessResponse, ResearchReportResponse, ResearchScorecardResponse, StrategyDetailResponse
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/research")


@router.get("/alpha-radar")
async def alpha_radar(request: Request, count: int = 15):
    return await get_app_state(request).alpha_radar.fetch_simulated_flow_async(count)


@router.get("/macro-calendar")
def macro_calendar_events(request: Request, days: int = 7):
    return get_app_state(request).macro_calendar.fetch_upcoming_events(days=days)


@router.post("/correlation")
async def asset_correlation(request: Request, payload: AssetCorrelationPayload):
    return await get_app_state(request).research_facade.asset_correlation(payload.symbols, payload.days)


@router.post("/backtests/run")
def research_backtests_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.run_backtests(as_of or date.today())


@router.get("/backtests")
def research_backtests(request: Request):
    return get_app_state(request).research.list_experiments()


@router.get("/backtests/compare")
def research_backtests_compare(request: Request, left_id: str, right_id: str):
    return get_app_state(request).research.compare_experiments(left_id, right_id)


@router.post("/report/run", response_model=ResearchReportResponse)
def research_report_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.report(as_of or date.today())


@router.post("/stability/run")
def research_stability_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.stability(as_of or date.today())


@router.get("/scorecard", response_model=ResearchScorecardResponse)
@router.post("/scorecard/run")
def research_scorecard_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.research_facade.scorecard(evaluation_date, include_candidates=False)


@router.get("/candidates/scorecard", response_model=ResearchScorecardResponse)
@router.post("/candidates/scorecard")
def research_candidates_scorecard(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.research_facade.scorecard(evaluation_date, include_candidates=True)


@router.post("/recommendations/run")
def research_recommendations_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.recommendations(as_of or date.today())


@router.get("/market-awareness", response_model=MarketAwarenessResponse)
@router.post("/market-awareness/run", response_model=MarketAwarenessResponse)
def research_market_awareness(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.market_awareness(as_of or date.today())


@router.post("/ideas/run")
def research_ideas_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.ideas(as_of or date.today())


@router.post("/news/summarize")
def research_news_summarize(request: Request, payload: ResearchNewsSummaryPayload):
    app = get_app_state(request)
    return app.research_facade.summarize_news([item.model_dump(mode="json") for item in payload.items])


@router.post("/selections/review")
def research_selections_review(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.review_selections(as_of or date.today())


@router.get("/selections")
def research_selections(request: Request):
    return get_app_state(request).selection.list_records()


@router.get("/selections/summary")
def research_selections_summary(request: Request):
    return get_app_state(request).selection.summary()


@router.post("/allocations/review")
def research_allocations_review(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.review_allocations(as_of or date.today())


@router.get("/allocations")
def research_allocations(request: Request):
    return get_app_state(request).allocations.list_records()


@router.get("/allocations/summary")
def research_allocations_summary(request: Request):
    return get_app_state(request).allocations.summary()


@router.get("/strategies/{strategy_id}", response_model=StrategyDetailResponse)
def research_strategy_detail(request: Request, strategy_id: str, as_of: date | None = None):
    app = get_app_state(request)
    return app.research_facade.strategy_detail(strategy_id, as_of or date.today())


# ---- Phase 1-3 service endpoints ----


@router.get("/features")
def research_features(
    request: Request,
    symbols: str = Query("SPY,QQQ", description="Comma-separated symbols"),
    days: int = 180,
):
    app = get_app_state(request)
    return app.research_facade.features([s.strip() for s in symbols.split(",") if s.strip()], days)


@router.get("/factors")
def research_factors(
    request: Request,
    symbols: str = Query("SPY,QQQ", description="Comma-separated symbols"),
    days: int = 180,
):
    app = get_app_state(request)
    return app.research_facade.factors([s.strip() for s in symbols.split(",") if s.strip()], days)


@router.post("/optimize")
def research_optimize(
    request: Request,
    symbols: str = Query(..., description="Comma-separated symbols"),
    method: str = "risk_parity",
):
    app = get_app_state(request)
    return app.research_facade.optimize(
        [s.strip() for s in symbols.split(",") if s.strip()],
        method,
    )


@router.get("/ml/predict")
def research_ml_predict(
    request: Request,
    symbols: str = Query("SPY,QQQ", description="Comma-separated symbols"),
):
    app = get_app_state(request)
    return app.research_facade.ml_predict([s.strip() for s in symbols.split(",") if s.strip()])


@router.get("/alternative")
def research_alternative(
    request: Request,
    symbols: str | None = Query(None, description="Comma-separated symbols (optional)"),
):
    app = get_app_state(request)
    parsed = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    return app.research_facade.alternative_data_snapshot(parsed)


@router.get("/ai/briefing")
def research_ai_briefing(request: Request):
    app = get_app_state(request)
    return app.research_facade.ai_briefing()


@router.post("/auto-research/run")
def research_auto_run(request: Request):
    app = get_app_state(request)
    return app.research_facade.auto_research_report()


@router.get("/auto-research/latest")
def research_auto_latest(request: Request):
    app = get_app_state(request)
    report = app.auto_research.latest_report()
    return report or {"error": "no reports available"}


@router.get("/attribution")
def research_attribution(request: Request, start: date, end: date):
    app = get_app_state(request)
    return app.research_facade.attribution(start, end)
