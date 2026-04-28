from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tradingcat.domain.models import Market
from tradingcat.services.trading_session import TradingSessionService, TradingPhase

if TYPE_CHECKING:
    from tradingcat.services.ai_researcher import AIResearcher
    from tradingcat.services.insight_engine import InsightEngine
    from tradingcat.services.market_awareness import MarketAwarenessService

logger = logging.getLogger(__name__)


@dataclass
class PreMarketBriefingResult:
    as_of: date
    awareness_snapshot: object
    ai_briefing: object | None = None
    insight_count: int = 0
    briefing_path: str | None = None
    skipped_reason: str | None = None


class PreMarketOrchestrator:
    """盤前處理鏈：市場感知 → 隔夜洞察 → AI 簡報。

    預期在 TradingPhase.PRE_MARKET 階段執行（開盤前約 30 分鐘內）。
    """

    def __init__(
        self,
        *,
        market_awareness: MarketAwarenessService,
        insight_engine: InsightEngine,
        ai_researcher: AIResearcher,
        trading_session: TradingSessionService,
        data_dir: str | Path = "data",
    ) -> None:
        self._market_awareness = market_awareness
        self._insight_engine = insight_engine
        self._ai_researcher = ai_researcher
        self._trading_session = trading_session
        self._data_dir = Path(data_dir)

    def run(self, as_of: date | None = None, market: Market | None = None) -> PreMarketBriefingResult:

        as_of = as_of or date.today()
        target_market = market or Market.CN

        # 1. 階段檢查：非 PRE_MARKET 時跳過但記錄
        session = self._trading_session.get_phase(target_market)
        if session.phase != TradingPhase.PRE_MARKET:
            logger.info("pre_market [%s]: skipped (phase=%s, as_of=%s)", target_market.value, session.phase, as_of)
            return PreMarketBriefingResult(
                as_of=as_of,
                awareness_snapshot={},
                skipped_reason=f"current phase is {session.phase.value}, not pre_market",
            )

        # 2. 市場感知快照（market_awareness 已覆蓋多市場，無需過濾）
        awareness = self._market_awareness.snapshot(as_of=as_of)
        logger.info(
            "pre_market: awareness snapshot — regime=%s risk=%s confidence=%s",
            getattr(awareness, "overall_regime", "N/A"),
            getattr(awareness, "risk_posture", "N/A"),
            getattr(awareness, "confidence", "N/A"),
        )

        # 3. 隔夜洞察（InsightEngine run）
        insight_result = self._insight_engine.run(as_of=as_of)
        logger.info("pre_market: insight engine produced %d insights", len(insight_result.produced))

        # 4. AI 簡報
        ai_briefing = None
        briefing_path = None
        if self._ai_researcher.enabled:
            try:
                awareness_dict = self._safe_asdict(awareness)
                ai_briefing = self._ai_researcher.market_briefing(market_data=awareness_dict)
                path = self._ai_researcher.save_analysis(ai_briefing)
                briefing_path = str(path)
                logger.info("pre_market: AI briefing saved to %s", briefing_path)
            except Exception as exc:
                logger.warning("pre_market: AI briefing failed (%s); continuing without it", exc)

        return PreMarketBriefingResult(
            as_of=as_of,
            awareness_snapshot=awareness,
            ai_briefing=ai_briefing,
            insight_count=len(insight_result.produced),
            briefing_path=briefing_path,
        )

    @staticmethod
    def _safe_asdict(obj: object) -> dict[str, object]:
        """Best-effort conversion of an arbitrary object to a dict."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if hasattr(obj, "__dataclass_fields__"):
            from dataclasses import fields

            return {f.name: getattr(obj, f.name) for f in fields(obj)}
        if isinstance(obj, dict):
            return obj
        try:
            return json.loads(json.dumps(obj, default=str))
        except Exception:
            return {"_raw": str(obj)}
