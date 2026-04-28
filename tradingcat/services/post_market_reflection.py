from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Callable

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote, InsightUserAction

if TYPE_CHECKING:
    from tradingcat.repositories.insight_store import InsightStore
    from tradingcat.services.ai_researcher import AIResearcher
    from tradingcat.services.market_awareness import MarketAwarenessService
    from tradingcat.services.trading_journal import TradingJournalService

logger = logging.getLogger(__name__)


@dataclass
class PostMarketReflectionResult:
    as_of: date
    plan: DailyTradingPlanNote | None = None
    summary: DailyTradingSummaryNote | None = None
    ai_journal: object | None = None
    unresolved_insight_count: int = 0
    deviations: list[str] = field(default_factory=list)
    parameter_hints: list[str] = field(default_factory=list)


class PostMarketReflectionService:
    """盤後回顧鏈：計劃 vs 實際 → AI 日誌 → 未處理洞察收集。

    預期在 TradingPhase.POST_MARKET 階段執行（收盤後）。
    """

    def __init__(
        self,
        *,
        ai_researcher: AIResearcher,
        insight_store: InsightStore,
        trading_journal: TradingJournalService,
        awareness_service: MarketAwarenessService,
    ) -> None:
        self._ai_researcher = ai_researcher
        self._insight_store = insight_store
        self._trading_journal = trading_journal
        self._awareness_service = awareness_service

    def run(
        self,
        as_of: date | None = None,
        *,
        summary_factory: Callable[[date], DailyTradingSummaryNote] | None = None,
    ) -> PostMarketReflectionResult:
        as_of = as_of or date.today()

        # 1. 加載今日計劃
        plan = self._trading_journal.latest_plan(as_of=as_of)

        # 2. 生成今日總結（如果提供了 factory）
        summary = None
        if summary_factory:
            summary = summary_factory(as_of)
        else:
            summary = self._trading_journal.latest_summary(as_of=as_of)

        # 3. 計劃 vs 實際偏差分析
        deviations: list[str] = []
        if plan and summary:
            deviations = self._compare_plan_to_actual(plan, summary)

        # 4. 查詢未處理洞察
        unresolved = self._insight_store.list(include_dismissed=False)
        unresolved_count = len(unresolved)

        # 5. 收集參數調整提示
        parameter_hints: list[str] = []
        if unresolved_count > 0:
            parameter_hints.append(f"{unresolved_count} 條洞察待處理（請在 Dashboard 中確認或忽略）")

        # 6. AI 日誌
        ai_journal = None
        if self._ai_researcher.enabled:
            try:
                daily_data = self._build_journal_data(as_of, plan, summary, unresolved_count, deviations)
                ai_journal = self._ai_researcher.journal(daily_data=daily_data)
                self._ai_researcher.save_analysis(ai_journal)
            except Exception as exc:
                logger.warning("post_market: AI journal failed (%s); continuing without it", exc)

        return PostMarketReflectionResult(
            as_of=as_of,
            plan=plan,
            summary=summary,
            ai_journal=ai_journal,
            unresolved_insight_count=unresolved_count,
            deviations=deviations,
            parameter_hints=parameter_hints,
        )

    def _compare_plan_to_actual(
        self,
        plan: DailyTradingPlanNote,
        summary: DailyTradingSummaryNote,
    ) -> list[str]:
        """Extract observable discrepancies between plan and summary."""
        deviations: list[str] = []
        plan_intents = plan.counts.get("intent_count", 0)
        summary_orders = summary.metrics.get("order_count", 0)
        if isinstance(plan_intents, (int, float)) and isinstance(summary_orders, (int, float)):
            if plan_intents > 0 and summary_orders < plan_intents:
                deviations.append(
                    f"計劃 {int(plan_intents)} 條訂單意圖，實際僅 {int(summary_orders)} 條訂單"
                )
        if plan.status == "blocked":
            deviations.append("今日計劃因執行門禁阻塞")
        return deviations

    def _build_journal_data(
        self,
        as_of: date,
        plan: DailyTradingPlanNote | None,
        summary: DailyTradingSummaryNote | None,
        unresolved_count: int,
        deviations: list[str],
    ) -> dict[str, object]:
        return {
            "as_of": str(as_of),
            "plan_headline": plan.headline if plan else "N/A",
            "plan_status": plan.status if plan else "N/A",
            "summary_headline": summary.headline if summary else "N/A",
            "unresolved_insight_count": unresolved_count,
            "deviations": deviations,
        }
