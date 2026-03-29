# TradingCat Harness Delivery Report

Date: 2026-03-29
Audience: Opus 4.6 reviewer
Scope: 30-day personal-trader harness plan completed in full (`PLAN.json` 48/48)
Latest delivery commit: `299f1bd dashboard: align readiness diagnostics and gating`

## 1. Executive Summary

This harness run completed the full `PLAN.json` backlog and tightened TradingCat around one main goal:

- prevent synthetic or incomplete research from being treated as production-ready
- make data / execution / acceptance blockers visible across research, readiness, diagnostics, dashboard, and reports
- turn the project from a "control plane prototype" into something closer to a personal-trader operational review surface

The highest-value outcomes are:

- research gating is now explicit end-to-end
- persistent research universe and minimal real-history baseline are in place
- strategy signals are now market/history-driven instead of mostly sample-driven
- trigger / execution / reconcile / audit now form a traceable chain
- acceptance / rollout / go-live evidence is now persisted and exposed consistently
- dashboard no longer overstates readiness, and now surfaces blocked-by-data vs paper-only states

## 2. Delivery Shape

The work landed as a sequence of focused commits, ending with:

- `f75d229` research: block silent synthetic promotion
- `8d3b524` research: expose blocker fields across scorecard and detail
- `a59fd3a` research: hard-block incomplete report coverage
- `4969842` research: expose detail coverage blockers
- `d8562d4` selection: force blocked strategies to paper only
- `e5cfbd0` allocation: keep blocked strategies in shadow mode
- `eb9a995` data: summarize coverage blockers
- `322232c` data: persist symbol-level sync run stats
- `fd2f688` data: prioritize repair plan by research impact
- `7ba0500` data: return repair recheck summaries
- `9a59411` ops: surface data readiness blockers in readiness
- `93031b2` research: surface corporate action coverage blockers
- `6ffb036` research: expose FX coverage blockers
- `debcca4` data: bootstrap research history baseline
- `491b989` triggers: use real RSI indicator inputs
- `93da7ca` triggers: use real SMA indicator inputs
- `193b65a` triggers: persist evaluation snapshots and context
- `320f1cd` triggers: explain non-trigger reasons explicitly
- `4663b6c` execution: track expected vs realized price context
- `09b206f` execution: summarize quality by asset class
- `8a1e211` ops: expose TCA sample breakdown
- `fa2bbf9` reports: highlight execution drags in ops summaries
- `ca620b4` refactor: isolate harness reporting analytics
- `d2978d9` execution: link authorization summary to fill source
- `c896a87` reconcile: expose portfolio impact traces
- `eecb42e` audit: link orders to authorization traces
- `1ea4299` manual-fill: lock portfolio consistency chain
- `33c803f` ops: block readiness on execution mismatches
- `d99c8bf` ops: persist acceptance evidence tags
- `56c9c31` ops: chain acceptance evidence through reports
- `4203cfe` research: persist market-driven universe signals
- `299f1bd` dashboard: align readiness diagnostics and gating

## 3. What Was Added

### A. Research trust and data gating

- `StrategyAnalysisService` now returns explicit `data_source`, `data_ready`, `promotion_blocked`, `blocking_reasons`, `validation_status`, `minimum_history_coverage_ratio`, and top-level hard-block semantics.
- Selection and allocation now defensively downgrade blocked strategies to `paper_only` / `shadow`, even if an upstream recommendation regresses.
- Corporate-action and FX coverage are now first-class research inputs instead of silent assumptions.

Primary files:

- [tradingcat/services/strategy_analysis.py](/Users/miau/Documents/TradingCat/tradingcat/services/strategy_analysis.py)
- [tradingcat/services/research.py](/Users/miau/Documents/TradingCat/tradingcat/services/research.py)
- [tradingcat/services/selection.py](/Users/miau/Documents/TradingCat/tradingcat/services/selection.py)
- [tradingcat/services/allocation.py](/Users/miau/Documents/TradingCat/tradingcat/services/allocation.py)

### B. Persistent universe and research baseline

- Instrument catalog is now persistent and filterable by enabled/tradable/liquidity status.
- Strategy research moved off `sample_instruments()` as the primary path and onto market-driven universe selection.
- Baseline history sync now seeds a minimal reproducible research universe instead of relying on ad hoc cached data.

Primary files:

- [tradingcat/services/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/services/market_data.py)
- [tradingcat/routes/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/routes/market_data.py)
- [tradingcat/strategies/simple.py](/Users/miau/Documents/TradingCat/tradingcat/strategies/simple.py)
- [tradingcat/domain/models.py](/Users/miau/Documents/TradingCat/tradingcat/domain/models.py)

### C. Trigger, execution, reconcile, and audit traceability

- RSI and SMA trigger conditions now use real indicator inputs.
- Trigger evaluations now persist indicator snapshots and explicit non-trigger reasons.
- Execution tracks expected vs realized price context, TCA sample breakdown, and authorization source.
- Reconcile / manual fill / audit now connect order intent, authorization, reconciliation source, portfolio effect, and status transitions.

Primary files:

- [tradingcat/services/rule_engine.py](/Users/miau/Documents/TradingCat/tradingcat/services/rule_engine.py)
- [tradingcat/services/execution.py](/Users/miau/Documents/TradingCat/tradingcat/services/execution.py)
- [tradingcat/services/reconciliation.py](/Users/miau/Documents/TradingCat/tradingcat/services/reconciliation.py)
- [tradingcat/services/audit.py](/Users/miau/Documents/TradingCat/tradingcat/services/audit.py)

### D. Acceptance, rollout, and go-live evidence chain

