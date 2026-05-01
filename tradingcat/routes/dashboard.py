from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from tradingcat.api.view_models import DashboardSummaryResponse
from tradingcat.domain.models import Market
from tradingcat.routes.common import get_app_state, render_template

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/dashboard")


@router.get("", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return render_template(request, "dashboard.html")


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(request: Request, as_of: date | None = None):
    return get_app_state(request).dashboard_summary(as_of)


@router.get("/strategies/{strategy_id}", response_class=HTMLResponse)
def dashboard_strategy_page(request: Request, strategy_id: str):
    get_app_state(request).strategy_by_id(strategy_id)
    return render_template(request, "strategy.html")


@router.get("/accounts/{account_id}", response_class=HTMLResponse)
def dashboard_account_page(request: Request, account_id: str):
    if account_id not in {"total", "CN", "HK", "US"}:
        raise HTTPException(status_code=404, detail="Unknown account")
    return render_template(request, "account.html")


@router.get("/research", response_class=HTMLResponse)
def dashboard_research_page(request: Request):
    return render_template(request, "research.html")


@router.get("/journal", response_class=HTMLResponse)
def dashboard_journal_page(request: Request):
    return render_template(request, "journal.html")


@router.get("/daily-log", response_class=HTMLResponse)
def daily_log_page(request: Request):
    return render_template(request, "daily_log.html")


@router.get("/operations", response_class=HTMLResponse)
def dashboard_operations_page(request: Request):
    return render_template(request, "operations.html")


@router.get("/insights", response_class=HTMLResponse)
def dashboard_insights_page(request: Request):
    return render_template(request, "insights.html")


# ──────────────────────────────────────────────
# 盘前简报详情
# ──────────────────────────────────────────────


@router.get("/briefing", response_class=HTMLResponse)
def briefing_page(request: Request):
    return render_template(request, "briefing.html")


@router.get("/briefing/data")
def briefing_data(request: Request, as_of: date | None = None, market: str = Query(default="CN")):
    app = get_app_state(request)
    target_market = Market(market)
    result = app.daily_log.run_briefing(as_of=as_of, market=target_market)
    awareness_dict = _safe_asdict(result.awareness_snapshot) if hasattr(result, "awareness_snapshot") else {}
    ai_content = None
    observations = []
    support_resistance = []
    sector_rotation = []
    if result.ai_briefing is not None:
        ai_content = getattr(result.ai_briefing, "content", None)
        meta = getattr(result.ai_briefing, "metadata", {}) or {}
        if isinstance(meta, dict):
            observations = meta.get("observations", []) or []
            support_resistance = meta.get("support_resistance", []) or []
            sector_rotation = meta.get("sector_rotation", []) or []
    # Load AI briefing from saved file if available
    briefing_text = ai_content or ""
    if not briefing_text and result.briefing_path:
        try:
            path = Path(result.briefing_path)
            if path.exists():
                report_data = json.loads(path.read_text(encoding="utf-8"))
                briefing_text = report_data.get("content", "")
                meta = report_data.get("metadata", {}) or {}
                if isinstance(meta, dict):
                    observations = meta.get("observations", []) or observations
                    support_resistance = meta.get("support_resistance", []) or support_resistance
                    sector_rotation = meta.get("sector_rotation", []) or sector_rotation
        except Exception as exc:
            logger.warning("briefing data: failed to load saved report: %s", exc)

    return {
        "as_of": str(result.as_of),
        "market": result.market,
        "skipped_reason": result.skipped_reason,
        "insight_count": result.insight_count,
        "awareness_snapshot": awareness_dict,
        "briefing_text": briefing_text,
        "observations": observations,
        "support_resistance": support_resistance,
        "sector_rotation": sector_rotation,
    }


# ──────────────────────────────────────────────
# 盘后复盘详情
# ──────────────────────────────────────────────


@router.get("/review", response_class=HTMLResponse)
def review_page(request: Request):
    return render_template(request, "review.html")


@router.get("/review/data")
def review_data(request: Request, as_of: date | None = None, market: str = Query(default="CN")):
    app = get_app_state(request)
    target_market = Market(market)
    result = app.run_post_market_reflection(as_of or date.today())
    plan_dict = result.plan.model_dump(mode="json") if result.plan else None
    summary_dict = result.summary.model_dump(mode="json") if result.summary else None
    ai_content = None
    trade_scores = []
    lessons_learned = []
    adjustments = []
    if result.ai_journal is not None:
        ai_content = getattr(result.ai_journal, "content", None)
        meta = getattr(result.ai_journal, "metadata", {}) or {}
        if isinstance(meta, dict):
            trade_scores = meta.get("trade_scores", []) or []
            lessons_learned = meta.get("lessons_learned", []) or []
            adjustments = meta.get("adjustments", []) or []

    return {
        "as_of": str(result.as_of),
        "market": target_market.value,
        "plan": plan_dict,
        "summary": summary_dict,
        "deviations": result.deviations,
        "unresolved_insight_count": result.unresolved_insight_count,
        "ai_journal_text": ai_content,
        "trade_scores": trade_scores,
        "lessons_learned": lessons_learned,
        "adjustments": adjustments,
    }


# ──────────────────────────────────────────────
# 洞察详情
# ──────────────────────────────────────────────


@router.get("/insights/{insight_id}", response_class=HTMLResponse)
def insight_detail_page(request: Request, insight_id: str):
    app = get_app_state(request)
    insight = app.insight_store.get(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return render_template(request, "insight_detail.html", insight_id=insight_id)


def _safe_asdict(obj: object) -> dict:
    if hasattr(obj, "model_dump"):
        result = obj.model_dump(mode="json")
    elif hasattr(obj, "__dataclass_fields__"):
        from dataclasses import fields as dc_fields
        result = {f.name: getattr(obj, f.name) for f in dc_fields(obj)}
    elif isinstance(obj, dict):
        result = obj
    else:
        try:
            result = json.loads(json.dumps(obj, default=str))
        except Exception:
            return {"_raw": str(obj)}
    return _sanitize_json(result)


def _sanitize_json(obj: object) -> object:
    """Recursively replace NaN/Infinity with None so the value is JSON-safe."""
    import math as _math
    if isinstance(obj, float):
        if _math.isnan(obj) or _math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    return obj
