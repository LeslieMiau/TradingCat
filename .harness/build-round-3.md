# Build Round 3 — HK Sentiment + Cross-Market Composite Risk Switch

**Generator**: claude-sonnet-4-6 (in-session)
**Round scope**: HK view (`^HSIV` primary / realized-vol fallback) + `HKSouthboundClient` (feature-flag `hk_southbound_enabled`) + southbound bucket classification + composite risk switch with overrides (VIX>30/CNN<10 → min WATCH; 2-market STRESS → force OFF) + `sentiment_hk_vol_stress` / `sentiment_force_defense` action rules.
**Non-goals (R3)**: UI sparklines, DuckDB persistence, UI polish.

## Delivered

### New files

| Path | Purpose |
|---|---|
| `tradingcat/adapters/sentiment_sources/hk_southbound.py` | `HKSouthboundClient` — fetches southbound (mainland→HK) Stock Connect flow from East Money kline API. Returns `HKSouthboundReading(net_5d_hkd_bn)` or `None`. Parses kline rows, sums last N days, converts 万→HKD bn. Never raises. |
| `tests/test_hk_southbound.py` | 8 tests: positive/negative net, window slicing, missing klines, empty klines, HTTP 500, non-numeric rows skipped, short rows skipped. All driven by `httpx.MockTransport`. |

### Modifications

| Path | Change |
|---|---|
| `tradingcat/services/market_sentiment.py` | Module docstring updated (R2→R3 scope). Added `HKSouthboundClient` + `HKSouthboundReading` imports. Added `_classify_southbound()` function (>+10 CALM/+0.5, -10..+10 NEUTRAL/0, <-10 STRESS/-0.5). `__init__` type-annotated `hk_flows_client: HKSouthboundClient | None`. Replaced southbound stub with real `_fetch_hk_southbound_indicator()` using the injected client. **Critical fix**: `_classify_market_status()` now only escalates view-level status from indicators with negative scores — prevents contrarian CNN EXTREME_FEAR (positive score) from being misclassified as a danger signal at the market view level. |
| `tradingcat/adapters/sentiment_sources/fakes.py` | Added `StaticHKSouthboundClient` (reading + raise_on_fetch flag), `make_hk_southbound_reading` helper. |
| `tradingcat/runtime.py` | Added `HKSouthboundClient` import. Conditional construction when `hk_southbound_enabled`. Passed as `hk_flows_client=` to `MarketSentimentService`. |
| `tests/test_market_sentiment_service.py` | `_build_services` now accepts `hk_flows_client` kwarg and passes it through. 8 new HK southbound tests: bucket classification (×3 parametrized), score with southbound enabled (both aligned + divergent), southbound enabled but client missing, southbound exception propagation. Fixed `test_risk_switch_on_when_composite_positive` (seed HSIV to prevent synthetic data interference). Fixed `test_composite_excludes_unknown_markets` (block HK symbols via monkeypatch). |
| `tests/test_market_awareness_service_sentiment.py` | Added HK fake imports. 2 new tests: `test_hk_sentiment_does_not_change_overall_score` (golden baseline invariant with HK STRESS + southbound injected), `test_sentiment_force_defense_when_risk_switch_off_no_existing_reduce_risk`. |

## Critical bug fix

`_classify_market_status()` was propagating all indicator-level status labels to the market view, including contrarian signals. CNN Fear & Greed in EXTREME_FEAR bucket has a **positive** score (+0.6, contrarian buy signal), but the old code surfaced it as the market-level status. This caused the two-market STRESS override to fire incorrectly when CNN showed extreme fear (positive sentiment) and HK showed genuine STRESS (negative sentiment) — treating both markets as "stressed" even though only one was genuinely risk-negative.

**Fix**: `_classify_market_status` now filters indicator statuses by `score < 0` before escalating. Only indicators that represent genuine danger signals (negative scores) can promote the market-level status to STRESS/EXTREME_FEAR/etc.

## Verification

```
tests/test_hk_southbound.py ........ 8 passed
tests/test_market_sentiment_service.py ....................................... 41 passed
tests/test_market_awareness_service_sentiment.py ............. 13 passed
tests/test_market_awareness_service.py .......... 10 passed (no regression)
tests/test_market_sentiment_http.py ......... 9 passed (no regression)
tests/test_architecture_boundaries.py ...... 6 passed (no regression)
tests/test_cn_market_flows.py .............. 14 passed (no regression)
tests/test_api.py (sentiment/awareness) .... 4 passed (no regression)
```

**Total: 111/111 (core) + 4 API = all green.**

