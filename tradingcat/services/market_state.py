from __future__ import annotations

import logging
import math
import re
import statistics
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from tradingcat.domain.models import (
    Bar,
    Instrument,
    Market,
    MarketStateEvidence,
    MarketStateGroupSignal,
    MarketStateSnapshot,
    MarketStateTimelinePoint,
)
from tradingcat.repositories.market_state_store import MarketStateStore


logger = logging.getLogger(__name__)


_DEFAULT_BENCHMARKS = {
    Market.CN: "510300",
    Market.HK: "0700",
    Market.US: "SPY",
}


class MarketStateService:
    def __init__(
        self,
        *,
        market_history: Any,
        market_awareness: Any,
        store: MarketStateStore,
        ai_researcher: Any | None = None,
        max_universe_size: int = 80,
        enable_awareness_crosscheck: bool = False,
    ) -> None:
        self._market_history = market_history
        self._market_awareness = market_awareness
        self._store = store
        self._ai_researcher = ai_researcher
        self._max_universe_size = max_universe_size
        self._enable_awareness_crosscheck = enable_awareness_crosscheck

    @property
    def backend(self) -> str:
        return self._store.backend

    def snapshot(
        self,
        *,
        market: Market,
        as_of: date | None = None,
        observed_at: datetime | None = None,
        session_tag: str | None = None,
        persist: bool = False,
        include_ai: bool = False,
    ) -> MarketStateSnapshot:
        session_date = as_of or date.today()
        now = observed_at or datetime.now(UTC)
        tag = session_tag or self._session_tag(now, market)
        awareness = self._safe_awareness(session_date) if self._enable_awareness_crosscheck else {}
        market_view = self._market_view(awareness, market)
        benchmark_symbol = str((market_view or {}).get("benchmark_symbol") or _DEFAULT_BENCHMARKS[market])
        instruments = self._universe(market)

        blockers: list[str] = []
        evidence: list[MarketStateEvidence] = []
        if not instruments:
            blockers.append(f"No enabled tradable research universe is available for {market.value}.")

        observations = self._instrument_observations(instruments, session_date, blockers)
        benchmark = self._benchmark_observation(benchmark_symbol, session_date, blockers)
        usable = [item for item in observations if item.get("return_1d") is not None]

        returns = [float(item["return_1d"]) for item in usable]
        median_return = statistics.median(returns) if returns else None
        breadth_ratio = sum(1 for value in returns if value > 0) / len(returns) if returns else None
        benchmark_return = benchmark.get("return_1d")
        relative_strength = (
            float(median_return) - float(benchmark_return)
            if median_return is not None and benchmark_return is not None
            else None
        )
        median_volatility = self._safe_median([item.get("volatility_20d") for item in usable])
        benchmark_drawdown = benchmark.get("drawdown_20d")

        evidence.extend(
            self._evidence_rows(
                market=market,
                observed_at=now,
                median_return=median_return,
                breadth_ratio=breadth_ratio,
                benchmark_symbol=benchmark_symbol,
                benchmark_return=benchmark_return,
                relative_strength=relative_strength,
                median_volatility=median_volatility,
                benchmark_drawdown=benchmark_drawdown,
            )
        )
        if market_view:
            evidence.append(
                MarketStateEvidence(
                    source="market_awareness",
                    label="现有市场感知",
                    value=str(market_view.get("regime", "unknown")),
                    status=self._awareness_status(str(market_view.get("regime", "neutral"))),
                    observed_at=now,
                    explanation="来自 TradingCat 现有 market awareness 快照，用作交叉校验。",
                )
            )

        focus_groups, avoid_groups = self._group_signals(usable, median_return)
        risk_score = self._risk_score(
            breadth_ratio=breadth_ratio,
            median_return=median_return,
            relative_strength=relative_strength,
            median_volatility=median_volatility,
            benchmark_drawdown=benchmark_drawdown,
            blocker_count=len(blockers),
        )
        confidence = self._confidence(
            usable_count=len(usable),
            universe_count=len(instruments),
            evidence=evidence,
            blockers=blockers,
        )
        bias_label = self._bias_label(
            risk_score=risk_score,
            breadth_ratio=breadth_ratio,
            median_return=median_return,
            relative_strength=relative_strength,
        )
        snapshot = MarketStateSnapshot(
            market=market,
            session_date=session_date,
            observed_at=now,
            session_tag=tag if tag in {"pre_open", "open", "morning", "afternoon", "close", "manual"} else "manual",
            bias_label=bias_label,
            risk_score=risk_score,
            confidence=confidence,
            updated_at=now,
            absolute_view={
                "median_return_pct": median_return,
                "breadth_ratio": breadth_ratio,
                "benchmark_return_pct": benchmark_return,
                "median_volatility_20d": median_volatility,
                "usable_instrument_count": len(usable),
                "universe_count": len(instruments),
            },
            relative_view={
                "benchmark": benchmark_symbol,
                "relative_strength_pct": relative_strength,
                "style_hint": self._style_hint(relative_strength, breadth_ratio),
                "benchmark_drawdown_20d": benchmark_drawdown,
            },
            focus_groups=focus_groups,
            avoid_groups=avoid_groups,
            evidence=evidence,
            blockers=blockers,
        )
        # Always populate with template explanation
        snapshot = snapshot.model_copy(update={"research_explanation": self._template_explanation(snapshot)})
        if include_ai:
            ai_result = self._ai_explanation(snapshot)
            if ai_result is not None:
                snapshot = snapshot.model_copy(update={"research_explanation": ai_result})
        if persist:
            self._store.upsert(snapshot)
        return snapshot

    def latest_or_snapshot(self, *, market: Market, as_of: date | None = None) -> MarketStateSnapshot:
        session_date = as_of or date.today()
        latest = self._store.latest(market=market, session_date=session_date)
        if latest is not None:
            return latest
        # Fallback to most recent snapshot across all dates
        any_snapshot = self._store.latest_any(market=market)
        if any_snapshot is not None:
            return any_snapshot
        return self.snapshot(market=market, as_of=session_date)

    def timeline(self, *, market: Market, session_date: date | None = None) -> dict[str, object]:
        target_date = session_date or date.today()
        snapshots = self._store.list(market=market, session_date=target_date)
        points: list[MarketStateTimelinePoint] = []
        previous: MarketStateSnapshot | None = None
        for snapshot in snapshots:
            changes = self._changes(previous, snapshot)
            points.append(
                MarketStateTimelinePoint(
                    market=snapshot.market,
                    session_date=snapshot.session_date,
                    observed_at=snapshot.observed_at,
                    session_tag=snapshot.session_tag,
                    bias_label=snapshot.bias_label,
                    risk_score=snapshot.risk_score,
                    confidence=snapshot.confidence,
                    focus_groups=snapshot.focus_groups,
                    avoid_groups=snapshot.avoid_groups,
                    evidence=snapshot.evidence[:5],
                    blockers=snapshot.blockers,
                    changed_from_previous=bool(changes),
                    changes=changes,
                )
            )
            previous = snapshot
        return {
            "market": market.value,
            "session_date": target_date.isoformat(),
            "count": len(points),
            "backend": self.backend,
            "points": [point.model_dump(mode="json") for point in points],
        }

    def research_explanation(self, snapshot: MarketStateSnapshot) -> dict[str, object]:
        """Return AI explanation if available, otherwise template fallback."""
        ai_result = self._ai_explanation(snapshot)
        return ai_result or self._template_explanation(snapshot)

    def _ai_explanation(self, snapshot: MarketStateSnapshot) -> dict[str, object] | None:
        """Try AI explanation; return None if unavailable or fails."""
        if self._ai_researcher is None or not getattr(self._ai_researcher, "enabled", False):
            return None
        try:
            analysis = self._ai_researcher.explain_market_state(snapshot.model_dump(mode="json"))
            content = self._filter_ai_text(getattr(analysis, "content", "") or "")
            metadata = getattr(analysis, "metadata", {}) or {}
            if not content:
                return None
            return {
                "source": "ai_researcher",
                "summary": self._filter_ai_text(str(metadata.get("summary") or getattr(analysis, "summary", ""))),
                "why_watch": self._filter_ai_text(str(metadata.get("why_watch") or "")),
                "supporting_evidence": [self._filter_ai_text(str(item)) for item in metadata.get("supporting_evidence", [])],
                "conflicting_evidence": [self._filter_ai_text(str(item)) for item in metadata.get("conflicting_evidence", [])],
                "next_observation": self._filter_ai_text(str(metadata.get("next_observation") or "")),
                "data_limits": [self._filter_ai_text(str(item)) for item in metadata.get("data_limits", [])],
                "content": content,
                "guardrail": "research_only_no_trade_instruction",
            }
        except Exception:  # noqa: BLE001
            logger.exception("market state AI explanation failed")
            return None

    def _safe_awareness(self, as_of: date) -> dict[str, object]:
        try:
            return self._market_awareness.snapshot(as_of).model_dump(mode="json")
        except Exception:  # noqa: BLE001
            logger.debug("market awareness unavailable for market state", exc_info=True)
            return {}

    @staticmethod
    def _market_view(awareness: dict[str, object], market: Market) -> dict[str, object] | None:
        for view in awareness.get("market_views", []) if isinstance(awareness, dict) else []:
            if isinstance(view, dict) and view.get("market") == market.value:
                return view
        return None

    def _universe(self, market: Market) -> list[Instrument]:
        try:
            instruments = self._market_history.research_universe(
                markets=[market.value],
                asset_classes=["stock", "etf"],
                minimum_liquidity_bucket="medium",
            )
        except Exception:  # noqa: BLE001
            logger.debug("market state universe load failed", exc_info=True)
            instruments = []
        return instruments[: self._max_universe_size]

    def _instrument_observations(
        self,
        instruments: list[Instrument],
        as_of: date,
        blockers: list[str],
    ) -> list[dict[str, object]]:
        rows = []
        for instrument in instruments:
            bars = self._bars_for(instrument, as_of)
            if len(bars) < 2:
                continue
            row = self._bar_observation(instrument, bars)
            if row is not None:
                rows.append(row)
        if instruments and not rows:
            blockers.append("No usable local bars were available for the selected research universe.")
        elif instruments and len(rows) < max(3, math.ceil(len(instruments) * 0.3)):
            blockers.append("Local history covers too few instruments for a high-confidence market-state read.")
        return rows

    def _benchmark_observation(self, symbol: str, as_of: date, blockers: list[str]) -> dict[str, object]:
        instrument = self._market_history.get_instrument(symbol, strict=False)
        if instrument is None:
            blockers.append(f"Benchmark symbol {symbol} is not present in the instrument catalog.")
            return {"symbol": symbol}
        bars = self._bars_for(instrument, as_of)
        if len(bars) < 2:
            blockers.append(f"Benchmark symbol {symbol} has insufficient local history.")
            return {"symbol": symbol}
        return self._bar_observation(instrument, bars) or {"symbol": symbol}

    def _bars_for(self, instrument: Instrument, as_of: date) -> list[Bar]:
        start = as_of - timedelta(days=370)
        try:
            bars = self._market_history.bars_for_instrument(instrument, start, as_of, fetch_missing=False)
        except Exception:  # noqa: BLE001
            return []
        return sorted(bars, key=lambda bar: bar.timestamp)

    @staticmethod
    def _bar_observation(instrument: Instrument, bars: list[Bar]) -> dict[str, object] | None:
        closes = [float(bar.close) for bar in bars if bar.close and bar.close > 0]
        if len(closes) < 2:
            return None
        returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes)) if closes[index - 1] > 0]
        return_1d = returns[-1] if returns else None
        return_5d = (closes[-1] / closes[-6] - 1) if len(closes) >= 6 and closes[-6] > 0 else None
        window = closes[-20:] if len(closes) >= 20 else closes
        peak = max(window) if window else closes[-1]
        drawdown = (closes[-1] / peak - 1) if peak > 0 else None
        volatility = statistics.pstdev(returns[-20:]) * math.sqrt(252) if len(returns) >= 5 else None
        return {
            "symbol": instrument.symbol,
            "market": instrument.market.value,
            "asset_class": instrument.asset_class.value,
            "tags": list(instrument.tags or []),
            "return_1d": return_1d,
            "return_5d": return_5d,
            "drawdown_20d": drawdown,
            "volatility_20d": volatility,
        }

    def _evidence_rows(
        self,
        *,
        market: Market,
        observed_at: datetime,
        median_return: float | None,
        breadth_ratio: float | None,
        benchmark_symbol: str,
        benchmark_return: float | None,
        relative_strength: float | None,
        median_volatility: float | None,
        benchmark_drawdown: float | None,
    ) -> list[MarketStateEvidence]:
        return [
            MarketStateEvidence(
                source="cross_section",
                label="市场涨跌中位数",
                value=median_return,
                status=self._return_status(median_return),
                observed_at=observed_at,
                explanation=f"{market.value} 研究池最近一个交易日的中位收益。",
            ),
            MarketStateEvidence(
                source="market_breadth",
                label="上涨家数比例",
                value=breadth_ratio,
                status=self._breadth_status(breadth_ratio),
                observed_at=observed_at,
                explanation="本地研究池中最近一个交易日收涨标的占比。",
            ),
            MarketStateEvidence(
                source="benchmark",
                label=f"{benchmark_symbol} 基准涨跌",
                value=benchmark_return,
                status=self._return_status(benchmark_return),
                observed_at=observed_at,
                explanation="基准指数或代理 ETF 的最近一个交易日表现。",
            ),
            MarketStateEvidence(
                source="relative_strength",
                label="个股中位数相对基准",
                value=relative_strength,
                status=self._relative_status(relative_strength),
                observed_at=observed_at,
                explanation="市场内部中位数减去基准表现，用于识别指数与内部结构背离。",
            ),
            MarketStateEvidence(
                source="risk_structure",
                label="波动与回撤",
                value=median_volatility,
                status=self._risk_status(median_volatility, benchmark_drawdown),
                observed_at=observed_at,
                explanation="用研究池年化波动和基准 20 日回撤给风险读数做交叉校验。",
            ),
        ]

    @staticmethod
    def _group_signals(
        observations: list[dict[str, object]],
        median_return: float | None,
    ) -> tuple[list[MarketStateGroupSignal], list[MarketStateGroupSignal]]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in observations:
            tags = [str(tag) for tag in row.get("tags", []) if tag]
            group = tags[0] if tags else str(row.get("asset_class", "unknown"))
            grouped.setdefault(group, []).append(row)
        rows = []
        for name, members in grouped.items():
            returns = [float(item["return_1d"]) for item in members if item.get("return_1d") is not None]
            if not returns:
                continue
            score = statistics.median(returns)
            rows.append(
                MarketStateGroupSignal(
                    name=name,
                    score=round(score, 6),
                    members=[str(item["symbol"]) for item in members[:6]],
                    reason=f"{name} 分组最近一日中位收益 {score:.2%}，样本 {len(returns)} 个。",
                )
            )
        threshold = median_return if median_return is not None else 0.0
        focus = [row for row in rows if row.score > threshold]
        avoid = [row for row in rows if row.score < threshold]
        focus.sort(key=lambda item: item.score, reverse=True)
        avoid.sort(key=lambda item: item.score)
        return focus[:5], avoid[:5]

    @staticmethod
    def _risk_score(
        *,
        breadth_ratio: float | None,
        median_return: float | None,
        relative_strength: float | None,
        median_volatility: float | None,
        benchmark_drawdown: float | None,
        blocker_count: int,
    ) -> int:
        score = 5.0
        if breadth_ratio is not None:
            score += (0.5 - breadth_ratio) * 4
        if median_return is not None:
            score -= max(-1.5, min(1.5, median_return * 100))
        if relative_strength is not None:
            score -= max(-1.0, min(1.0, relative_strength * 80))
        if median_volatility is not None and median_volatility > 0.28:
            score += min(1.5, (median_volatility - 0.28) * 4)
        if benchmark_drawdown is not None and benchmark_drawdown < -0.05:
            score += min(2.0, abs(benchmark_drawdown) * 20)
        score += min(2.0, blocker_count * 0.6)
        return max(0, min(10, round(score)))

    @staticmethod
    def _confidence(
        *,
        usable_count: int,
        universe_count: int,
        evidence: list[MarketStateEvidence],
        blockers: list[str],
    ) -> int:
        if universe_count <= 0:
            return 0
        coverage = usable_count / universe_count
        complete_evidence = sum(1 for item in evidence if item.status != "blocked") / max(1, len(evidence))
        value = 25 + (coverage * 45) + (complete_evidence * 30) - (len(blockers) * 12)
        return max(0, min(100, round(value)))

    @staticmethod
    def _bias_label(
        *,
        risk_score: int,
        breadth_ratio: float | None,
        median_return: float | None,
        relative_strength: float | None,
    ) -> str:
        if risk_score >= 8:
            return "risk_off"
        if risk_score >= 6:
            return "defensive"
        if breadth_ratio is not None and median_return is not None:
            if breadth_ratio >= 0.62 and median_return > 0.003 and (relative_strength is None or relative_strength >= -0.002):
                return "strong"
            if breadth_ratio >= 0.52 and median_return >= 0:
                return "constructive"
        return "mixed"

    @staticmethod
    def _style_hint(relative_strength: float | None, breadth_ratio: float | None) -> str:
        if relative_strength is None or breadth_ratio is None:
            return "unknown"
        if relative_strength > 0.004 and breadth_ratio >= 0.55:
            return "broad_strength"
        if relative_strength < -0.004 and breadth_ratio < 0.45:
            return "index_led_or_weak_internal"
        return "balanced"

    @staticmethod
    def _changes(previous: MarketStateSnapshot | None, current: MarketStateSnapshot) -> list[str]:
        if previous is None:
            return []
        changes = []
        if previous.bias_label != current.bias_label:
            changes.append(f"bias {previous.bias_label} -> {current.bias_label}")
        if abs(previous.risk_score - current.risk_score) >= 2:
            changes.append(f"risk_score {previous.risk_score} -> {current.risk_score}")
        if abs(previous.confidence - current.confidence) >= 20:
            changes.append(f"confidence {previous.confidence} -> {current.confidence}")
        prev_focus = {g.name for g in previous.focus_groups}
        curr_focus = {g.name for g in current.focus_groups}
        if prev_focus != curr_focus:
            new_groups = curr_focus - prev_focus
            gone_groups = prev_focus - curr_focus
            if new_groups:
                changes.append(f"new focus groups: {', '.join(sorted(new_groups))}")
            if gone_groups:
                changes.append(f"removed focus groups: {', '.join(sorted(gone_groups))}")
        prev_avoid = {g.name for g in previous.avoid_groups}
        curr_avoid = {g.name for g in current.avoid_groups}
        if prev_avoid != curr_avoid:
            new_groups = curr_avoid - prev_avoid
            gone_groups = prev_avoid - curr_avoid
            if new_groups:
                changes.append(f"new avoid groups: {', '.join(sorted(new_groups))}")
            if gone_groups:
                changes.append(f"removed avoid groups: {', '.join(sorted(gone_groups))}")
        return changes

    @staticmethod
    def _session_tag(observed_at: datetime, market: Market) -> str:
        # Convert UTC to market local time
        _OFFSETS = {Market.CN: 8, Market.HK: 8, Market.US: -4}  # US ET approximate (no DST adjustment)
        _CLOSE_HOUR = {Market.CN: 15, Market.HK: 16, Market.US: 16}
        offset = _OFFSETS.get(market, 8)
        local_dt = observed_at + timedelta(hours=offset)
        t = local_dt.time()
        close_hour = _CLOSE_HOUR.get(market, 15)

        if t < time(9, 0):
            return "pre_open"
        if t < time(10, 30):
            return "open"
        if t < time(12, 0):
            return "morning"
        if t < time(close_hour, 0):
            return "afternoon"
        return "close"

    @staticmethod
    def _safe_median(values: list[object]) -> float | None:
        clean = [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(float(value))]
        return statistics.median(clean) if clean else None

    @staticmethod
    def _return_status(value: float | None) -> str:
        if value is None:
            return "blocked"
        if value >= 0.003:
            return "supportive"
        if value <= -0.003:
            return "warning"
        return "mixed"

    @staticmethod
    def _breadth_status(value: float | None) -> str:
        if value is None:
            return "blocked"
        if value >= 0.58:
            return "supportive"
        if value < 0.45:
            return "warning"
        return "mixed"

    @staticmethod
    def _relative_status(value: float | None) -> str:
        if value is None:
            return "blocked"
        if value >= 0.003:
            return "supportive"
        if value <= -0.003:
            return "warning"
        return "mixed"

    @staticmethod
    def _risk_status(volatility: float | None, drawdown: float | None) -> str:
        if volatility is None and drawdown is None:
            return "blocked"
        if (volatility is not None and volatility > 0.32) or (drawdown is not None and drawdown < -0.08):
            return "warning"
        if (volatility is not None and volatility < 0.22) and (drawdown is None or drawdown > -0.04):
            return "supportive"
        return "mixed"

    @staticmethod
    def _awareness_status(regime: str) -> str:
        if regime == "bullish":
            return "supportive"
        if regime in {"caution", "risk_off"}:
            return "warning"
        return "mixed"

    @staticmethod
    def _template_explanation(snapshot: MarketStateSnapshot) -> dict[str, object]:
        support = [item.explanation for item in snapshot.evidence if item.status == "supportive"]
        conflict = [item.explanation for item in snapshot.evidence if item.status in {"warning", "blocked"}]
        return {
            "source": "template",
            "summary": f"{snapshot.market.value} 市场结构为 {snapshot.bias_label}，风险分 {snapshot.risk_score}/10。",
            "why_watch": "该快照用于观察市场内部结构与基准表现是否一致。",
            "supporting_evidence": support[:3],
            "conflicting_evidence": conflict[:3],
            "next_observation": "下一次刷新时重点比较风险分、广度和相对基准强弱是否继续变化。",
            "data_limits": list(snapshot.blockers),
            "guardrail": "research_only_no_trade_instruction",
        }

    @staticmethod
    def _filter_ai_text(text: str) -> str:
        # Blocklist: Chinese + English trade directive terms (case-insensitive)
        _FORBIDDEN_PATTERNS = [
            r"买入(?!场|点)", r"卖出", r"加仓", r"减仓", r"下单",
            r"止损", r"目标价", r"入场", r"仓位",
            r"buy\b", r"sell\b", r"position\b", r"entry\b",
            r"stop.loss", r"target.price", r"order\b",
            r"approve\b", r"建仓", r"平仓", r"调仓",
            r"入場", r"出場",
        ]
        filtered = text.strip()
        for pattern in _FORBIDDEN_PATTERNS:
            filtered = re.sub(pattern, "[已过滤交易指令]", filtered, flags=re.IGNORECASE)
        return filtered
