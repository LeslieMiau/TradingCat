# Absorbed Capabilities — Cookbook

This is the operator-facing index for the capabilities absorbed from
`hsliuping/TradingAgents-CN` over rounds 01–15. Every item is **off by default**
and **advisory-only** — none of them generate `Signal` / `OrderIntent` /
approvals / execution instructions. The trading loop is unchanged.

For the absorption rationale, see `/Users/miau/.claude/plans/https-github-com-hsliuping-tradingagent-peppy-pinwheel.md`.
For per-round detail, see `.handoff/round-NN-*.md`.

## TL;DR — try it now

```bash
.venv/bin/python scripts/absorb_dogfood.py
# audits env knobs, then runs an offline end-to-end pipeline with a fake
# LLM and writes a Markdown report to data/reports/dogfood/
```

That run proves the absorbed code paths work without any external
dependency or API key.

## What got absorbed

| Phase | Rounds | What it gives you | Status |
|---|---|---|---|
| P1 — A-share data sources | 01–04 | AKShare / BaoStock / Tushare adapters, factory composite | code-complete, off by default |
| P2 — News sources + filter | 05–07 | East Money / 财联社 / Finnhub / Alpha Vantage clients + unified `NewsItem` model + dedup pipeline | code-complete, off by default |
| P3 — China hard risk rules | 08 | 涨跌停 / T+1 / ST blacklist injected into `RiskEngine` | **on by default** for CN instruments |
| P4 — Technical features | 09 | `compute_technical_features(bars)` → MA / MACD / RSI / BOLL / 量比 + support/resistance | always available; research-only |
| P5 — Universe screener | 10 | `UniverseScreener.screen(...)` — multi-dim ranking | always available; research-only |
| P6 — LLM advisory layer | 11–15 | budget gate → provider abstraction → research analyst → report export → cache + batch orchestration | code-complete, off by default |

## Env knob catalogue

`scripts/absorb_dogfood.py` prints this live; the table below is the canonical reference.

### A-share market data (Rounds 01–04)

| Env var | Default | Purpose |
|---|---|---|
| `TRADINGCAT_AKSHARE_ENABLED` | `false` | turn on AKShare adapter (CN bars/quotes) |
| `TRADINGCAT_AKSHARE_ADJUST` | `qfq` | `""` / `qfq` / `hfq` |
| `TRADINGCAT_AKSHARE_SPOT_CACHE_TTL_SECONDS` | `30.0` | cache full A-share spot snapshot |
| `TRADINGCAT_BAOSTOCK_ENABLED` | `false` | free A-share fallback |
| `TRADINGCAT_BAOSTOCK_ADJUSTFLAG` | `2` | `1` 后复权 / `2` 前复权 / `3` 不复权 |
| `TRADINGCAT_TUSHARE_ENABLED` | `false` | Tushare Pro adapter |
| `TRADINGCAT_TUSHARE_TOKEN` | unset | Tushare token (env-only, never committed) |
| `TRADINGCAT_TUSHARE_ADJ` | `qfq` | `""` / `qfq` / `hfq` |

Optional deps (install only what you enable):

```bash
pip install 'tradingcat[sentiment_akshare]'    # Round 01
pip install 'tradingcat[sentiment_baostock]'   # Round 03
pip install 'tradingcat[sentiment_tushare]'    # Round 04
```

When `TRADINGCAT_AKSHARE_ENABLED=true`, the factory wraps the existing
market-data chain (Futu → YFinance → Static) with a
`CompositeMarketDataAdapter` that routes CN instruments to AKShare and
falls back to the inner chain on failure. BaoStock / Tushare adapters
exist but are **not yet wired into the factory** — they are imported and
config-controlled, ready for the next operator-driven step.

### News sources (Rounds 05–06)

| Env var | Default | Purpose |
|---|---|---|
| `TRADINGCAT_EASTMONEY_NEWS_ENABLED` | `false` | East Money adapter (no key required) |
| `TRADINGCAT_EASTMONEY_NEWS_COLUMN` | `351` | news column id |
| `TRADINGCAT_EASTMONEY_NEWS_PAGE_SIZE` | `20` | page size |
| `TRADINGCAT_EASTMONEY_NEWS_CACHE_TTL_SECONDS` | `600` | cache TTL |
| `TRADINGCAT_CLS_NEWS_ENABLED` | `false` | 财联社 web feed |
| `TRADINGCAT_CLS_NEWS_PAGE_SIZE` | `20` | page size |
| `TRADINGCAT_FINNHUB_NEWS_ENABLED` | `false` | Finnhub `company-news` |
| `TRADINGCAT_FINNHUB_TOKEN` | unset | Finnhub API token (env-only) |
| `TRADINGCAT_FINNHUB_NEWS_SYMBOLS` | unset | comma-separated tickers |
| `TRADINGCAT_ALPHA_VANTAGE_NEWS_ENABLED` | `false` | Alpha Vantage `NEWS_SENTIMENT` |
| `TRADINGCAT_ALPHA_VANTAGE_API_KEY` | unset | API key (env-only) |
| `TRADINGCAT_ALPHA_VANTAGE_NEWS_TICKERS` | unset | comma-separated tickers |

