from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request

from tradingcat.api.schemas import AssetCorrelationPayload, ResearchNewsSummaryPayload
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
    end = date.today()
    start = end - timedelta(days=payload.days)
    return await get_app_state(request).strategy_analysis.calculate_asset_correlation_async(payload.symbols, start, end)


@router.post("/backtests/run")
def research_backtests_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    experiments = []
    for strategy in app.research_strategies:
        experiments.append(app.research.run_experiment(strategy.strategy_id, evaluation_date, strategy.generate_signals(evaluation_date)))
    return {"count": len(experiments), "experiments": experiments}


@router.get("/backtests")
def research_backtests(request: Request):
    return get_app_state(request).research.list_experiments()


@router.get("/backtests/compare")
def research_backtests_compare(request: Request, left_id: str, right_id: str):
    return get_app_state(request).research.compare_experiments(left_id, right_id)


@router.post("/report/run")
def research_report_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.strategy_analysis.summarize_strategy_report(evaluation_date, app._strategy_signal_map(evaluation_date))


@router.post("/stability/run")
def research_stability_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.strategy_analysis.summarize_strategy_stability(evaluation_date, app._strategy_signal_map(evaluation_date))


@router.get("/scorecard")
@router.post("/scorecard/run")
def research_scorecard_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.strategy_analysis.build_profit_scorecard(evaluation_date, app._strategy_signal_map(evaluation_date))


@router.get("/candidates/scorecard")
@router.post("/candidates/scorecard")
def research_candidates_scorecard(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.strategy_analysis.build_profit_scorecard(
        evaluation_date,
        app._strategy_signal_map(evaluation_date, include_candidates=True),
    )


@router.post("/recommendations/run")
def research_recommendations_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.strategy_analysis.recommend_strategy_actions(evaluation_date, app._strategy_signal_map(evaluation_date, include_candidates=True))


@router.post("/ideas/run")
def research_ideas_run(request: Request, as_of: date | None = None):
    app = get_app_state(request)
    evaluation_date = as_of or date.today()
    return app.research_ideas.suggest_experiments(evaluation_date, app._strategy_signal_map(evaluation_date))


@router.post("/news/summarize")
def research_news_summarize(request: Request, payload: ResearchNewsSummaryPayload):
    return get_app_state(request).research_ideas.summarize_news([item.model_dump(mode="json") for item in payload.items])


@router.post("/selections/review")
def research_selections_review(request: Request, as_of: date | None = None):
    return get_app_state(request).review_strategy_selections(as_of or date.today())


@router.get("/selections")
def research_selections(request: Request):
    return get_app_state(request).selection.list_records()


@router.get("/selections/summary")
def research_selections_summary(request: Request):
    return get_app_state(request).selection.summary()


@router.post("/allocations/review")
def research_allocations_review(request: Request, as_of: date | None = None):
    return get_app_state(request).review_strategy_allocations(as_of or date.today())


@router.get("/allocations")
def research_allocations(request: Request):
    return get_app_state(request).allocations.list_records()


@router.get("/allocations/summary")
def research_allocations_summary(request: Request):
    return get_app_state(request).allocations.summary()


@router.get("/strategies/{strategy_id}")
def research_strategy_detail(request: Request, strategy_id: str, as_of: date | None = None):
    app = get_app_state(request)
    strategy = app.strategy_by_id(strategy_id)
    evaluation_date = as_of or date.today()
    return app.strategy_analysis.strategy_detail(strategy_id, evaluation_date, strategy.generate_signals(evaluation_date))

