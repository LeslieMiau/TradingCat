# TradingCat Harness 交付报告

日期：2026-03-29
读者：Opus 4.6 reviewer
范围：30 天个人交易者 harness plan 已全部完成（`PLAN.json` 48/48）
最新交付 commit：`299f1bd dashboard: align readiness diagnostics and gating`

## 1. 执行摘要

本轮 harness 完成了 `PLAN.json` 的全部 backlog，并围绕一个核心目标收紧 TradingCat：不要把 synthetic 或不完整研究误判为 production-ready。

主要目标包括：

- 让数据、执行和验收阻塞项在 research、readiness、diagnostics、dashboard 和 reports 中都可见。
- 把项目从“控制平面原型”推进到更接近个人交易者运营复盘面的状态。
- 保持策略 promotion、执行授权、对账、审计和 rollout evidence 的链路可追踪。

最高价值结果：

- Research gating 已端到端显式化。
- 持久化研究股票池和最小真实历史基线已落地。
- 策略信号从样本驱动转向市场/历史驱动。
- Trigger / execution / reconcile / audit 形成可追踪链路。
- Acceptance / rollout / go-live evidence 已持久化并一致暴露。
- Dashboard 不再夸大 readiness，并能区分 `blocked_by_data` 与 `paper_only` 状态。

## 2. 交付形态

工作以一系列聚焦 commit 落地，最后到：

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

## 3. 新增内容

### A. 研究可信度和数据门禁

- `StrategyAnalysisService` 返回显式 `data_source`、`data_ready`、`promotion_blocked`、`blocking_reasons`、`validation_status`、`minimum_history_coverage_ratio` 和顶层 hard-block 语义。
- Selection 和 allocation 防御性地把 blocked strategy 降级为 `paper_only` / `shadow`，即使上游 recommendation 回归也不会误升档。
- 公司行为和 FX 覆盖成为一等研究输入，不再是静默假设。

主要文件：

- [tradingcat/services/strategy_analysis.py](/Users/miau/Documents/TradingCat/tradingcat/services/strategy_analysis.py)
- [tradingcat/services/research.py](/Users/miau/Documents/TradingCat/tradingcat/services/research.py)
- [tradingcat/services/selection.py](/Users/miau/Documents/TradingCat/tradingcat/services/selection.py)
- [tradingcat/services/allocation.py](/Users/miau/Documents/TradingCat/tradingcat/services/allocation.py)

### B. 持久化股票池和研究基线

- Instrument catalog 现在持久化，并可按 enabled / tradable / liquidity 状态过滤。
- 策略研究主路径从 `sample_instruments()` 转向市场驱动的 universe selection。
- Baseline history sync 会种下最小可复现研究股票池，不再依赖临时 cached data。

主要文件：

- [tradingcat/services/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/services/market_data.py)
- [tradingcat/routes/market_data.py](/Users/miau/Documents/TradingCat/tradingcat/routes/market_data.py)
- [tradingcat/strategies/simple.py](/Users/miau/Documents/TradingCat/tradingcat/strategies/simple.py)
- [tradingcat/domain/models.py](/Users/miau/Documents/TradingCat/tradingcat/domain/models.py)

### C. Trigger、执行、对账和审计可追踪

- RSI 和 SMA trigger 条件使用真实指标输入。
- Trigger evaluation 持久化指标快照，并显式记录未触发原因。
- Execution 记录 expected vs realized price context、TCA sample breakdown 和 authorization source。
- Reconcile / manual fill / audit 连接 order intent、authorization、reconciliation source、portfolio effect 和状态迁移。

主要文件：

- [tradingcat/services/rule_engine.py](/Users/miau/Documents/TradingCat/tradingcat/services/rule_engine.py)
- [tradingcat/services/execution.py](/Users/miau/Documents/TradingCat/tradingcat/services/execution.py)
- [tradingcat/services/reconciliation.py](/Users/miau/Documents/TradingCat/tradingcat/services/reconciliation.py)
- [tradingcat/services/audit.py](/Users/miau/Documents/TradingCat/tradingcat/services/audit.py)

### D. Acceptance、rollout 和 go-live 证据链

- Operations journal 持久化 `clean_day`、`manual_day`、`incident_day`、`blocked_day` 等 evidence tag。
- Weekly / acceptance / live-acceptance / go-live / report archive 流程消费同一条 evidence chain。
- Readiness 和 gate response 暴露 reconciliation mismatch 与 execution blocker 细节，而不只是布尔红绿状态。

主要文件：

- [tradingcat/services/operations.py](/Users/miau/Documents/TradingCat/tradingcat/services/operations.py)
- [tradingcat/services/operations_analytics.py](/Users/miau/Documents/TradingCat/tradingcat/services/operations_analytics.py)
- [tradingcat/services/reporting.py](/Users/miau/Documents/TradingCat/tradingcat/services/reporting.py)
- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)

### E. 最终 dashboard / diagnostics 对齐

最终 closeout commit 处理最后 6 个 plan item：