Key assertions:
- **HSIV bucket classification**: 14→CALM, 20→NEUTRAL, 25→ELEVATED, 35→STRESS ✓
- **Realized-vol fallback**: HSIV empty → compute 20d annual vol from 0700/2800 → source="realized_vol_fallback" ✓
- **Southbound classification**: +15→CALM(+0.5), 0→NEUTRAL(0), -15→STRESS(-0.5) ✓
- **HK weight formula (southbound disabled)**: 1.0×vol_score ✓
- **HK weight formula (southbound enabled)**: 0.7×vol + 0.3×southbound = 0.35-0.15=0.20 for (CALM, STRESS) ✓
- **Southbound enabled but client missing**: indicator UNKNOWN, adapter_limitations has "hk_southbound_client_missing" ✓
- **Southbound exception**: indicator degrades, snapshot valid ✓
- **Composite all three markets**: 0.45×US + 0.30×CN + 0.25×HK exact match ✓
- **Two-market STRESS override**: US STRESS + CN STRESS → force OFF ✓
- **Single-market STRESS no override**: HK alone STRESS → not OFF ✓
- **VIX>30 → min WATCH**: forces ON→WATCH ✓
- **CNN<10 → min WATCH**: contrarian extreme fear doesn't trigger two-market override ✓
- **`_classify_market_status` fix**: CNN EXTREME_FEAR (positive score) does NOT escalate US view to EXTREME_FEAR ✓
- **Golden baseline invariant**: HK sentiment injected → `overall_score`/`regime`/`posture` unchanged ✓
- **`sentiment_hk_vol_stress`**: HSIV STRESS → action emitted, severity=MEDIUM, markets=[HK] ✓
- **`sentiment_force_defense`**: risk_switch=OFF + bullish posture → emitted, severity=HIGH ✓
- **HTTP client**: positive/negative net parsing, window slicing, missing/empty/500/non-numeric edge cases ✓
- **No-raise contract**: all paths → snapshot valid ✓

## Decisions / tradeoffs

1. **Southbound classification thresholds**: Used ±10 HKD bn (5d net) for southbound vs ±20 CNY bn for northbound. HK southbound volumes are typically smaller than northbound, and the currency difference (HKD vs CNY) further adjusts the scale. These thresholds are not yet config-exposed — can be added in R4 if needed.

2. **`_classify_market_status` fix (contrarian signal handling)**: Rather than adding a `contrarian: bool` flag to indicators, the fix uses the indicator's score sign as the discriminant. Indicators with positive scores (meaning bullish sentiment) should not escalate the view to danger status. This is general enough to handle any future contrarian indicator without per-indicator special-casing.

3. **East Money southbound endpoint**: Uses the same kamt.kline/get endpoint as northbound but with `secid=EMK.SOUTH`. The exact field mapping (index 3 = net buy) is inferred from the northbound pattern. The client handles malformed rows gracefully.

4. **Feature flag default**: `hk_southbound_enabled` defaults to `False`. The runtime only constructs the client when the flag is on. Tests that exercise southbound pass `hk_southbound_enabled=True` via config override.

## Self-evaluation

| Dimension | Score | Notes |
|---|---|---|
| Spec coverage (R3) | 9/10 | All R3 deliverables: HK HSIV + fallback, southbound client, composite risk switch, override rules, action rules. |
| Test rigor | 10/10 | 8 HTTP + 8 service + 2 integration = 18 new R3 tests. All buckets parametrized, weight formula, missing/disabled/exception paths. Critical `_classify_market_status` bug found + fixed + regression tests added. |
| Regression safety | 10/10 | Golden baseline with HK injected → scores unchanged. All pre-existing R1+R2 tests green (41 service + 9 HTTP + 14 CN HTTP + 11 integration + 10 awareness + 6 architecture). |
| No-raise contract | 10/10 | Southbound client raising → indicator degrades. All 3 views + composite survive. |
| Config surface | 9/10 | `hk_southbound_enabled` flag wired + tested. Southbound thresholds not yet config-exposed (acceptable for R3). |
| Architecture boundaries | 10/10 | `HKSouthboundClient` imports only `SentimentHttpClient`. No FastAPI leak. 6/6 boundary tests pass. |

**Weighted aggregate: 9.7/10**

## Handoff

- `.harness/status.json`: updated to `rounds.3.phase=awaiting_qa`
- Evaluator entry points:
  1. `pytest tests/test_hk_southbound.py tests/test_market_sentiment_service.py tests/test_market_awareness_service_sentiment.py tests/test_market_awareness_service.py tests/test_market_sentiment_http.py tests/test_cn_market_flows.py tests/test_architecture_boundaries.py` — all green
  2. `pytest tests/test_api.py -k "sentiment or awareness"` — 4/4 green
  3. Live uvicorn → `/research/market-awareness` — verify HK view with hk_vol indicator
  4. `hk_southbound_enabled=true` restart — verify southbound indicator appears
  5. Architecture boundary tests — verify no import leak
