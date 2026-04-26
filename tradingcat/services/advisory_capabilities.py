"""Snapshot the absorbed advisory-capability state.

Read-only diagnostic. Pure function over an ``AppConfig``. Never raises:
SDK introspection failures degrade to ``ready=False`` rather than
propagating. Safe for cheap polling and CLI scripts.

The snapshot answers two operator questions in one read:
1. What did the TradingAgents-CN absorption add to this repo?
2. For each of those capabilities, is it currently usable, or what's
   blocking it (missing optional SDK, missing API key, config off)?

The route layer (``tradingcat/routes/advisory.py``) wraps this; the
service stays import-free of FastAPI so it can also be invoked from
tests, CLI scripts, and scheduled diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from tradingcat.config import AppConfig


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    id: str
    round: str
    kind: str
    description: str
    enabled: bool
    ready: bool
    blockers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "round": self.round,
            "kind": self.kind,
            "description": self.description,
            "enabled": self.enabled,
            "ready": self.ready,
            "blockers": list(self.blockers),
        }


def build_advisory_capability_snapshot(config: AppConfig) -> dict[str, Any]:
    """Return a JSON-serializable snapshot of absorbed capability state."""

    capabilities: list[CapabilityStatus] = []

    # -------- Data sources (Rounds 01-04) --------
    capabilities.append(
        _data_source(
            cap_id="akshare_data",
            round_id="R01-R02",
            sdk_module="akshare",
            description="AKShare A-share market data adapter",
            enabled=config.akshare.enabled,
        )
    )
    capabilities.append(
        _data_source(
            cap_id="baostock_data",
            round_id="R03",
            sdk_module="baostock",
            description="BaoStock free A-share fallback adapter",
            enabled=config.baostock.enabled,
        )
    )
    capabilities.append(
        _data_source(
            cap_id="tushare_data",
            round_id="R04",
            sdk_module="tushare",
            description="Tushare Pro A-share + research dataset adapter",
            enabled=config.tushare.enabled,
            extra_blockers=(
                ("token_missing", not bool((config.tushare.token or "").strip())),
            ),
        )
    )

    # -------- News sources (Rounds 05-06) --------
    capabilities.append(
        CapabilityStatus(
            id="eastmoney_news",
            round="R05",
            kind="news_source",
            description="East Money news adapter (no key required)",
            enabled=config.eastmoney_news.enabled,
            ready=True,
        )
    )
    capabilities.append(
        CapabilityStatus(
            id="cls_news",
            round="R06",
            kind="news_source",
            description="财联社 news feed adapter",
            enabled=config.cls_news.enabled,
            ready=True,
        )
    )
    capabilities.append(
        _news_source_with_key(
            cap_id="finnhub_news",
            round_id="R06",
            description="Finnhub company-news adapter",
            enabled=config.finnhub_news.enabled,
            key_present=bool((config.finnhub_news.token or "").strip()),
            blocker_label="token_missing",
        )
    )
    capabilities.append(
        _news_source_with_key(
            cap_id="alpha_vantage_news",
            round_id="R06",
            description="Alpha Vantage NEWS_SENTIMENT adapter",
            enabled=config.alpha_vantage_news.enabled,
            key_present=bool((config.alpha_vantage_news.api_key or "").strip()),
            blocker_label="api_key_missing",
        )
    )

    # -------- Pure-function research services (Rounds 07/09) --------
    capabilities.append(
        CapabilityStatus(
            id="news_filter",
            round="R07",
            kind="research_service",
            description="Unified NewsItem deterministic dedup/rank pipeline",
            enabled=True,
            ready=True,
        )
    )
    capabilities.append(
        CapabilityStatus(
            id="technical_features",
            round="R09",
            kind="research_service",
            description="MA/MACD/RSI/BOLL/volume technical-feature computer",
            enabled=True,
            ready=True,
        )
    )

    # -------- Risk guards (Round 08) — auto-on for CN --------
    capabilities.append(
        CapabilityStatus(
            id="cn_market_risk_rules",
            round="R08",
            kind="risk_guard",
            description="CN 涨跌停 / T+1 / ST guards baked into RiskEngine",
            enabled=config.risk.cn_market_rules_enabled,
            ready=True,
        )
    )

    # -------- Universe screener + report export (Rounds 10/14) --------
    capabilities.append(
        CapabilityStatus(
            id="universe_screener",
            round="R10",
            kind="research_service",
            description="Multi-dimensional research candidate ranker",
            enabled=True,
            ready=True,
        )
    )
    capabilities.append(
        CapabilityStatus(
            id="report_export",
            round="R14",
            kind="research_service",
            description="Markdown research report exporter",
            enabled=True,
            ready=True,
        )
    )

    # -------- LLM advisory layer (Rounds 11-13, 15) --------
    llm_blockers: list[str] = []
    if config.llm.enabled and config.llm.provider in {"", "disabled"}:
        llm_blockers.append("provider_unset")
    if config.llm.enabled and not (config.llm.model or "").strip():
        llm_blockers.append("model_unset")

    llm_layer_ready = config.llm.enabled and not llm_blockers
    capabilities.append(
        CapabilityStatus(
            id="llm_budget_gate",
            round="R11",
            kind="llm_layer",
            description=(
                f"Daily-token / monthly-cost budget enforcement "
                f"(daily={config.llm.daily_token_budget}, monthly_usd={config.llm.monthly_cost_budget})"
            ),
            enabled=config.llm.enabled,
            ready=True,  # gate works whether or not a provider is wired
        )
    )
    capabilities.append(
        CapabilityStatus(
            id="llm_provider",
            round="R12",
            kind="llm_layer",
            description=(
                f"LLM provider abstraction "
                f"(configured: provider={config.llm.provider!r}, model={config.llm.model!r})"
            ),
            enabled=config.llm.enabled,
            ready=llm_layer_ready,
            blockers=tuple(llm_blockers),
        )
    )
    capabilities.append(
        CapabilityStatus(
            id="research_analyst",
            round="R13",
            kind="llm_layer",
            description="Advisory ResearchAnalystService (consumes LLMProvider)",
            enabled=config.llm.enabled,
            ready=llm_layer_ready,
            blockers=tuple(llm_blockers),
        )
    )
    capabilities.append(
        CapabilityStatus(
            id="batch_research",
            round="R15",
            kind="research_orchestration",
            description=(
                "UniverseScreener + ResearchAnalyst + ReportExport orchestration "
                "with in-memory LLM response cache"
            ),
            enabled=True,
            ready=True,  # works with FakeLLMProvider even when llm.enabled=false
        )
    )

    # -------- Daily advisory report scheduler (post-R15 wiring) --------
    advisory_cfg = config.advisory_report
    daily_blockers: list[str] = []
    if advisory_cfg.enabled:
        try:
            advisory_cfg.output_dir.parent.exists()  # cheap probe
        except Exception:
            daily_blockers.append("output_dir_unreachable")
    capabilities.append(
        CapabilityStatus(
            id="daily_advisory_report",
            round="post-R15",
            kind="research_orchestration",
            description=(
                f"Daily advisory report scheduler "
                f"(cron {advisory_cfg.cron_hour:02d}:{advisory_cfg.cron_minute:02d} "
                f"{advisory_cfg.cron_timezone}, output: {advisory_cfg.output_dir}, "
                f"retention: {advisory_cfg.retention_days}d)"
            ),
            enabled=advisory_cfg.enabled,
            ready=not daily_blockers,
            blockers=tuple(daily_blockers),
        )
    )

    return {
        "advisory_only": True,
        "snapshot_at": datetime.now(UTC).isoformat(),
        "capabilities": [cap.as_dict() for cap in capabilities],
        "summary": _summarize(capabilities),
        "boundaries": {
            "produces_signals": False,
            "produces_orders": False,
            "produces_approvals": False,
            "modifies_existing_risk_rules": False,
            "note": (
                "Absorbed capabilities are advisory-only. None of them generate "
                "Signal / OrderIntent / approvals; R08 only adds CN-specific "
                "guards on top of existing risk rules, never loosening them."
            ),
        },
    }


# -------------------------------------------------------------------- helpers


def _data_source(
    *,
    cap_id: str,
    round_id: str,
    sdk_module: str,
    description: str,
    enabled: bool,
    extra_blockers: tuple[tuple[str, bool], ...] = (),
) -> CapabilityStatus:
    blockers: list[str] = []
    if not _module_importable(sdk_module):
        blockers.append("sdk_missing")
    for label, condition in extra_blockers:
        if condition:
            blockers.append(label)
    return CapabilityStatus(
        id=cap_id,
        round=round_id,
        kind="data_source",
        description=description,
        enabled=enabled,
        ready=not blockers,
        blockers=tuple(blockers),
    )


def _news_source_with_key(
    *,
    cap_id: str,
    round_id: str,
    description: str,
    enabled: bool,
    key_present: bool,
    blocker_label: str,
) -> CapabilityStatus:
    return CapabilityStatus(
        id=cap_id,
        round=round_id,
        kind="news_source",
        description=description,
        enabled=enabled,
        ready=key_present,
        blockers=() if key_present else (blocker_label,),
    )


def _module_importable(name: str) -> bool:
    if not name:
        return True
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _summarize(capabilities: list[CapabilityStatus]) -> dict[str, int]:
    total = len(capabilities)
    enabled = sum(1 for cap in capabilities if cap.enabled)
    ready_to_enable = sum(1 for cap in capabilities if not cap.enabled and cap.ready)
    blocked = sum(1 for cap in capabilities if not cap.ready)
    return {
        "total": total,
        "enabled": enabled,
        "ready_to_enable": ready_to_enable,
        "blocked": blocked,
    }
