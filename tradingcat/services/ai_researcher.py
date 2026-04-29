from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AIFeature(str, Enum):
    BRIEFING = "briefing"  # 盘前简报
    ANOMALY = "anomaly"  # 异动解读
    STRATEGY = "strategy"  # 策略建议
    JOURNAL = "journal"  # 日报/周报


@dataclass
class AIAnalysis:
    feature: AIFeature
    content: str
    summary: str
    confidence: str  # high/medium/low
    generated_at: datetime = field(default_factory=lambda: datetime.now())
    model: str = "deepseek-chat"
    metadata: dict[str, Any] = field(default_factory=dict)


class AIResearcher:
    """AI-powered investment research assistant using DeepSeek API.

    All output is informational only — never directly triggers trades.
    """

    _DEFAULT_MODEL = "deepseek-chat"
    _API_BASE = "https://api.deepseek.com/v1"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 data_dir: Path | None = None) -> None:
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._model = model or os.environ.get("AI_MODEL", self._DEFAULT_MODEL)
        self._data_dir = data_dir or Path("data/ai_reports")
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    # ---- system prompts ----

    def _system_prompt(self, feature: AIFeature) -> str:
        prompts = {
            AIFeature.BRIEFING: (
                "You are an experienced quantitative investment analyst. "
                "Write a pre-market briefing in Chinese (with English ticker symbols). "
                "Output valid JSON with the following fields:\n"
                "- regime: market regime assessment (bullish/neutral/caution/risk_off) with supporting_evidence string\n"
                "- risk_posture: string assessment\n"
                "- confidence: string (high/medium/low)\n"
                "- support_resistance: array of {asset, support_levels: [float], resistance_levels: [float]}\n"
                "- sector_rotation: array of {sector, observation, direction (strengthening/weakening/neutral)}\n"
                "- observations: array of research observations, each with:\n"
                "    symbol, observation (string), confidence (0-1), rationale, time_horizon (intraday/short_term/medium_term)\n"
                "- content: full analysis text in Chinese with specific numbers and levels\n"
                "Provide observations as research input only — do not output buy/sell/hold trading actions. "
                "All observations must cite supporting data. Be specific — avoid vague phrases like 'may fluctuate'."
            ),
            AIFeature.ANOMALY: (
                "You are a trade surveillance analyst. "
                "Analyze the detected price/volume anomaly and provide a concise assessment in Chinese. "
                "State: (1) possible causes, (2) risk level, (3) related factors to monitor. "
                "Keep under 200 words. Be specific."
            ),
            AIFeature.STRATEGY: (
                "You are a quantitative strategy researcher. "
                "Based on the current strategy performance and factor data, suggest specific improvements in Chinese. "
                "Consider: parameter tuning, new factors, risk controls, regime changes. "
                "Keep under 300 words. Be actionable."
            ),
            AIFeature.JOURNAL: (
                "You are a portfolio manager writing a post-market review in Chinese. "
                "Output valid JSON with the following fields:\n"
                "- content: full review text in Chinese with bullet points\n"
                "- trade_scores: array of {symbol, score (0-10), entry_quality (0-10), exit_quality (0-10),\n"
                "    sizing_quality (0-10), notes}\n"
                "- lessons_learned: array of {category (execution/planning/risk_management), lesson, impact}\n"
                "- adjustments: array of {adjustment, reason, target_outcome}\n"
                "You MUST include: plan vs actual deviation analysis, per-symbol trade quality scoring, "
                "categorized lessons, and at least 3 specific adjustments for the next session. "
                "Be specific with numbers — avoid vague phrases."
            ),
        }
        return prompts.get(feature, prompts[AIFeature.BRIEFING])

    # ---- API call ----

    def _call_api(self, system: str, user: str, max_tokens: int = 1024) -> str | None:
        if not self.enabled:
            logger.warning("AIResearcher disabled: no API key configured")
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key, base_url=self._API_BASE)
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content
        except ImportError:
            logger.warning("openai package not installed; skipping AI call")
            return None
        except Exception:
            logger.exception("AI API call failed for feature")
            return None

    def _parse_json(self, text: str | None) -> dict:
        if not text:
            return {"content": "", "summary": "AI analysis unavailable", "confidence": "low"}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"content": text, "summary": text[:100], "confidence": "medium"}

    # ---- analysis methods ----

    def market_briefing(self, market_data: dict[str, Any] | None = None) -> AIAnalysis:
        """Generate pre-market briefing."""
        user = json.dumps({
            "request": "pre_market_briefing",
            "date": str(date.today()),
            "context": market_data or {},
        }, ensure_ascii=False, default=str)
        raw = self._call_api(self._system_prompt(AIFeature.BRIEFING), user)
        parsed = self._parse_json(raw)
        return AIAnalysis(
            feature=AIFeature.BRIEFING,
            content=parsed.get("content", raw or "Briefing unavailable"),
            summary=parsed.get("summary", "Pre-market briefing"),
            confidence=parsed.get("confidence", "medium"),
            metadata={"market_data_snapshot": bool(market_data)},
        )

    def analyze_anomaly(self, symbol: str, price: float, volume: float,
                        avg_volume: float, context: dict | None = None) -> AIAnalysis:
        """Analyze a price/volume anomaly."""
        user = json.dumps({
            "request": "anomaly_analysis",
            "symbol": symbol,
            "price": price,
            "volume": volume,
            "avg_volume": avg_volume,
            "volume_ratio": round(volume / avg_volume, 2) if avg_volume > 0 else 0,
            "context": context or {},
        }, ensure_ascii=False, default=str)
        raw = self._call_api(self._system_prompt(AIFeature.ANOMALY), user, max_tokens=512)
        parsed = self._parse_json(raw)
        return AIAnalysis(
            feature=AIFeature.ANOMALY,
            content=parsed.get("content", raw or "Analysis unavailable"),
            summary=f"{symbol} anomaly analysis",
            confidence=parsed.get("confidence", "medium"),
            metadata={"symbol": symbol, "price": price, "volume_ratio": volume / avg_volume if avg_volume > 0 else 0},
        )

    def strategy_suggestions(self, strategy_report: dict[str, Any] | None = None) -> AIAnalysis:
        """Suggest strategy improvements based on recent performance."""
        user = json.dumps({
            "request": "strategy_suggestions",
            "date": str(date.today()),
            "strategy_report": strategy_report or {},
        }, ensure_ascii=False, default=str)
        raw = self._call_api(self._system_prompt(AIFeature.STRATEGY), user)
        parsed = self._parse_json(raw)
        return AIAnalysis(
            feature=AIFeature.STRATEGY,
            content=parsed.get("content", raw or "Suggestions unavailable"),
            summary=parsed.get("summary", "Strategy suggestions"),
            confidence=parsed.get("confidence", "medium"),
        )

    def journal(self, daily_data: dict[str, Any] | None = None) -> AIAnalysis:
        """Generate daily/weekly journal entry."""
        user = json.dumps({
            "request": "journal",
            "date": str(date.today()),
            "data": daily_data or {},
        }, ensure_ascii=False, default=str)
        raw = self._call_api(self._system_prompt(AIFeature.JOURNAL), user, max_tokens=1536)
        parsed = self._parse_json(raw)
        return AIAnalysis(
            feature=AIFeature.JOURNAL,
            content=parsed.get("content", raw or "Journal unavailable"),
            summary=parsed.get("summary", "Trading journal"),
            confidence=parsed.get("confidence", "medium"),
            metadata={
                "trade_scores": parsed.get("trade_scores", []),
                "lessons_learned": parsed.get("lessons_learned", []),
                "adjustments": parsed.get("adjustments", []),
            },
        )

    def explain_insight_evidence(self, insight_data: dict[str, Any] | None = None) -> AIAnalysis:
        """Generate a research-only explanation for a detected insight.

        This method intentionally does NOT output buy/sell/hold actions or
        entry/target/stop prices. It provides evidence analysis only.
        """
        system = (
            "You are a quantitative risk analyst. Given the following market insight, "
            "provide an evidence-based explanation in Chinese. "
            "Output valid JSON with these fields:\n"
            "- key_factors: array of {factor, impact (positive/negative/neutral), detail}\n"
            "- risk_factors: array of strings describing plausible risks\n"
            "- reference_time_window: string (e.g. 'next 1-2 trading days')\n"
            "- content: full analysis text in Chinese\n"
            "Do NOT output buy/sell/hold actions or price targets. "
            "Focus on explaining what the insight means and what factors to monitor."
        )
        user = json.dumps({
            "request": "insight_explanation",
            "date": str(date.today()),
            "insight": insight_data or {},
        }, ensure_ascii=False, default=str)
        raw = self._call_api(system, user, max_tokens=1024)
        parsed = self._parse_json(raw)
        return AIAnalysis(
            feature=AIFeature.ANOMALY,  # reuse anomaly category for insights
            content=parsed.get("content", raw or "Explanation unavailable"),
            summary=parsed.get("summary", "Insight explanation"),
            confidence=parsed.get("confidence", "medium"),
            metadata={
                "key_factors": parsed.get("key_factors", []),
                "risk_factors": parsed.get("risk_factors", []),
                "reference_time_window": parsed.get("reference_time_window", "N/A"),
            },
        )

    # ---- persistence ----

    def save_analysis(self, analysis: AIAnalysis) -> Path:
        fname = f"{analysis.feature.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = self._data_dir / fname
        path.write_text(json.dumps({
            "feature": analysis.feature.value,
            "content": analysis.content,
            "summary": analysis.summary,
            "confidence": analysis.confidence,
            "generated_at": analysis.generated_at.isoformat(),
            "model": analysis.model,
            "metadata": analysis.metadata,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def list_reports(self, feature: AIFeature | None = None, limit: int = 10) -> list[Path]:
        pattern = f"{feature.value}_*.json" if feature else "*_*.json"
        files = sorted(self._data_dir.glob(pattern), reverse=True)
        return files[:limit]
