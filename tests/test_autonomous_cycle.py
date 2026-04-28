"""Tests for autonomous daily-cycle services."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from unittest.mock import MagicMock, sentinel

import pytest

from tradingcat.domain.models import (
    DailyTradingPlanNote,
    Insight,
    InsightKind,
    InsightSeverity,
    InsightUserAction,
    Market,
    MarketSession,
)
from tradingcat.services.post_market_reflection import PostMarketReflectionService
from tradingcat.services.pre_market_orchestrator import PreMarketOrchestrator
from tradingcat.services.self_iteration import SelfIterationService
from tradingcat.services.trading_session import TradingPhase, TradingSessionService


# ---------------------------------------------------------------------------
# TradingSessionService
# ---------------------------------------------------------------------------


class _FakeCalendar:
    """Returns a MarketSession for any given (market, now) pair provided via
    a side-effect dict keyed by (market, iso_timestamp)."""

    def __init__(self, sessions: dict[tuple, MarketSession]) -> None:
        self._sessions = sessions

    def get_session(self, market: Market, now: datetime | None = None) -> MarketSession:
        key = (market, now.isoformat() if now else "default")
        if key not in self._sessions:
            msg = f"no fake session for {key}"
            raise KeyError(msg)
        return self._sessions[key]


def _session(phase: str, is_trading_day: bool = True, local: str = "Asia/Shanghai") -> MarketSession:
    return MarketSession(
        market=Market.CN,
        timezone=local,
        local_date=date(2026, 4, 27),
        open_time=time(9, 30),
        close_time=time(15, 0),
        is_trading_day=is_trading_day,
        phase=phase,
    )


def _cst(h: int, m: int) -> datetime:
    """Create a datetime in Asia/Shanghai timezone."""
    from zoneinfo import ZoneInfo

    return datetime(2026, 4, 27, h, m, tzinfo=ZoneInfo("Asia/Shanghai"))


class TestTradingSessionService:
    @pytest.fixture
    def service(self):
        cal = _FakeCalendar({})
        return TradingSessionService(cal, opening_window_minutes=30, closing_window_minutes=30)

    @pytest.mark.parametrize(
        ("base_phase", "is_trading", "hour_min", "expected"),
        [
            # pre_open: >30min before open -> SLEEP
            ("pre_open", True, (0, 30), TradingPhase.SLEEP),
            ("pre_open", True, (8, 29), TradingPhase.SLEEP),
            # pre_open: <=30min before open -> PRE_MARKET
            ("pre_open", True, (9, 0), TradingPhase.PRE_MARKET),
            ("pre_open", True, (9, 29), TradingPhase.PRE_MARKET),
            # open: first 30min -> OPENING
            ("open", True, (9, 30), TradingPhase.OPENING),
            ("open", True, (9, 45), TradingPhase.OPENING),
            ("open", True, (9, 59), TradingPhase.OPENING),
            # open: core hours -> INTRADAY
            ("open", True, (10, 0), TradingPhase.INTRADAY),
            ("open", True, (13, 0), TradingPhase.INTRADAY),
            ("open", True, (14, 29), TradingPhase.INTRADAY),
            # open: last 30min -> CLOSING
            ("open", True, (14, 30), TradingPhase.CLOSING),
            ("open", True, (14, 45), TradingPhase.CLOSING),
            ("open", True, (14, 59), TradingPhase.CLOSING),
            # closed on trading day -> POST_MARKET
            ("closed", True, (15, 1), TradingPhase.POST_MARKET),
            ("closed", True, (20, 0), TradingPhase.POST_MARKET),
            # closed on non-trading day -> SLEEP
            ("closed", False, (10, 0), TradingPhase.SLEEP),
            ("closed", False, (23, 59), TradingPhase.SLEEP),
        ],
    )
    def test_phase_derivation(self, service, base_phase, is_trading, hour_min, expected):
        h, m = hour_min
        now = _cst(h, m)
        # Patch the underlying calendar to always return our specified base session
        service._calendar.get_session = lambda mkt, n=None: _session(base_phase, is_trading_day=is_trading)

        result = service.get_phase(Market.CN, now=now)
        assert result.phase == expected, f"base={base_phase} is_trading={is_trading} now={now} -> {expected}"

    def test_custom_windows(self):
        cal = _FakeCalendar({})
        svc = TradingSessionService(cal, opening_window_minutes=15, closing_window_minutes=45)
        svc._calendar.get_session = lambda m, n=None: _session("open")

        assert svc.get_phase(Market.CN, now=_cst(9, 40)).phase == TradingPhase.OPENING  # 10 min from open
        assert svc.get_phase(Market.CN, now=_cst(9, 46)).phase == TradingPhase.INTRADAY  # 16 min -> past window
        assert svc.get_phase(Market.CN, now=_cst(14, 20)).phase == TradingPhase.CLOSING  # 40 min to close < 45


# ---------------------------------------------------------------------------
# PreMarketOrchestrator
# ---------------------------------------------------------------------------


class TestPreMarketOrchestrator:
    @pytest.fixture
    def mock_awareness(self):
        m = MagicMock()
        m.snapshot.return_value = MagicMock()
        return m

    @pytest.fixture
    def mock_engine(self):
        m = MagicMock()
        m.run.return_value = MagicMock()
        m.run.return_value.produced = ["insight_1"]
        return m

    @pytest.fixture
    def mock_ai(self):
        m = MagicMock()
        m.enabled = True
        m.market_briefing.return_value = MagicMock(content="briefing", summary="brief")
        return m

    @pytest.fixture
    def mock_session(self):
        m = MagicMock()
        m.get_phase.return_value.phase = TradingPhase.PRE_MARKET
        return m

    def test_run_generates_briefing(self, mock_awareness, mock_engine, mock_ai, mock_session):
        orch = PreMarketOrchestrator(
            market_awareness=mock_awareness,
            insight_engine=mock_engine,
            ai_researcher=mock_ai,
            trading_session=mock_session,
        )
        result = orch.run(as_of=date(2026, 4, 27))

        assert result.as_of == date(2026, 4, 27)
        assert result.insight_count == 1
        assert result.ai_briefing is not None
        assert result.skipped_reason is None

    def test_skip_when_not_pre_market(self, mock_awareness, mock_engine, mock_ai, mock_session):
        mock_session.get_phase.return_value.phase = TradingPhase.INTRADAY
        orch = PreMarketOrchestrator(
            market_awareness=mock_awareness,
            insight_engine=mock_engine,
            ai_researcher=mock_ai,
            trading_session=mock_session,
        )
        result = orch.run(as_of=date(2026, 4, 27))
        assert result.skipped_reason is not None

    def test_graceful_degradation_no_ai(self, mock_awareness, mock_engine, mock_session):
        ai_disabled = MagicMock()
        ai_disabled.enabled = False

        orch = PreMarketOrchestrator(
            market_awareness=mock_awareness,
            insight_engine=mock_engine,
            ai_researcher=ai_disabled,
            trading_session=mock_session,
        )
        result = orch.run(as_of=date(2026, 4, 27))
        assert result.ai_briefing is None
        assert result.briefing_path is None


# ---------------------------------------------------------------------------
# PostMarketReflectionService
# ---------------------------------------------------------------------------


class TestPostMarketReflectionService:
    @pytest.fixture
    def plan(self):
        return DailyTradingPlanNote(
            as_of=date(2026, 4, 27),
            headline="2 条信号，3 条订单意图",
            status="planned",
            counts={"intent_count": 3},
            metrics={"order_count": 1},
        )

    @pytest.fixture
    def summary(self):
        return MagicMock(
            headline="当日总结",
            metrics={"order_count": 1},
            highlights=[],
            blockers=[],
            next_actions=[],
        )

    @pytest.fixture
    def mock_journal(self, plan):
        m = MagicMock()
        m.latest_plan.return_value = plan
        m.latest_summary.return_value = MagicMock(
            headline="当日总结",
            metrics={"order_count": 0},
            highlights=[],
            blockers=[],
            next_actions=[],
        )
        return m

    @pytest.fixture
    def mock_store(self):
        m = MagicMock()
        m.list.return_value = [MagicMock()]
        return m

    @pytest.fixture
    def mock_ai(self):
        m = MagicMock()
        m.enabled = True
        m.journal.return_value = MagicMock(content="journal", summary="daily log")
        return m

    def test_run_includes_plan_and_summary(self, mock_journal, mock_store, mock_ai):
        svc = PostMarketReflectionService(
            ai_researcher=mock_ai,
            insight_store=mock_store,
            trading_journal=mock_journal,
            awareness_service=MagicMock(),
        )
        result = svc.run(as_of=date(2026, 4, 27))
        assert result.plan is not None
        assert result.summary is not None
        assert result.unresolved_insight_count == 1

    def test_detects_deviation_when_orders_missing(self, mock_journal, mock_store, mock_ai, plan):
        mock_journal.latest_plan.return_value = plan
        svc = PostMarketReflectionService(
            ai_researcher=mock_ai,
            insight_store=mock_store,
            trading_journal=mock_journal,
            awareness_service=MagicMock(),
        )
        result = svc.run(as_of=date(2026, 4, 27))
        # summary has 0 orders, plan has 3 intents
        dev_has_planned = any("3" in d and "0" in d for d in result.deviations)
        dev_has_intent = any("订单意图" in d for d in result.deviations)
        assert dev_has_planned or dev_has_intent

    def test_graceful_no_plan(self, mock_store, mock_ai):
        journal_no_plan = MagicMock()
        journal_no_plan.latest_plan.return_value = None
        journal_no_plan.latest_summary.return_value = None

        svc = PostMarketReflectionService(
            ai_researcher=mock_ai,
            insight_store=mock_store,
            trading_journal=journal_no_plan,
            awareness_service=MagicMock(),
        )
        result = svc.run(as_of=date(2026, 4, 27))
        assert result.plan is None
        assert result.ai_journal is not None  # AI still runs with N/A data


# ---------------------------------------------------------------------------
# SelfIterationService
# ---------------------------------------------------------------------------


def _make_insight(kind: InsightKind, action: InsightUserAction) -> Insight:
    return Insight(
        id=f"{kind.value}_{action.value}_{hash(action)}",
        kind=kind,
        severity=InsightSeverity.NOTABLE,
        headline="test insight",
        subjects=["TEST"],
        causal_chain=[],
        confidence=0.8,
        triggered_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
        user_action=action,
    )


class TestSelfIterationService:
    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.list.return_value = [
            _make_insight(InsightKind.CORRELATION_BREAK, InsightUserAction.ACKNOWLEDGED),
            _make_insight(InsightKind.CORRELATION_BREAK, InsightUserAction.DISMISSED),
            _make_insight(InsightKind.CORRELATION_BREAK, InsightUserAction.PENDING),
            _make_insight(InsightKind.SECTOR_DIVERGENCE, InsightUserAction.ACTED),
            _make_insight(InsightKind.FLOW_ANOMALY, InsightUserAction.DISMISSED),
            _make_insight(InsightKind.FLOW_ANOMALY, InsightUserAction.DISMISSED),
            _make_insight(InsightKind.NEWS_DRIVEN, InsightUserAction.ACKNOWLEDGED),
        ]
        return store

    @pytest.fixture
    def mock_ai(self):
        m = MagicMock()
        m.enabled = True
        return m

    @pytest.fixture
    def mock_auto_research(self):
        m = MagicMock()
        m.run_weekly.return_value = MagicMock(report_path="/tmp/report.json")
        m.run_monthly.return_value = MagicMock(report_path="/tmp/monthly.json")
        return m

    def test_run_weekly_computes_signal_noise(self, mock_store, mock_ai, mock_auto_research):
        svc = SelfIterationService(
            insight_store=mock_store,
            ai_researcher=mock_ai,
            auto_research=mock_auto_research,
        )
        result = svc.run_weekly(as_of=date(2026, 4, 27))

        assert "correlation_break" in result.insight_signal_noise
        assert "sector_divergence" in result.insight_signal_noise
        assert "flow_anomaly" in result.insight_signal_noise
        assert "news_driven" in result.insight_signal_noise

        cb = result.insight_signal_noise["correlation_break"]
        assert cb["total"] == 3
        assert cb[InsightUserAction.ACKNOWLEDGED.value] == 1
        # signal_ratio = (1 acknowledged + 0 acted) / 3 ≈ 0.333
        assert cb["signal_ratio"] == pytest.approx(0.333, abs=0.01)

    def test_tuning_hints_for_high_dismiss_rate(self, mock_ai, mock_auto_research):
        """FLOW_ANOMALY has 2 dismissed out of 2 — should generate a hint."""
        mock_store = MagicMock()
        mock_store.list.return_value = [
            _make_insight(InsightKind.FLOW_ANOMALY, InsightUserAction.DISMISSED),
            _make_insight(InsightKind.FLOW_ANOMALY, InsightUserAction.DISMISSED),
        ]
        svc = SelfIterationService(
            insight_store=mock_store,
            ai_researcher=mock_ai,
            auto_research=mock_auto_research,
        )
        result = svc.run_weekly(as_of=date(2026, 4, 27))
        hints = result.detector_tuning_hints
        assert len(hints) >= 1
        assert any("flow_anomaly" in h for h in hints)

    def test_run_monthly_includes_monthly_report(self, mock_store, mock_ai, mock_auto_research):
        svc = SelfIterationService(
            insight_store=mock_store,
            ai_researcher=mock_ai,
            auto_research=mock_auto_research,
        )
        result = svc.run_monthly(as_of=date(2026, 4, 27))
        assert result.monthly_report_path == "/tmp/monthly.json"
