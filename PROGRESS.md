# PROGRESS

## 2026-04-09 08:09:54 CST - Harness initialization for market-awareness capability

- User request: add market-awareness capability to TradingCat so the system can read market trend and produce operator guidance; user explicitly asked to write the plan first and then execute through harness.
- Restore sequence completed:
  - `pwd`
  - `git log --oneline -20`
  - Read `/Users/miau/Documents/TradingCat/README.md`
  - Read `/Users/miau/Documents/TradingCat/PLAN.md`
  - Ran `bash ~/.codex/scripts/global-init.sh`
- Harness state on entry:
  - `PLAN.json` missing
  - `PROGRESS.md` missing
  - `.harness/` missing
  - Repo therefore requires fresh harness initialization before feature work.
- Current repo state notes:
  - Existing `init.sh` already present and executable.
  - Unrelated untracked file left untouched: `docs/2026-03-31-harness-review-report.md`
- Baseline verification:
  - Ran `./.venv/bin/pytest tests/test_api.py -q`
  - Result: `6 failed, 48 passed`
  - Failing tests captured before feature work:
    - `test_research_interfaces_expose_data_blockers`
    - `test_ops_evaluate_triggers_uses_real_rsi_series`
    - `test_ops_evaluate_triggers_uses_real_sma_series`
    - `test_orders_endpoint_exposes_expected_vs_realized_price_context`
    - `test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots`
    - `test_execution_run_endpoint`
  - Highest-priority blocker observed:
    - research scorecard/detail generation is still capable of hitting live Futu option-chain throttling (`Get Option Chain is too frequent`) and quote-right gaps during safe-mode tests; this must be stabilized before the new feature can be trusted.
- Planning decision:
  - Build the new capability as a dedicated market-awareness service plus query/API/dashboard integration.
  - Keep the feature advisory-only: it may produce posture and action guidance, but it must not auto-place or auto-approve trades.
  - Fix the current baseline regressions first, then implement market-awareness analytics, then expose the results through API and dashboard, then run focused pytest + local API/UI smoke validation.
- Harness artifacts initialized in this checkpoint:
  - `PLAN.json`
  - `PROGRESS.md`
  - `.harness/spec.md`
  - `.harness/status.json`

## 2026-04-09 08:09:54 CST - Checkpoint after planning bootstrap

- Marked the harness bootstrap feature complete:
  - fresh `PLAN.json` exists with 60 immutable feature entries
  - fresh `PROGRESS.md` exists with restored state and baseline findings
  - initialization checkpoint commit created: `6756f77 harness: initialize market awareness plan`
- Marked the baseline reproduction feature complete:
  - `./.venv/bin/pytest tests/test_api.py -q` reproduced the failing set
  - the failure list is now the entry gate before market-awareness feature work
- Marked the market-awareness product-contract feature complete:
  - `.harness/spec.md` now locks the advisory-only posture engine, new research endpoint shape, dashboard integration target, and delivery constraints
- Next active feature:
  - feature 3, stabilize research report / scorecard / strategy-detail generation when live Futu option-chain requests are throttled or quote rights are missing

## 2026-04-09 08:09:54 CST - Checkpoint after research-path stabilization

- Completed feature 3:
  - `ResearchQueryService` research endpoints now request signals through `local_history_only=True`, so report/scorecard/detail no longer force live option-chain reads during safe/test research flows.
  - `MarketDataService.fetch_option_chain()` now returns a deterministic synthetic option chain inside local-history-only mode.
  - `OptionHedgeStrategy.generate_signals()` now falls back safely instead of crashing when option-chain fetch fails.
- Completed feature 7:
  - `MarketDataService.ensure_history()` now backfills missing symbols with synthetic bars inside local-history-only mode, which lets research signal generation stay aligned with the persisted universe instead of reverting to sample instruments.
  - Strategy detail and report signal-insight payloads now continue to expose `historical_*` signal sources and indicator snapshots for persisted symbols like `IVV`, `VOO`, and `AAPL`.
- Verification:
  - `./.venv/bin/pytest tests/test_api.py -q -k 'research_interfaces_expose_data_blockers or research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots'`
  - Result: `2 passed`
- Remaining baseline failures still open after this checkpoint:
  - `test_ops_evaluate_triggers_uses_real_rsi_series`
  - `test_ops_evaluate_triggers_uses_real_sma_series`
  - `test_orders_endpoint_exposes_expected_vs_realized_price_context`
  - `test_execution_run_endpoint`
- Next active feature:
  - feature 4 / 5, restore trigger evaluation so RSI and SMA use the synced real series instead of stale fallback values

## 2026-04-09 08:21:54 CST - Checkpoint after trigger-series restoration

- Completed feature 4:
  - `RuleEngine._recent_closes()` now evaluates indicator series inside `MarketDataService.local_history_only()`, so trigger evaluation prefers synced local history and deterministic fallback bars before any live-adapter path.
  - `/ops/evaluate-triggers` now reads the real `RSI_14` series for `SPY` during safe-mode tests instead of returning a stale fallback observation with `data_ready=false`.
- Completed feature 5:
  - The same indicator-history fix restores `SMA_10` evaluation for trigger checks, so RSI and SMA use the same local-history-first path and stay consistent with the synced benchmark bars.
  - Missing-symbol behavior remains intact: unknown symbols still return `indicator_data_missing` rather than falsely passing trigger conditions.
- Verification:
  - `./.venv/bin/pytest tests/test_rule_engine.py -q -k 'rsi or sma or data_missing'`
  - Result: `5 passed`
  - `./.venv/bin/pytest tests/test_api.py -q -k 'test_ops_evaluate_triggers_uses_real_rsi_series or test_ops_evaluate_triggers_uses_real_sma_series or test_ops_evaluate_triggers_marks_indicator_data_missing'`
  - Result: `3 passed`
- Remaining baseline failures still open after this checkpoint:
  - `test_orders_endpoint_exposes_expected_vs_realized_price_context`
  - `test_execution_run_endpoint`
- Next active feature:
  - feature 6, restore reconciled order price-context fields on `/orders`
