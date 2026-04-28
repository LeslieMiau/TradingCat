from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from tradingcat.domain.models import InsightKind, InsightUserAction

if TYPE_CHECKING:
    from tradingcat.repositories.insight_store import InsightStore
    from tradingcat.services.ai_researcher import AIResearcher
    from tradingcat.services.auto_research import AutoResearchPipeline

logger = logging.getLogger(__name__)


@dataclass
class SelfIterationResult:
    as_of: date
    insight_signal_noise: dict[str, dict[str, int]] = field(default_factory=dict)
    detector_tuning_hints: list[str] = field(default_factory=list)
    strategy_suggestions: object | None = None
    weekly_report_path: str | None = None
    monthly_report_path: str | None = None


class SelfIterationService:
    """每週/每月自我迭代循環。

    分析近期洞察回饋（ack/dismiss 率）→ 信噪比指標 → 策略建議 → 研究管線。
    預期在非交易時間執行（如週六上午）。
    """

    def __init__(
        self,
        *,
        insight_store: InsightStore,
        ai_researcher: AIResearcher,
        auto_research: AutoResearchPipeline,
    ) -> None:
        self._insight_store = insight_store
        self._ai_researcher = ai_researcher
        self._auto_research = auto_research

    def run_weekly(self, as_of: date | None = None) -> SelfIterationResult:
        as_of = as_of or date.today()
        lookback = as_of - timedelta(days=7)

        # 1. 查詢近期洞察（含已忽略的）
        all_insights = self._insight_store.list(include_dismissed=True)
        recent = [i for i in all_insights if i.triggered_at.date() >= lookback]

        # 2. 按種類統計 user_action 分佈
        signal_noise: dict[str, dict[str, int]] = {}
        for kind in InsightKind:
            kind_insights = [i for i in recent if i.kind == kind]
            if not kind_insights:
                continue
            counts: dict[str, int] = {"total": len(kind_insights)}
            action_counts = Counter(i.user_action.value for i in kind_insights)
            counts.update(dict(action_counts))
            # signal-to-noise heuristic: (acknowledged + acted) / total
            signal = counts.get(InsightUserAction.ACKNOWLEDGED.value, 0) + counts.get(
                InsightUserAction.ACTED.value, 0
            )
            total = counts["total"]
            counts["signal_ratio"] = round(signal / total, 3) if total > 0 else 0.0
            signal_noise[kind.value] = counts

        # 3. 產生調參提示
        tuning_hints = self._generate_tuning_hints(signal_noise)

        # 4. AI 策略建議
        strategy_suggestions = None
        if self._ai_researcher.enabled:
            try:
                strategy_report = {
                    "as_of": str(as_of),
                    "insight_signal_noise": signal_noise,
                    "tuning_hints": tuning_hints,
                }
                strategy_suggestions = self._ai_researcher.strategy_suggestions(
                    strategy_report=strategy_report
                )
                self._ai_researcher.save_analysis(strategy_suggestions)
            except Exception as exc:
                logger.warning("self_iteration: strategy suggestions failed (%s)", exc)

        # 5. 每週研究管線
        weekly_path = None
        try:
            weekly_report = self._auto_research.run_weekly(as_of=as_of)
            weekly_path = weekly_report.report_path
        except Exception as exc:
            logger.warning("self_iteration: weekly research failed (%s)", exc)

        return SelfIterationResult(
            as_of=as_of,
            insight_signal_noise=signal_noise,
            detector_tuning_hints=tuning_hints,
            strategy_suggestions=strategy_suggestions,
            weekly_report_path=weekly_path,
        )

    def run_monthly(self, as_of: date | None = None) -> SelfIterationResult:
        as_of = as_of or date.today()
        result = self.run_weekly(as_of)

        try:
            monthly_report = self._auto_research.run_monthly(as_of=as_of)
            result.monthly_report_path = monthly_report.report_path
        except Exception as exc:
            logger.warning("self_iteration: monthly research failed (%s)", exc)

        return result

    @staticmethod
    def _generate_tuning_hints(
        signal_noise: dict[str, dict[str, int]],
    ) -> list[str]:
        hints: list[str] = []
        for kind, counts in signal_noise.items():
            total = counts.get("total", 0)
            dismissed = counts.get(InsightUserAction.DISMISSED.value, 0)
            if total > 0 and dismissed / total > 0.7:
                hints.append(
                    f"{kind}: 高忽略率（{dismissed}/{total}），建議調低敏感度或檢查檢測器邏輯"
                )
            signal = counts.get("signal_ratio", 0)
            if isinstance(signal, (int, float)) and signal > 0.5:
                hints.append(
                    f"{kind}: 高信噪比（signal_ratio={signal}），檢測器表現良好"
                )
        return hints
