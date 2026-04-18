# TradingCat Harness Delivery Report

Date: 2026-03-31
Audience: Opus 4.6 reviewer
Scope: engineering-blocker harness cycle completed in full (`PLAN.json` 12/12)
Latest delivery commit: `7655ee5 harness: finish control-plane blocker alignment`

## 1. Executive Summary

This harness cycle was narrower than the 2026-03-29 delivery. It did not try to make TradingCat immediately live-trading ready. Instead, it focused on clearing the remaining engineering blockers that were making the control plane dishonest or unstable:

- stale resident `:8000` behavior diverging from fresh processes
- readiness over-counting candidate strategies as production blockers
- blocker scope bleeding across unrelated symbols
- `data_quality` vs `research_ready` semantics drifting apart
- `go-live` / `live-acceptance` / `dashboard` mixing diagnostics noise, rollout blockers, and true engineering blockers
- rollout policy mismatch (`100%` policy vs `hold` recommendation) being visible but not promoted to a first-class blocker

At the end of this run:

- resident `:8000` and fresh `uvicorn` agree on the key gate endpoints
- production readiness only considers the default execution strategies
- blocker reasons are scoped to real signal dependencies
- dashboard no longer goes blank when the candidate snapshot is missing
- rollout policy mismatch is now an explicit blocker in go-live and live-acceptance
- `PLAN.json` is complete and the worktree is clean

This is an engineering completion, not a real-money readiness completion.

## 2. Delivery Shape

The cycle landed in three main commits:

- `df3b8f5` `harness: align resident blocker inputs with fresh runtime`
- `c79200c` `harness: narrow readiness blockers to execution strategies`
- `7655ee5` `harness: finish control-plane blocker alignment`

The first commit stabilized resident-vs-fresh runtime truth. The second shrank research-readiness gating to the real execution set. The final commit cleaned up the remaining control-plane semantics and dashboard fallback behavior.

## 3. What Changed

### A. Resident and fresh runtime truth were aligned

- instrument catalog refresh behavior now updates long-lived resident state instead of letting `:8000` keep stale blocker inputs
- resident/fresh parity is now treated as a real acceptance criterion, not an afterthought
- service health verification covers `/preflight/startup`, `/ops/readiness`, `/ops/go-live`, and `/ops/live-acceptance`

Primary files:

- [tradingcat/services/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/services/market_data.py)
- [tradingcat/repositories/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/repositories/market_data.py)
- [tests/test_market_data_service.py](/Users/miau/Documents/TradingCat/tests/test_market_data_service.py)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)

### B. Research readiness now gates only the production execution set

- `ReadinessQueryService.research_readiness_summary()` no longer pulls in research candidates `d/e/f/g` when computing the top-level production gate
- readiness still reports real blockers, but only for `strategy_a_etf_rotation`, `strategy_b_equity_momentum`, and `strategy_c_option_overlay`
- candidate strategy blockers remain available in research surfaces instead of inflating operations readiness

Primary files:

- [tradingcat/services/query_services.py](/Users/miau/Documents/TradingCat/tradingcat/services/query_services.py)
- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
- [tests/test_runtime_recovery.py](/Users/miau/Documents/TradingCat/tests/test_runtime_recovery.py)

### C. Blocker scope is now tied to actual signal dependencies

- corporate-action and FX blockers are asserted against the symbols and quote currencies actually present in the current signal set
- base strategies no longer inherit unrelated symbol blockers from widened candidate/universe scans
- this keeps blocker explanations interpretable during live operations review

Primary files:

- [tests/test_research_reporting.py](/Users/miau/Documents/TradingCat/tests/test_research_reporting.py)
- [tradingcat/services/query_services.py](/Users/miau/Documents/TradingCat/tradingcat/services/query_services.py)

### D. Control-plane blocker semantics were cleaned up

- `rollout_policy_summary()` now returns:
  - `recommended_stage`
  - `policy_matches_recommendation`
  - `blocking_reasons`
- `go_live_summary()` now splits blocker classes into:
  - `engineering_blockers`
  - `rollout_blockers`
  - `policy_blockers`
- top-level `go_live.blockers` still provide a merged operator view, but info-grade diagnostics are no longer treated as first-class blockers there
- `live_acceptance_summary()` now includes `next_requirement`, making the remaining clean-day/week gate explicit

Primary files:

- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)

### E. Dashboard fallback behavior is now honest and useful

- when the persisted candidate snapshot is missing, the strategy panel now falls back to current `research_readiness.strategies`
- this preserves:
  - `display_status`
  - `status_reason`
  - `blocked_by_data_count`
- dashboard still does not trigger live candidate scorecard recomputation on GET; only the minimal strategy-status fallback is used
- acceptance progress on dashboard now matches `live_acceptance` more closely and includes the current `next_requirement`

Primary files:

