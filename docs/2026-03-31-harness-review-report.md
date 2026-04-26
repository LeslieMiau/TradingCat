# TradingCat Harness 交付报告

日期：2026-03-31
读者：Opus 4.6 审阅人
范围：工程阻塞项 harness cycle 已全部完成（`PLAN.json` 12/12）
最新交付 commit：`7655ee5 harness: finish control-plane blocker alignment`

## 1. 执行摘要

这轮 harness cycle 比 2026-03-29 的交付范围更窄。它不试图让 TradingCat 立即达到实盘就绪，而是集中清理让控制平面“不诚实”或不稳定的工程阻塞项：

- 常驻 `:8000` 进程行为与新进程不一致。
- readiness 把候选策略过度计入生产阻塞项。
- 阻塞原因跨不相关 symbol 外溢。
- `data_quality` 与 `research_ready` 语义漂移。
- `go-live` / `live-acceptance` / `dashboard` 混合了诊断噪声、rollout 阻塞和真正工程阻塞。
- rollout policy 不匹配（`100%` policy vs `hold` recommendation）虽然可见，但没有升格为一等阻塞项。

本轮结束时：

- 常驻 `:8000` 和新启动的 `uvicorn` 在关键 gate endpoint 上一致。
- 生产 readiness 只考虑默认执行策略。
- 阻塞原因已收敛到真实 signal 依赖。
- 缺少候选快照时 dashboard 不再空白。
- rollout policy mismatch 已在 go-live 和 live-acceptance 中成为明确阻塞项。
- `PLAN.json` 完成，worktree 干净。

这是工程完成状态，不代表真实资金实盘就绪。

## 2. 交付形态

本轮落地为 3 个主要 commit：

- `df3b8f5` `harness: align resident blocker inputs with fresh runtime`
- `c79200c` `harness: narrow readiness blockers to execution strategies`
- `7655ee5` `harness: finish control-plane blocker alignment`

第一个 commit 稳定常驻进程与新进程的事实口径；第二个 commit 把 research-readiness gate 缩到真实执行集；最后一个 commit 清理剩余控制平面语义和 dashboard fallback 行为。

## 3. 变更内容

### A. 常驻运行时和新运行时事实口径一致

- Instrument catalog refresh 会更新长生命周期 resident state，避免 `:8000` 持有过期 blocker 输入。
- resident/fresh parity 被作为真正验收标准，而不是事后检查。
- service health verification 覆盖 `/preflight/startup`、`/ops/readiness`、`/ops/go-live` 和 `/ops/live-acceptance`。

主要文件：

- [tradingcat/services/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/services/market_data.py)
- [tradingcat/repositories/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/repositories/market_data.py)
- [tests/test_market_data_service.py](/Users/miau/Documents/TradingCat/tests/test_market_data_service.py)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)

### B. Research readiness 只 gate 生产执行集

- `ReadinessQueryService.research_readiness_summary()` 不再把研究候选策略 `d/e/f/g` 拉进顶层生产 gate。
- readiness 仍报告真实阻塞项，但只针对 `strategy_a_etf_rotation`、`strategy_b_equity_momentum` 和 `strategy_c_option_overlay`。
- 候选策略阻塞项保留在 research surface，不再抬高 operations readiness。

主要文件：

- [tradingcat/services/query_services.py](/Users/miau/Documents/TradingCat/tradingcat/services/query_services.py)
- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
- [tests/test_runtime_recovery.py](/Users/miau/Documents/TradingCat/tests/test_runtime_recovery.py)

### C. 阻塞项范围绑定到真实 signal 依赖

- 公司行为和 FX 阻塞项按当前 signal set 中真实出现的 symbol 与 quote currency 断言。
- 基础策略不再继承 candidate/universe 扩展扫描中的无关 symbol 阻塞项。
- 这让 live operations review 里的阻塞解释保持可读。

主要文件：

- [tests/test_research_reporting.py](/Users/miau/Documents/TradingCat/tests/test_research_reporting.py)
- [tradingcat/services/query_services.py](/Users/miau/Documents/TradingCat/tradingcat/services/query_services.py)

### D. 控制平面阻塞语义清理

- `rollout_policy_summary()` 现在返回 `recommended_stage`、`policy_matches_recommendation`、`blocking_reasons`。
- `go_live_summary()` 将阻塞类别拆成 `engineering_blockers`、`rollout_blockers`、`policy_blockers`。
- 顶层 `go_live.blockers` 仍提供合并后的操作员视图，但 info 级诊断不再被当成一等阻塞项。
- `live_acceptance_summary()` 新增 `next_requirement`，明确剩余 clean-day/week gate。

主要文件：

- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)

### E. Dashboard fallback 变得诚实且可用

- 持久化候选快照缺失时，策略面板回退到当前 `research_readiness.strategies`。
- fallback 保留 `display_status`、`status_reason`、`blocked_by_data_count`。
- Dashboard 仍不会在 GET 请求中触发 live candidate scorecard 重算，只使用最小策略状态 fallback。
- Dashboard 上的 acceptance progress 更贴近 `live_acceptance`，并包含当前 `next_requirement`。

主要文件：

