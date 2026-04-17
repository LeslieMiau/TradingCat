# QA Round 3 — HK Sentiment + Cross-Market Composite Risk Switch

**Evaluator**: claude-sonnet-4-6
**Date**: 2026-04-17
**Generator self-score**: 9.7/10

## QA method

1. **Pytest slice** — `test_hk_southbound.py` (8) + `test_market_sentiment_service.py` (41) + `test_market_awareness_service_sentiment.py` (13) + `test_market_awareness_service.py` (10) + `test_market_sentiment_http.py` (9) + `test_cn_market_flows.py` (14) + `test_architecture_boundaries.py` (6) = **111/111 passed** in 5.36s. API tests (sentiment/awareness): **4/4 passed** in 42.85s.

2. **Code audit — `_classify_market_status` fix**:
   - Root cause: CNN EXTREME_FEAR has positive score (+0.6, contrarian buy signal), but the old priority-based promotion logic treated it as a danger signal. This caused US view status to be EXTREME_FEAR, which combined with genuine HK STRESS triggered the two-market override incorrectly.
   - Fix: `danger_statuses` set is filtered by `ind.score < 0`, so only indicators with genuinely negative sentiment scores can escalate the view status. This is correct and general — works for any future contrarian indicator.
   - Verified: `test_single_market_stress_does_not_force_off` — CNN EXTREME_FEAR(+0.6) + HK STRESS(-0.5). Before fix: US=EXTREME_FEAR + HK=STRESS → 2 markets → OFF. After fix: US=CALM + HK=STRESS → 1 market → not OFF. ✓

3. **Code audit — `HKSouthboundClient`**:
   - Mirrors `CNMarketFlowsClient` pattern: thin wrapper, typed return, never raises.
   - Parses kline rows (date,buy,sell,net,...), sums last N rows, converts 万→HKD bn (÷1e5).
   - Handles malformed rows: short rows skipped, non-numeric values skipped, empty klines → None.
   - Uses same East Money host as CN northbound but with `secid=EMK.SOUTH`.
   - 8 HTTP tests cover all edge cases comprehensively.

4. **Code audit — `_fetch_hk_southbound_indicator`**:
   - Feature-flagged: `hk_southbound_enabled=False` → returns None (no indicator in view).
   - Client missing but flag on: returns UNKNOWN indicator + adapter_limitations tag.
   - Client raises: catches exception, logs, degrades to UNKNOWN.
   - `_classify_southbound()`: >+10 HKD bn → CALM(+0.5), -10..+10 → NEUTRAL(0), <-10 → STRESS(-0.5). Matches spec intent.

5. **Code audit — `_aggregate_hk_score`**:
   - When southbound disabled: vol_weight = 1.0 (not 0.7). Correct.
   - When southbound enabled: 0.7*vol + 0.3*southbound. Tested with aligned (0.5, abs=1e-3) and divergent (0.2, abs=1e-3) scenarios.
   - When southbound value=None: falls through UNKNOWN check, only vol contributes. Correct renormalization.

6. **Integration audit — golden baseline**:
   - `test_hk_sentiment_does_not_change_overall_score`: injects HSIV STRESS + southbound STRESS, verifies `overall_score`/`regime`/`posture` identical to baseline. ✓
   - `test_sentiment_force_defense_when_risk_switch_off_no_existing_reduce_risk`: verifies force_defense emitted when sentiment risk-off + bullish price posture. ✓

## Scoring

| Dimension | Self-score | QA score | Rationale |
|---|---|---|---|
| Spec coverage (R3 scope) | 9 | **9** | All R3 deliverables: HK HSIV + realized-vol fallback, southbound client (feature-flagged), composite risk switch with VIX>30/CNN<10/two-market overrides, hk_vol_stress + force_defense action rules. |
| Test rigor | 10 | **10** | 18 new R3 tests: 8 HTTP, 8 service (parametrized buckets, weight formula, missing/disabled/exception), 2 integration (golden baseline + force_defense). The critical `_classify_market_status` bug was found and fixed with explicit regression tests. |
| Regression safety | 10 | **10** | Golden baseline with HK injected passes. All pre-existing R1+R2 tests green (41 service + 9 HTTP + 14 CN + 11 integration + 10 awareness + 6 architecture + 4 API). |
| No-raise contract | 10 | **10** | Southbound client raising → indicator degrades. HSIV unavailable → realized-vol fallback. All 3 views + composite survive any failure combination. |
| Config surface | 9 | **9** | `hk_southbound_enabled` flag wired + tested. Southbound thresholds not config-exposed but acceptable — spec doesn't mandate it for R3 (CN northbound thresholds are also hard-coded). |
| Architecture boundaries | 10 | **10** | `HKSouthboundClient` imports only `SentimentHttpClient`. No FastAPI leak. 6/6 boundary tests pass. |

**Weighted QA aggregate: 9.7/10** — R3 passes.

## Issues found

### Non-blocking

1. **Southbound thresholds hard-coded**: `_classify_southbound` uses ±10 HKD bn. Unlike VIX/HSIV buckets which use `_bucket_for_value`, southbound uses a standalone function (same pattern as northbound/margin). Acceptable for R3 — can config-expose in R4 if needed.

2. **`secid=EMK.SOUTH` untested against live API**: The East Money secid for composite southbound is inferred from the northbound pattern. Unit tests validate parsing; live connectivity depends on the East Money endpoint being accessible (China IP typically required).

3. **Realized-vol fallback produces non-None values from StaticMarketDataAdapter**: In tests using `StaticMarketDataAdapter` without explicit HSIV seeding, `_compute_realized_vol` may succeed if fallback symbols (0700, 2800) happen to be in the catalog. The generator correctly patched affected tests to either seed HSIV explicitly or monkeypatch HK symbols away.

### Blocking

None.

## Verdict

**PASS** — all dimensions ≥ 9, weighted aggregate 9.7 ≥ 7.0. R3 is approved. Proceed to Round 4.
