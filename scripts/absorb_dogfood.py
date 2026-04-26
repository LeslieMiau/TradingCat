#!/usr/bin/env python3
"""TradingAgents-CN absorption — dogfood smoke run.

Phase 1: audits every env knob the absorption introduced and prints a
status table.

Phase 2: wires the research pipeline end-to-end without any external API
keys or network — synthetic bars feed compute_technical_features, hand-
crafted fundamentals/news feed UniverseScreener, FakeLLMProvider passes
through LLMBudgetGate, and BatchResearchService stitches it all into a
Markdown report on disk.

The run proves the absorbed code paths are wired and produce output. It
does NOT exercise live AKShare/Tushare/East Money/Finnhub endpoints
(those need optional deps + tokens and add latency), nor a real LLM.
Once the user has a key/dep, the same script can be extended to swap in
the real provider — the seams are the same.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Allow running as `python scripts/absorb_dogfood.py` from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tradingcat.adapters.llm.fake import FakeLLMProvider  # noqa: E402
from tradingcat.adapters.market import StaticMarketDataAdapter  # noqa: E402
from tradingcat.config import AppConfig, LLMConfig  # noqa: E402
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market  # noqa: E402
from tradingcat.domain.news import NewsEventClass, NewsItem, NewsUrgency  # noqa: E402
from tradingcat.services.batch_research import BatchResearchService  # noqa: E402
from tradingcat.services.llm_budget import (  # noqa: E402
    InMemoryLLMUsageLedger,
    LLMBudgetGate,
)
from tradingcat.services.research_analysts import ResearchAnalystService  # noqa: E402
from tradingcat.services.universe_screener import UniverseScreener  # noqa: E402
from tradingcat.strategies.research_candidates import (  # noqa: E402
    compute_technical_features,
)


# ---------------------------------------------------------------- Env audit


@dataclass(frozen=True)
class AbsorbEnv:
    name: str
    round_id: str
    purpose: str
    needs_dep: str = ""
    needs_key: bool = False


# Curated list of the env knobs the absorption introduced.
ABSORB_ENV: list[AbsorbEnv] = [
    AbsorbEnv("TRADINGCAT_AKSHARE_ENABLED", "R01/R02", "AKShare A-share market data", needs_dep="akshare"),
    AbsorbEnv("TRADINGCAT_BAOSTOCK_ENABLED", "R03", "BaoStock A-share fallback", needs_dep="baostock"),
    AbsorbEnv("TRADINGCAT_TUSHARE_ENABLED", "R04", "Tushare Pro A-share + research", needs_dep="tushare", needs_key=True),
    AbsorbEnv("TRADINGCAT_TUSHARE_TOKEN", "R04", "Tushare Pro token (env-only)", needs_key=True),
    AbsorbEnv("TRADINGCAT_EASTMONEY_NEWS_ENABLED", "R05", "East Money news source"),
    AbsorbEnv("TRADINGCAT_CLS_NEWS_ENABLED", "R06", "Cailianshe / 财联社 news source"),
    AbsorbEnv("TRADINGCAT_FINNHUB_NEWS_ENABLED", "R06", "Finnhub company-news (US)", needs_key=True),
    AbsorbEnv("TRADINGCAT_FINNHUB_TOKEN", "R06", "Finnhub API token", needs_key=True),
    AbsorbEnv("TRADINGCAT_ALPHA_VANTAGE_NEWS_ENABLED", "R06", "Alpha Vantage NEWS_SENTIMENT", needs_key=True),
    AbsorbEnv("TRADINGCAT_ALPHA_VANTAGE_API_KEY", "R06", "Alpha Vantage API key", needs_key=True),
    AbsorbEnv("TRADINGCAT_LLM_ENABLED", "R11", "LLM budget gate switch"),
    AbsorbEnv("TRADINGCAT_LLM_PROVIDER", "R11/R12", "LLM provider id (e.g. deepseek, qwen)"),
    AbsorbEnv("TRADINGCAT_LLM_MODEL", "R11/R12", "LLM model id"),
    AbsorbEnv("TRADINGCAT_LLM_DAILY_TOKEN_BUDGET", "R11", "Per-day token cap for advisory analysts"),
    AbsorbEnv("TRADINGCAT_LLM_MONTHLY_COST_BUDGET", "R11", "Per-month cost cap (USD)"),
]


def _bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _set_env(name: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return "unset"
    if "TOKEN" in name or "KEY" in name:
        return "set (redacted)" if raw.strip() else "unset"
    return raw.strip() or "unset"


def _import_present(module: str) -> bool:
    if not module:
        return True
    try:
        __import__(module)
        return True
    except Exception:
        return False


def audit_env() -> None:
    print("=" * 78)
    print("Absorbed-capability env audit")
    print("=" * 78)
    print(f"{'Env var':<46} {'Round':<8} {'State':<22}")
    print("-" * 78)
    for entry in ABSORB_ENV:
        state = _set_env(entry.name)
        marker = "·"
        if entry.name.endswith("ENABLED") and _bool_env(entry.name):
            marker = "✓"
            if entry.needs_dep and not _import_present(entry.needs_dep):
                marker = "!"
                state = f"{state} (dep missing: {entry.needs_dep})"
        print(f"{marker} {entry.name:<44} {entry.round_id:<8} {state:<22}")
    print()
    print("Legend: ✓ enabled · disabled (default) ! enabled but optional dep missing")
    print()


# ---------------------------------------------------------------- Dogfood run


_INSTRUMENTS: list[Instrument] = [
    Instrument(symbol="510300", market=Market.CN, asset_class=AssetClass.ETF, currency="CNY", name="CSI 300 ETF"),
    Instrument(symbol="300308", market=Market.CN, asset_class=AssetClass.STOCK, currency="CNY", name="中际旭创"),
    Instrument(symbol="0700", market=Market.HK, asset_class=AssetClass.STOCK, currency="HKD", name="Tencent"),
    Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD", name="SPDR S&P 500 ETF"),
    Instrument(symbol="NVDA", market=Market.US, asset_class=AssetClass.STOCK, currency="USD", name="NVIDIA"),
]


_FUNDAMENTALS: dict[str, dict[str, object]] = {
    "510300": {"pe_ratio": 12.5, "pb_ratio": 1.4, "dividend_yield": 0.022, "roe": 0.11},
    "300308": {"pe_ratio": 32.1, "pb_ratio": 5.6, "earnings_growth": 0.45, "roe": 0.18},
    "0700": {"pe_ratio": 18.7, "pb_ratio": 3.2, "earnings_growth": 0.12, "roe": 0.16},
    "SPY": {"pe_ratio": 22.0, "pb_ratio": 4.1, "dividend_yield": 0.014, "roe": 0.18},
    "NVDA": {"pe_ratio": 58.4, "pb_ratio": 38.0, "earnings_growth": 1.20, "roe": 0.92},
}


def _build_news() -> list[NewsItem]:
    now = datetime.now(UTC)
    return [
        NewsItem(
            source="eastmoney",
            source_quality=0.85,
            title="中际旭创 Q1 业绩超预期，800G 光模块订单饱满",
            url="https://example.com/news/300308-q1",
            published_at=now - timedelta(hours=2),
            summary="光模块龙头一季报营收同比 +118%，CPO 进展顺利。",
            symbols=["300308"],
            urgency=NewsUrgency.HIGH,
            event_class=NewsEventClass.EARNINGS,
            relevance=0.95,
        ),
        NewsItem(
            source="cls",
            source_quality=0.80,
            title="证监会就 ETF 互联互通新规公开征求意见",
            url="https://example.com/news/etf-policy",
            published_at=now - timedelta(hours=6),
            summary="拟扩大跨境 ETF 互联互通范围，对沪深 300 ETF 形成边际利好。",
            symbols=["510300"],
            urgency=NewsUrgency.MEDIUM,
            event_class=NewsEventClass.POLICY,
            relevance=0.7,
        ),
        NewsItem(
            source="finnhub",
            source_quality=0.75,
            title="NVIDIA partners with major hyperscaler on next-gen AI fabric",
            url="https://example.com/news/nvda-fabric",
            published_at=now - timedelta(hours=10),
            summary="Multi-billion dollar buildout reportedly anchored on Blackwell-class chips.",
            symbols=["NVDA"],
            urgency=NewsUrgency.MEDIUM,
            event_class=NewsEventClass.M_AND_A,
            relevance=0.85,
        ),
    ]


def _build_technical_features() -> dict[str, object]:
    """Use StaticMarketDataAdapter synthetic bars + compute_technical_features.

    StaticMarketDataAdapter is the existing in-repo fallback that emits
    deterministic monotonically-rising bars. Good enough to exercise the
    feature pipeline; no network needed.
    """

    static = StaticMarketDataAdapter()
    end = date.today()
    start = end - timedelta(days=120)
    snapshots: dict[str, object] = {}
    for instrument in _INSTRUMENTS:
        bars: list[Bar] = static.fetch_bars(instrument, start, end)
        if not bars:
            continue
        try:
            snapshots[instrument.symbol] = compute_technical_features(bars)
        except Exception as exc:  # never abort dogfood on a single bad symbol
            print(f"  warn: technical features failed for {instrument.symbol}: {exc}")
    return snapshots


def run_dogfood(report_dir: Path) -> Path:
    print("=" * 78)
    print("End-to-end dogfood (offline, FakeLLMProvider)")
    print("=" * 78)

    config = AppConfig.from_env()
    print(f"  Loaded AppConfig — base_currency={config.base_currency}, "
          f"akshare.enabled={config.akshare.enabled}, "
          f"llm.enabled={config.llm.enabled}")

    technical = _build_technical_features()
    print(f"  Built technical snapshots for {len(technical)} symbols")

    news = _build_news()
    print(f"  Built {len(news)} synthetic NewsItems")

    ledger = InMemoryLLMUsageLedger()
    budget = LLMBudgetGate(
        LLMConfig(
            enabled=True,
            provider="fake",
            model="dogfood-fake",
            daily_token_budget=10_000,
            monthly_cost_budget=1.0,
        ),
        ledger=ledger,
    )
    provider = FakeLLMProvider(
        budget,
        model="dogfood-fake",
        response_text=(
            "Advisory summary: top candidates concentrated in CN growth + AI infra. "
            "CSI 300 supportive on policy ETF tailwind; 300308 momentum + earnings-beat alignment. "
            "Risks: NVDA stretched valuation; tracking macro + China tightening."
        ),
    )
    analyst = ResearchAnalystService(provider)
    screener = UniverseScreener()
    batch = BatchResearchService(screener=screener, analyst=analyst)

    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"absorb_dogfood_{stamp}.md"

    result = batch.run(
        _INSTRUMENTS,
        technical=technical,
        fundamentals=_FUNDAMENTALS,
        news=news,
        limit=5,
        report_path=report_path,
    )

    print()
    print(f"  candidates ranked: {len(result.candidates)}")
    for cand in result.candidates:
        print(f"    {cand.instrument.symbol:<8} score={cand.score:.3f}  "
              f"tech={cand.technical_score:.2f} fund={cand.fundamental_score:.2f} "
              f"news={cand.news_score:.2f}")
    print(f"  analyst outputs: {len(result.analyst_outputs)} "
          f"(advisory_only={result.analyst_outputs[0].metadata.get('advisory_only')})")
    print(f"  LLM usage entries recorded: {len(ledger.list_usage())}")
    print(f"  Markdown report: {result.report_path}")
    print()
    return result.report_path  # type: ignore[return-value]


# ---------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/reports/dogfood"),
        help="Where to write the Markdown report (default: data/reports/dogfood/)",
    )
    parser.add_argument("--skip-audit", action="store_true", help="skip env audit phase")
    parser.add_argument("--skip-dogfood", action="store_true", help="skip end-to-end run")
    args = parser.parse_args()

    if not args.skip_audit:
        audit_env()
    if args.skip_dogfood:
        return 0
    report_path = run_dogfood(args.report_dir)
    print(f"Done. View the report:")
    print(f"  open '{report_path}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