- `/preflight/startup`、`/diagnostics/summary` 和 `/ops/readiness` 对齐同一组 research blocker。
- Dashboard strategy rows 暴露 `display_status` 和 `status_reason`。
- Dashboard operations 暴露 `acceptance_progress`。
- 为这些路径补充回归覆盖。

主要文件：

- [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
- [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
- [tradingcat/routes/preflight.py](/Users/miau/Documents/TradingCat/tradingcat/routes/preflight.py)
- [static/dashboard_strategy.js](/Users/miau/Documents/TradingCat/static/dashboard_strategy.js)
- [static/dashboard_operations.js](/Users/miau/Documents/TradingCat/static/dashboard_operations.js)
- [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)
- [tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)

## 4. 本轮架构修正

本轮一度引入轻微架构漂移。最终 closeout 有意修复最明显的 harness-induced decay，而不是只继续堆功能。

关键修正：

- Dashboard/readiness 聚合在 [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py) 中使用短生命周期 summary cache，避免一次请求重复计算同一批重型摘要。
- [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py) 不再在 strategy-row loop 内重复计算 selection/allocation summary。
- `dashboard/summary` 不再通过 GET 请求隐式生成 plan/summary；没有 archive 时返回显式 fallback notes。
- Dashboard 复用同一条 `strategy_signal_map + build_profit_scorecard` 路径，而不是为了 portfolio metrics 再计算一整份 strategy report。

这很重要，因为 harness 后期的主要风险不是正确性回归，而是 `app.py` 和 `facades.py` 的软边界侵蚀。

## 5. 已完成验证

最终 closeout 验证包括：

```bash
.venv/bin/pytest tests/test_research_reporting.py tests/test_selection_service.py tests/test_allocation_service.py tests/test_dashboard_facade.py tests/test_reports_helper.py tests/test_operations_journal.py tests/test_api.py::test_preflight_and_readiness_align_research_blockers tests/test_api.py::test_dashboard_page_and_assets tests/test_api.py::test_dashboard_summary_endpoint tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress -q
```

结果：`53 passed`

也在隔离实例上做了真实 HTTP 验证：

- `GET /preflight/startup`：确认 `healthy=true`、`research_ready=false`、`system_ready=false`。
- `GET /diagnostics/summary`：确认 synthetic fallback / missing history blocker 出现在顶层 `blockers`。
- `GET /ops/readiness`：确认 readiness blocker list 与 `research_readiness.blocking_reasons` 对齐。
- `GET /dashboard/summary`：确认存在 `details.acceptance_progress`，且 `strategy_c_option_overlay.display_status="blocked_by_data"`。

## 6. 推荐审查入口

1. Research gating 语义
   [tradingcat/services/strategy_analysis.py](/Users/miau/Documents/TradingCat/tradingcat/services/strategy_analysis.py)
   检查 `data_ready`、`promotion_blocked`、`validation_status` 和顶层 `report_status` 是否内部一致。

2. App 层聚合边界
   [tradingcat/app.py](/Users/miau/Documents/TradingCat/tradingcat/app.py)
   审查新 summary cache 是否隐藏 stale state 或破坏副作用预期。

3. Dashboard 聚合逻辑
   [tradingcat/facades.py](/Users/miau/Documents/TradingCat/tradingcat/facades.py)
   检查 `blocked_by_data`、`paper_only` 和 fallback note 行为的状态推导。

4. 前端渲染 contract
   [static/dashboard_strategy.js](/Users/miau/Documents/TradingCat/static/dashboard_strategy.js)、[static/dashboard_operations.js](/Users/miau/Documents/TradingCat/static/dashboard_operations.js)
   确认新字段被安全消费，不会制造误导状态。

5. 回归覆盖充分性
   [tests/test_api.py](/Users/miau/Documents/TradingCat/tests/test_api.py)、[tests/test_dashboard_facade.py](/Users/miau/Documents/TradingCat/tests/test_dashboard_facade.py)
   检查测试是否断言正确层级的行为，而不是过拟合实现细节。

## 7. 已知剩余风险

- `tests/test_api.py::test_preflight_and_broker_recovery_endpoints` 单独运行时仍很慢。功能已由更窄 API 测试和真实 HTTP 验证覆盖，但该测试仍适合后续拆瘦。
- 即使完成 cache/aggregation 清理，`TradingCatApplication` 仍是大型 orchestrator。本轮没有继续大规模 service extraction，以避免 destabilize 最终交付。
- `strategy_c_option_overlay` 仍保持“因 option-history 路径 synthetic 而 blocked”的真实姿态。这是有意设计，但 reviewer 应确认其他地方不会意外把它过度 promotion。

## 8. 工作区说明

本轮 harness 交付没有修改用户已有的 dirty files：

- [docs/codex-harness-engineering.md](/Users/miau/Documents/TradingCat/docs/codex-harness-engineering.md)
- [init.sh](/Users/miau/Documents/TradingCat/init.sh)
- [scripts/codex_harness/permission_guard.sh](/Users/miau/Documents/TradingCat/scripts/codex_harness/permission_guard.sh)

所有 harness feature 已完成，交付 commit series 结束于：

- `299f1bd dashboard: align readiness diagnostics and gating`