The clients all return adapter-local dicts compatible with the existing
`NewsObservationService` provider shape, but **none of them are auto-wired
into runtime yet**. To pipe them into the unified `NewsItem` filter,
construct the clients directly in your operator script (see
`scripts/absorb_dogfood.py` for shape) and pass results through
`tradingcat.services.news_filter`.

Optional dep (only needed if East Money's TLS fingerprint check tightens):

```bash
pip install 'tradingcat[sentiment_eastmoney]'  # adds curl_cffi
```

### Unified news filter (Round 07)

No env knobs — it's a pure-function service. Entry points:

- `tradingcat.domain.news.NewsItem`
- `tradingcat.domain.news.NewsUrgency`
- `tradingcat.domain.news.NewsEventClass`
- `tradingcat.services.news_filter` — URL canonicalization, tracking-param
  strip, title dedup, source allow/deny, urgency keyword classification,
  freshness × source_quality × relevance × urgency scoring.

### China hard risk rules (Round 08)

| Field on `RiskConfig` | Default | Purpose |
|---|---|---|
| `cn_market_rules_enabled` | `True` | master switch — **on by default** |
| `cn_limit_pct_regular` | `0.10` | regular A-share daily limit |
| `cn_limit_pct_st` | `0.05` | ST stock daily limit |
| `cn_limit_pct_growth_board` | `0.20` | 创业板 (300/301) / 科创板 (688) limit |

These are NOT env-driven — they're config defaults. Override via the same
mechanism as other `RiskConfig` fields if you need different limits.

The rules kick in inside `RiskEngine` and look at:
- `Instrument.tags` for `st_pattern`, `delisting_warning`
- `metadata.limit_status` for direct `limit_up` / `limit_down` annotation
- `metadata.last_buy_date` / `acquired_at` / `bought_at` for T+1 sell-lock

### Technical features (Round 09)

```python
from tradingcat.strategies.research_candidates import compute_technical_features
snapshot = compute_technical_features(bars)
# snapshot.ma5, .ma10, .ma20, .ma60
# snapshot.macd_dif, .macd_dea, .macd_hist
# snapshot.rsi14
# snapshot.boll_upper, .boll_mid, .boll_lower
# snapshot.volume_ratio_20d
# snapshot.support, .resistance
# snapshot.trend_alignment ('bullish' / 'bearish' / 'mixed')
# snapshot.momentum_state ('overbought' / 'oversold' / 'neutral')
```

Pure function, no env, no network, no external dep. Returns
`TechnicalFeatureSnapshot` for use as input to the screener / analyst.

### Universe screener (Round 10)

```python
from tradingcat.services.universe_screener import UniverseScreener
screener = UniverseScreener()  # default weights 0.4 tech / 0.35 fund / 0.25 news
candidates = screener.screen(
    instruments,
    technical={"600000": snapshot, ...},
    fundamentals={"600000": {"pe_ratio": 10.5, "roe": 0.15, ...}},
    news=[news_item, ...],
    limit=20,
)
```

Returns ranked `UniverseCandidate` objects with per-dimension subscores
and human-readable `reasons`. Research-only.

### LLM advisory layer (Rounds 11–15)

| Env var | Default | Purpose |
|---|---|---|
| `TRADINGCAT_LLM_ENABLED` | `false` | enable budget gate |
| `TRADINGCAT_LLM_PROVIDER` | `disabled` | `fake` / `openai_compatible` (extend as needed) |
| `TRADINGCAT_LLM_MODEL` | unset | model id (e.g. `deepseek-chat`, `qwen-turbo`) |
| `TRADINGCAT_LLM_DAILY_TOKEN_BUDGET` | `50000` | per-day cap; budget gate denies once exceeded |
| `TRADINGCAT_LLM_MONTHLY_COST_BUDGET` | `25.0` | per-month USD cap |

Stack (every layer enforces budget + advisory-only):

```
LLMBudgetGate            (R11) tradingcat/services/llm_budget.py
    ↓
LLMProvider              (R12) tradingcat/adapters/llm/{base,fake,openai_compatible}.py
    ↓ optionally cached
CachedLLMProvider        (R15) tradingcat/services/llm_cache.py
    ↓
ResearchAnalystService   (R13) tradingcat/services/research_analysts/
    ↓
ReportExportService      (R14) tradingcat/services/report_export.py
    ↓
BatchResearchService     (R15) tradingcat/services/batch_research.py
```

To plug in a real provider (e.g. DeepSeek / Qwen): construct
`OpenAICompatibleProvider` with the vendor's base URL + key + model id,
wire it into `ResearchAnalystService`. The budget gate already does the
right thing — denials raise `LLMProviderError` and never reach the
trading path.

## Verifying absorbed paths

```bash
# Audit env knobs + run end-to-end with fakes (no deps, no keys, no network):
.venv/bin/python scripts/absorb_dogfood.py

# Audit only:
.venv/bin/python scripts/absorb_dogfood.py --skip-dogfood

# Skip the audit and just run the offline pipeline:
.venv/bin/python scripts/absorb_dogfood.py --skip-audit

# Targeted pytest of all absorption-introduced suites:
.venv/bin/pytest \
  tests/test_akshare_adapter.py tests/test_baostock_adapter.py tests/test_tushare_adapter.py \
  tests/test_eastmoney_news_adapter.py tests/test_news_sources_round06.py tests/test_news_filter.py \
  tests/test_research_candidate_technical_features.py \
  tests/test_universe_screener.py \
  tests/test_llm_budget.py tests/test_llm_provider.py tests/test_research_analysts.py \
  tests/test_report_export.py tests/test_llm_cache_batch_research.py \
  tests/test_adapter_factory.py tests/test_risk.py tests/test_config.py
# expected: ~92 passed
```

## Daily advisory report (post-R15 wiring)

Once-a-day scheduled run that fires the absorbed research pipeline
(universe screener + technical features + optional LLM analyst) and
files a Markdown artefact under `data/reports/advisory/YYYY-MM-DD.md`.
**Read-only**; never produces signals/orders/approvals. The on-disk
file rolls daily and prunes anything older than `retention_days`.

Off by default. Enable with:

```
TRADINGCAT_ADVISORY_REPORT_ENABLED=true
# Optional overrides (defaults shown):
TRADINGCAT_ADVISORY_REPORT_CRON_HOUR=7
TRADINGCAT_ADVISORY_REPORT_CRON_MINUTE=45
TRADINGCAT_ADVISORY_REPORT_CRON_TIMEZONE=Asia/Shanghai
TRADINGCAT_ADVISORY_REPORT_OUTPUT_DIR=data/reports/advisory
TRADINGCAT_ADVISORY_REPORT_RETENTION_DAYS=30
TRADINGCAT_ADVISORY_REPORT_CANDIDATE_LIMIT=10
```

Restart the app to pick up the env change. `GET
/research/advisory/capabilities` will then show
`daily_advisory_report` as `enabled: true, ready: true`, and `GET
/scheduler/jobs` will list `advisory_research_daily` with the next run
time.

What ends up in each section:

| Section | Source | Populated when… |
|---|---|---|
| `## 候选标的排行` | `UniverseScreener` over instrument catalogue, R09 technical features computed from cached bars | Always |
| `## 资讯引用` | News providers (East Money / 财联社 / Finnhub / Alpha Vantage) | One or more news adapters configured + wired (provider hookup is a follow-up) |
| `## 分析师研究` | `ResearchAnalystService` over `OpenAICompatibleLLMProvider` | `LLMConfig.enabled=true` AND `provider`/`model`/`base_url`/`api_key` all set |

Without an LLM key set, the daily report still generates the deterministic
sections; the analyst block renders `_暂无分析师输出。_`. To wire a real
provider (e.g. DeepSeek / Qwen-via-OpenAI-compat / etc.):

```
TRADINGCAT_LLM_ENABLED=true
TRADINGCAT_LLM_PROVIDER=deepseek
TRADINGCAT_LLM_MODEL=deepseek-chat
TRADINGCAT_LLM_BASE_URL=https://api.deepseek.com/v1
TRADINGCAT_LLM_API_KEY=sk-...
TRADINGCAT_LLM_COST_PER_1K_TOKENS=0.00014  # vendor's rate
```

Manual run any time:

```python
from tradingcat.app import TradingCatApplication
app = TradingCatApplication()
app.run_daily_advisory_research()
```

(or skip-audit dogfood with `scripts/absorb_dogfood.py --skip-audit` for
a synthetic version)

## Boundaries (NOT crossed by the absorption)

The absorbed capabilities **do not**:

- generate `Signal` / `OrderIntent` from LLM output;
- mutate strategies in `tradingcat/strategies/simple.py` (production
  strategies stay deterministic);
- bypass the `approval` workflow or kill switch;
- weaken `RiskConfig` rules (R08 only adds CN-specific rules — never
  loosens existing US/HK ones);
- skip the paper-trading evidence requirement for live rollout
  (4–6 weeks per Stage A–D in `PLAN.md`).

If you find code that crosses any of these, it's a regression. Open an
issue or revert the offending round.

## Pointers

- Absorption plan: `/Users/miau/.claude/plans/https-github-com-hsliuping-tradingagent-peppy-pinwheel.md`
- Per-round handoffs: `.handoff/round-NN-*.md`
- Index of rounds: `.handoff/index.md`
- Dogfood script: `scripts/absorb_dogfood.py`
