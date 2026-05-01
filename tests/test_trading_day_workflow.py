from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from tradingcat.domain.models import (
    ApprovalRequest,
    AssetClass,
    Instrument,
    Insight,
    InsightEvidence,
    InsightKind,
    InsightSeverity,
    Market,
    OrderIntent,
    OrderSide,
    PortfolioSnapshot,
    Position,
)
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.trading_day_workflow import TradingDayWorkflowService


class _MarketState:
    def __init__(self, market: Market) -> None:
        self._market = market

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {
            "market": self._market.value,
            "bias_label": "risk_on" if self._market == Market.US else "neutral",
            "risk_score": 3.0,
            "confidence": 80.0,
            "blockers": [],
        }


class _MarketStateService:
    def latest_or_snapshot(self, *, market: Market):
        return _MarketState(market)


class _InsightStore:
    def __init__(self, insights: list[Insight]) -> None:
        self._insights = insights

    def list(self, *, include_dismissed: bool = False):
        return self._insights


def test_trading_day_workflow_builds_read_only_insight_matrix():
    instrument = Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")
    intent = OrderIntent(
        id="intent-spy",
        signal_id="strategy:spy",
        instrument=instrument,
        side=OrderSide.BUY,
        quantity=10,
        requires_approval=True,
    )
    approval = ApprovalRequest(order_intent=intent)
    insight = Insight(
        id="insight-spy",
        kind=InsightKind.FLOW_ANOMALY,
        severity=InsightSeverity.URGENT,
        headline="SPY flow anomaly",
        subjects=["SPY"],
        confidence=0.91,
        causal_chain=[
            InsightEvidence(
                source="flow_detector",
                fact="unusual_volume",
                value={"zscore": 3.2},
                observed_at=datetime(2026, 3, 9, tzinfo=UTC),
            )
        ],
        triggered_at=datetime(2026, 3, 9, tzinfo=UTC),
        expires_at=datetime(2026, 3, 9, tzinfo=UTC) + timedelta(days=1),
    )
    plan = {
        "status": "planned",
        "headline": "SPY plan",
        "items": [
            {
                "intent_id": "intent-spy",
                "strategy_id": "strategy",
                "symbol": "SPY",
                "market": "US",
                "side": "buy",
                "quantity": 10,
                "reference_price": 100.0,
                "reference_source": "synthetic",
                "reference_quality": "synthetic",
                "requires_approval": True,
            }
        ],
    }
    dashboard = {
        "journal": {"latest_plan": plan, "latest_summary": {"headline": "summary"}},
        "details": {
            "recent_orders": [
                {
                    "order_intent_id": "intent-spy",
                    "symbol": "SPY",
                    "market": "US",
                    "status": "submitted",
                    "reference_quality": "synthetic",
                }
            ],
            "execution_gate": {"reasons": []},
            "market_awareness": {},
        },
    }
    app = SimpleNamespace(
        market_calendar=MarketCalendarService(),
        market_state=_MarketStateService(),
        dashboard_summary=lambda _as_of: dashboard,
        operations_readiness=lambda: {"blockers": []},
        data_quality_summary=lambda: {"blockers": []},
        portfolio=SimpleNamespace(
            current_snapshot=lambda: PortfolioSnapshot(
                nav=100_000,
                positions=[
                    Position(
                        instrument=instrument,
                        quantity=10,
                        market_value=1_000,
                        weight=0.01,
                    )
                ],
            )
        ),
        approvals=SimpleNamespace(list_requests=lambda: [approval]),
        insight_store=_InsightStore([insight]),
    )

    payload = TradingDayWorkflowService(app).snapshot(date(2026, 3, 9))
    matrix = payload["intraday"]["insight_matrix"]
    row = matrix["rows"][0]

    assert matrix["counts"]["insights"] == 1
    assert row["symbol"] == "SPY"
    assert row["relation_type"] == "insight+position+plan_item+order+approval"
    assert row["insights"][0]["id"] == "insight-spy"
    assert row["causal_chain"][0]["source"] == "flow_detector"
    assert row["causal_chain"][0]["fact"] == "unusual_volume"
    assert row["position"]["quantity"] == 10
    assert row["plan_item"]["intent_id"] == "intent-spy"
    assert row["order"]["status"] == "submitted"
    assert row["approval"]["status"] == "pending"
    assert {item["rule"] for item in row["risk_rules"]} >= {"manual_approval_required", "synthetic_reference"}

    assert set(payload) >= {"action_queue", "heartbeat", "live_readiness"}
    assert payload["heartbeat"]["overall_status"] in {"ok", "degraded", "stale", "offline", "blocked"}
    assert all("source_service" in item and "source_field" in item for item in payload["heartbeat"]["components"])
    assert payload["live_readiness"]["ready"] is False
    assert all("source_service" in blocker and "source_field" in blocker for blocker in payload["live_readiness"]["blockers"])
    queue = payload["action_queue"]
    assert queue["count"] >= 1
    required_action_fields = {
        "id",
        "severity",
        "category",
        "title",
        "detail",
        "source_service",
        "source_field",
        "target_url",
        "created_at",
        "status",
    }
    assert all(required_action_fields <= set(item) for item in queue["items"])