- [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
- [tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)

## 4. Validation Completed

Targeted regression:

- `.venv/bin/pytest tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers tests/test_api.py::test_dashboard_summary_uses_live_research_readiness_rows_when_snapshot_missing tests/test_dashboard_facade.py tests/test_runtime_recovery.py::test_research_readiness_limits_gate_to_default_execution_strategies -q`
  - result: `8 passed`

Broader closeout regression:

- `.venv/bin/pytest tests/test_runtime_recovery.py tests/test_dashboard_facade.py tests/test_selection_service.py tests/test_allocation_service.py tests/test_rollout_policy.py tests/test_service_health.py tests/test_api.py::test_preflight_and_readiness_align_research_blockers tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress tests/test_api.py::test_dashboard_summary_uses_live_research_readiness_rows_when_snapshot_missing tests/test_api.py::test_dashboard_summary_returns_missing_snapshot_without_live_scorecard_recompute -q`
  - result: `35 passed`

Resident/fresh HTTP health:

- `.venv/bin/python -m tradingcat.services.service_health --base-url http://127.0.0.1:8000 --timeout 5`
  - result: all four gate endpoints healthy
- `.venv/bin/python -m tradingcat.services.service_health --base-url http://127.0.0.1:8053 --timeout 5`
  - result: all four gate endpoints healthy

Resident vs fresh structural parity:

- compared `/preflight/startup`
- compared `/ops/readiness`
- compared `/ops/go-live`
- compared `/ops/live-acceptance`
- compared `/dashboard/summary?as_of=2026-03-31`
- result: `mismatches: []`

Key live observations after resident restart:

- `/ops/readiness`
  - `data_quality.ready=true`
  - `research_readiness.blocked_strategy_ids=["strategy_a_etf_rotation","strategy_b_equity_momentum","strategy_c_option_overlay"]`
- `/ops/go-live`
  - `policy_matches_recommendation=false`
  - `policy_blockers=["Active rollout policy 100% does not match recommended stage hold."]`
- `/ops/live-acceptance`
  - `next_requirement.remaining_clean_days=28`
- `/dashboard/summary?as_of=2026-03-31`
  - strategy rows are present even with `snapshot_status="missing"`
  - `blocked_by_data_count=3`
  - acceptance progress blockers align with live-acceptance blockers

## 5. Recommended Review Entry Points

If Opus 4.6 is doing a focused review, these are the best starting points:

1. Production readiness scope
   - [tradingcat/services/query_services.py](/Users/miau/Documents/TradingCat/tradingcat/services/query_services.py)
   - Confirm the top-level readiness gate now intentionally excludes research candidates while preserving honest blocker semantics.

2. App-layer gate composition
   - [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
   - Review the relationship between `execution_gate_summary()`, `go_live_summary()`, `live_acceptance_summary()`, and `rollout_policy_summary()`.

3. Dashboard fallback contract
   - [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
   - Confirm the snapshot-missing fallback is minimal, read-only, and does not accidentally overstate candidate readiness.

4. Regression coverage realism
   - [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)
   - [tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)
   - [tests/test_runtime_recovery.py](/Users/miau/Documents/TradingCat/tests/test_runtime_recovery.py)
   - Check whether the tests are validating user-visible semantics rather than brittle implementation details.

## 6. Known Residual Risks

- `TradingCatApplication` is still a large orchestration shell. This cycle tightened contracts but did not attempt a larger extraction because the goal was parity and honesty, not another architectural wave.
- There are still Pydantic serialization warnings on some typed responses. They did not block this harness, but they are a reasonable follow-up cleanup target.
- The dashboard fallback path only reconstructs minimal strategy-status rows, not a full candidate scorecard. This is intentional, but reviewers should confirm that this limited fallback is the right product/ops tradeoff.
- `go-live` still includes operator-facing next actions coming from diagnostics and rollout. The blocker split is much cleaner now, but reviewers may still want to challenge the exact line between “diagnostic signal” and “promotion blocker”.

## 7. What This Does Not Claim

This report does not claim that TradingCat is ready for live capital.

The following remain external or operational gates:

- OpenD / broker validation is still not complete
- compliance checklists still have pending items
- acceptance evidence still has `ready_weeks=0` and `cn_manual_weeks=0`
- real research blockers still exist in corporate-action / FX completeness for the active execution strategies

So the correct conclusion is:

- engineering blocker cleanup is complete
- control-plane semantics are now much more honest and stable
- real-money readiness is still blocked by external evidence and remaining market-data completeness

## 8. Final Workspace State

The harness cycle is fully closed:

- [PLAN.json](/Users/miau/Documents/TradingCat/PLAN.json) is `12/12` complete
- [PROGRESS.md](/Users/miau/Documents/TradingCat/PROGRESS.md) contains the full session log and final evidence
- the worktree is clean

Final commit chain:

- `df3b8f5` `harness: align resident blocker inputs with fresh runtime`
- `c79200c` `harness: narrow readiness blockers to execution strategies`
- `7655ee5` `harness: finish control-plane blocker alignment`