- [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
- [tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)

## 4. 已完成验证

定向回归：

```bash
.venv/bin/pytest tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers tests/test_api.py::test_dashboard_summary_uses_live_research_readiness_rows_when_snapshot_missing tests/test_dashboard_facade.py tests/test_runtime_recovery.py::test_research_readiness_limits_gate_to_default_execution_strategies -q
```

结果：`8 passed`

更宽的收尾回归：

```bash
.venv/bin/pytest tests/test_runtime_recovery.py tests/test_dashboard_facade.py tests/test_selection_service.py tests/test_allocation_service.py tests/test_rollout_policy.py tests/test_service_health.py tests/test_api.py::test_preflight_and_readiness_align_research_blockers tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress tests/test_api.py::test_dashboard_summary_uses_live_research_readiness_rows_when_snapshot_missing tests/test_api.py::test_dashboard_summary_returns_missing_snapshot_without_live_scorecard_recompute -q
```

结果：`35 passed`

Resident/fresh HTTP health：

- `.venv/bin/python -m tradingcat.services.service_health --base-url http://127.0.0.1:8000 --timeout 5`：四个 gate endpoint 全部 healthy。
- `.venv/bin/python -m tradingcat.services.service_health --base-url http://127.0.0.1:8053 --timeout 5`：四个 gate endpoint 全部 healthy。

Resident vs fresh 结构一致性：

- 对比 `/preflight/startup`
- 对比 `/ops/readiness`
- 对比 `/ops/go-live`
- 对比 `/ops/live-acceptance`
- 对比 `/dashboard/summary?as_of=2026-03-31`
- 结果：`mismatches: []`

常驻进程重启后的关键观察：

- `/ops/readiness`：`data_quality.ready=true`，`research_readiness.blocked_strategy_ids=["strategy_a_etf_rotation","strategy_b_equity_momentum","strategy_c_option_overlay"]`。
- `/ops/go-live`：`policy_matches_recommendation=false`，`policy_blockers=["Active rollout policy 100% does not match recommended stage hold."]`。
- `/ops/live-acceptance`：`next_requirement.remaining_clean_days=28`。
- `/dashboard/summary?as_of=2026-03-31`：即使 `snapshot_status="missing"`，策略行仍存在；`blocked_by_data_count=3`；acceptance progress blocker 与 live-acceptance blocker 对齐。

## 5. 推荐审查入口

1. 生产 readiness 范围
   [tradingcat/services/query_services.py](/Users/miau/Documents/TradingCat/tradingcat/services/query_services.py)
   确认顶层 readiness gate 现在有意排除研究候选策略，同时保持诚实阻塞语义。

2. App 层 gate 组合
   [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
   审查 `execution_gate_summary()`、`go_live_summary()`、`live_acceptance_summary()` 和 `rollout_policy_summary()` 的关系。

3. Dashboard fallback contract
   [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
   确认 snapshot-missing fallback 是最小、只读的，并且不会夸大候选策略 readiness。

4. 回归覆盖真实性
   [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)、[tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)、[tests/test_runtime_recovery.py](/Users/miau/Documents/TradingCat/tests/test_runtime_recovery.py)
   检查测试是否验证用户可见语义，而不是脆弱的实现细节。

## 6. 已知剩余风险

- `TradingCatApplication` 仍是较大的编排外壳。本轮收紧了 contract，但没有做更大抽取，因为目标是 parity 和诚实状态，而不是另一轮架构大改。
- 部分 typed response 仍有 Pydantic serialization warning。它们没有阻塞本轮 harness，但适合作为后续 cleanup。
- Dashboard fallback 只重建最小策略状态行，不重建完整 candidate scorecard。这是有意取舍，但审阅时应确认该限制符合产品/运维预期。
- `go-live` 仍包含来自 diagnostics 和 rollout 的操作员下一步动作。阻塞项拆分已经更清晰，但审阅时仍可继续挑战“诊断信号”和“升档阻塞”的边界。

## 7. 本报告不声称的内容

本报告不声称 TradingCat 已可投入真实资金。

仍然存在以下外部或运营 gate：

- OpenD / broker validation 尚未完成。
- Compliance checklist 仍有 pending 项。
- Acceptance evidence 仍是 `ready_weeks=0` 和 `cn_manual_weeks=0`。
- 活跃执行策略在公司行为 / FX 完整性上仍有真实 research blocker。

正确结论是：

- 工程阻塞项清理已完成。
- 控制平面语义更诚实、更稳定。
- 真实资金就绪仍被外部证据和剩余市场数据完整性阻塞。

## 8. 最终工作区状态

Harness cycle 已完全关闭：

- [PLAN.json](/Users/miau/Documents/TradingCat/PLAN.json) 为 `12/12` complete。
- [PROGRESS.md](/Users/miau/Documents/TradingCat/PROGRESS.md) 包含完整会话日志和最终证据。
- Worktree 干净。

最终 commit chain：

- `df3b8f5` `harness: align resident blocker inputs with fresh runtime`
- `c79200c` `harness: narrow readiness blockers to execution strategies`
- `7655ee5` `harness: finish control-plane blocker alignment`