- Operations journal now persists explicit evidence tags such as `clean_day`, `manual_day`, `incident_day`, and `blocked_day`.
- Weekly/acceptance/live-acceptance/go-live/report archive flows now consume the same evidence chain.
- Readiness and gate responses now surface reconciliation mismatch and execution blocker details rather than only boolean red/green status.

Primary files:

- [tradingcat/services/operations.py](/Users/miau/Documents/TradingCat/tradingcat/services/operations.py)
- [tradingcat/services/operations_analytics.py](/Users/miau/Documents/TradingCat/tradingcat/services/operations_analytics.py)
- [tradingcat/services/reporting.py](/Users/miau/Documents/TradingCat/tradingcat/services/reporting.py)
- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)

### E. Final dashboard / diagnostics alignment

The final closeout commit focused on the last 6 plan items:

- `/preflight/startup`, `/diagnostics/summary`, and `/ops/readiness` now align on the same research blockers
- dashboard strategy rows now expose `display_status` and `status_reason`
- dashboard operations now exposes `acceptance_progress`
- regression coverage was added for these paths

Primary files:

- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
- [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
- [tradingcat/routes/preflight.py](/Users/miau/Documents/TradingCat/tradingcat/routes/preflight.py)
- [static/dashboard_strategy.js](/Users/miau/Documents/TradingCat/static/dashboard_strategy.js)
- [static/dashboard_operations.js](/Users/miau/Documents/TradingCat/static/dashboard_operations.js)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)
- [tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)

## 4. Architecture Corrections During The Run

Part of this run introduced mild architectural drift. The final closeout deliberately corrected the most obvious harness-induced decay instead of only shipping features.

The key corrections were:

- dashboard/readiness aggregations now use short-lived summary caching in [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py) so one request does not recompute the same heavy summaries multiple times
- [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py) no longer recomputes selection/allocation summary inside the strategy-row loop
- `dashboard/summary` no longer triggers implicit plan/summary generation as a side effect of a GET request; it now returns explicit fallback notes when no archive exists
- dashboard now reuses one `strategy_signal_map + build_profit_scorecard` path instead of recomputing a second full strategy report just to get portfolio metrics

This matters because the main risk near the end of the harness was not correctness regression, but soft boundary erosion in `app.py` and `facades.py`.

## 5. Validation Completed

The final closeout verification included:

- `.venv/bin/pytest tests/test_research_reporting.py tests/test_selection_service.py tests/test_allocation_service.py tests/test_dashboard_facade.py tests/test_reports_helper.py tests/test_operations_journal.py tests/test_api.py::test_preflight_and_readiness_align_research_blockers tests/test_api.py::test_dashboard_page_and_assets tests/test_api.py::test_dashboard_summary_endpoint tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress -q`
  - result: `53 passed`

Real HTTP verification was also run on an isolated instance:

- `GET /preflight/startup`
  - confirmed `healthy=true`, `research_ready=false`, `system_ready=false`
- `GET /diagnostics/summary`
  - confirmed synthetic fallback / missing history blockers appear in top-level `blockers`
- `GET /ops/readiness`
  - confirmed readiness blocker list aligns with `research_readiness.blocking_reasons`
- `GET /dashboard/summary`
  - confirmed `details.acceptance_progress` exists
  - confirmed `strategy_c_option_overlay.display_status="blocked_by_data"`

## 6. Recommended Review Entry Points

If Opus 4.6 is doing a focused review, these are the best starting points:

1. Research gating semantics
   - [tradingcat/services/strategy_analysis.py](/Users/miau/Documents/TradingCat/tradingcat/services/strategy_analysis.py)
   - Check whether `data_ready`, `promotion_blocked`, `validation_status`, and top-level `report_status` remain internally consistent.

2. App-layer aggregation boundaries
   - [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
   - Review the new summary cache and ensure it does not hide stale state or break side-effect expectations.

3. Dashboard aggregation logic
   - [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
   - Check status derivation for `blocked_by_data`, `paper_only`, and fallback note behavior.

4. Frontend rendering contract
   - [static/dashboard_strategy.js](/Users/miau/Documents/TradingCat/static/dashboard_strategy.js)
   - [static/dashboard_operations.js](/Users/miau/Documents/TradingCat/static/dashboard_operations.js)
   - Confirm new fields are consumed safely and do not create misleading states.

5. Regression coverage adequacy
   - [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)
   - [tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)
   - Check whether the tests are asserting behavior at the right level rather than overfitting to implementation details.

## 7. Known Residual Risks

- `tests/test_api.py::test_preflight_and_broker_recovery_endpoints` remains very slow when run alone. The functionality was covered by narrower API tests plus real HTTP validation, but the test itself is still a candidate for later slimming or decomposition.
- `TradingCatApplication` is still a large orchestrator even after the cache/aggregation cleanup. This harness stopped short of a bigger service extraction to avoid destabilizing the final delivery.
- `strategy_c_option_overlay` still has a realistic "blocked because option-history path is synthetic" posture. That is intentional, but reviewers should confirm this remains honest and not accidentally over-promoted elsewhere.

## 8. Workspace Notes

This harness delivery intentionally did not modify the user's pre-existing dirty files:

- [docs/codex-harness-engineering.md](/Users/miau/Documents/TradingCat/docs/codex-harness-engineering.md)
- [init.sh](/Users/miau/Documents/TradingCat/init.sh)
- [scripts/codex_harness/permission_guard.sh](/Users/miau/Documents/TradingCat/scripts/codex_harness/permission_guard.sh)

All harness features are complete, and the delivery commit series ends at:

- `299f1bd dashboard: align readiness diagnostics and gating`
