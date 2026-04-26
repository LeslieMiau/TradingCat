"""Tests for the advisory-capability snapshot service + route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tradingcat.config import (
    AlphaVantageNewsConfig,
    AppConfig,
    CLSNewsConfig,
    EastMoneyNewsConfig,
    FinnhubNewsConfig,
    LLMConfig,
    RiskConfig,
    AkshareConfig,
    BaostockConfig,
    TushareConfig,
)
from tradingcat.services.advisory_capabilities import (
    build_advisory_capability_snapshot,
)


def _config(**overrides) -> AppConfig:
    base = AppConfig()
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _by_id(snapshot: dict, cap_id: str) -> dict:
    for cap in snapshot["capabilities"]:
        if cap["id"] == cap_id:
            return cap
    raise AssertionError(f"capability {cap_id} not in snapshot")


def test_default_snapshot_marks_optional_sdks_blocked():
    snapshot = build_advisory_capability_snapshot(AppConfig())
    assert snapshot["advisory_only"] is True
    assert snapshot["boundaries"]["produces_signals"] is False
    # Default config: every data source disabled, optional SDKs absent in this env.
    akshare = _by_id(snapshot, "akshare_data")
    assert akshare["enabled"] is False
    # Whether ready depends on whether akshare happens to be importable in this venv.
    if not akshare["ready"]:
        assert "sdk_missing" in akshare["blockers"]
    cn_rules = _by_id(snapshot, "cn_market_risk_rules")
    assert cn_rules["enabled"] is True  # auto-on by default
    assert cn_rules["ready"] is True


def test_summary_counts_match_capability_states():
    snapshot = build_advisory_capability_snapshot(AppConfig())
    summary = snapshot["summary"]
    caps = snapshot["capabilities"]
    assert summary["total"] == len(caps)
    assert summary["enabled"] == sum(1 for c in caps if c["enabled"])
    assert summary["ready_to_enable"] == sum(1 for c in caps if not c["enabled"] and c["ready"])
    assert summary["blocked"] == sum(1 for c in caps if not c["ready"])


def test_tushare_token_missing_blocks_when_enabled():
    cfg = _config(tushare=TushareConfig(enabled=True, token=None))
    snapshot = build_advisory_capability_snapshot(cfg)
    tushare = _by_id(snapshot, "tushare_data")
    assert tushare["enabled"] is True
    # Even if SDK is importable, token-missing blocks.
    assert "token_missing" in tushare["blockers"]
    assert tushare["ready"] is False


def test_finnhub_key_missing_blocks_when_enabled():
    cfg = _config(finnhub_news=FinnhubNewsConfig(enabled=True, token=None))
    snapshot = build_advisory_capability_snapshot(cfg)
    finnhub = _by_id(snapshot, "finnhub_news")
    assert finnhub["enabled"] is True
    assert finnhub["blockers"] == ["token_missing"]


def test_alpha_vantage_key_missing_blocks_when_enabled():
    cfg = _config(alpha_vantage_news=AlphaVantageNewsConfig(enabled=True, api_key=None))
    snapshot = build_advisory_capability_snapshot(cfg)
    av = _by_id(snapshot, "alpha_vantage_news")
    assert av["enabled"] is True
    assert av["blockers"] == ["api_key_missing"]


def test_llm_layer_blocks_on_unset_provider_or_model():
    cfg = _config(llm=LLMConfig(enabled=True, provider="disabled", model=""))
    snapshot = build_advisory_capability_snapshot(cfg)
    provider = _by_id(snapshot, "llm_provider")
    assert provider["enabled"] is True
    assert "provider_unset" in provider["blockers"]
    assert "model_unset" in provider["blockers"]
    # Budget gate stays ready even when provider is unconfigured — its job is enforcement.
    gate = _by_id(snapshot, "llm_budget_gate")
    assert gate["ready"] is True


def test_news_sources_without_key_requirement_are_ready_immediately():
    snapshot = build_advisory_capability_snapshot(AppConfig())
    eastmoney = _by_id(snapshot, "eastmoney_news")
    cls = _by_id(snapshot, "cls_news")
    assert eastmoney["ready"] is True
    assert cls["ready"] is True
    assert eastmoney["enabled"] is False  # still off by default
    assert cls["enabled"] is False


def test_pure_function_services_are_always_enabled_and_ready():
    snapshot = build_advisory_capability_snapshot(AppConfig())
    for cap_id in ("news_filter", "technical_features", "universe_screener", "report_export", "batch_research"):
        cap = _by_id(snapshot, cap_id)
        assert cap["enabled"] is True
        assert cap["ready"] is True


def test_route_returns_snapshot_through_app_state():
    from tradingcat.app import TradingCatApplication
    from tradingcat.main import app

    # Use the already-wired FastAPI app; injecting AppConfig via app.state.
    test_state = TradingCatApplication()
    app.state.app_state = test_state

    with TestClient(app) as client:
        response = client.get("/research/advisory/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["advisory_only"] is True
    assert "capabilities" in payload
    assert "summary" in payload
    assert payload["summary"]["total"] == len(payload["capabilities"])
