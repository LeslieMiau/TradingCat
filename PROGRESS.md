## Harness initialized — 2026-03-28
- Project type: Python 3.12+ / FastAPI / pytest / local-first trading control plane.
- Features planned: 48
- init.sh generated: skipped (already exists and executable)
- .gitignore updated: skipped (already contains PLAN.json / PROGRESS.md)
- Existing work detected:
  - 架构拆分、dashboard 前端重构、共享组件/API registry 已完成。
  - 研究、执行、验收、rollout、报告链路已有较完整骨架，当前最缺的是“研究可信度闸门”与个人交易者真正能依赖的证据闭环。
  - 最近一次 harness 已清理，当前需要重新建立 30 天个人交易者版任务状态。
- Key decisions:
  - 这次 30 天主线按“个人真钱可用性”排序，不优先做更像机构前台的外观或情报终端感。
  - 第一项 feature 固定为“禁止 synthetic 研究结果被静默当真”，因为这是后续 universe、策略、验收与 rollout 可信度的前置闸门。
  - 现有未提交改动存在于 docs/init/shell 脚本中，本次不覆盖这些无关改动，只新增 harness 状态文件并在独立提交中推进当前 feature。

## Session update — 2026-03-28
- Completed feature #1: 研究/推荐/筛选链路对 synthetic 数据源返回显式阻塞或降级状态，禁止策略在 synthetic 条件下进入 keep/active。
- Code changes:
  - `ResearchService.run_experiment()` 现在区分 `threshold_validation_passed` 与 `data_ready`，并把 `synthetic` / 历史缺失原因写入 `data_blockers`。
  - `StrategyAnalysisService` 现在把 `promotion_blocked`、`blocking_reasons`、`data_ready`、`data_source` 暴露到 report / recommendation / scorecard / strategy detail。
  - recommendation 逻辑优先按数据就绪性降级：数据未就绪时强制 `paper_only`，不再静默进入 `keep` / `active`。
- Validation:
  - `.venv/bin/pytest tests/test_research_reporting.py tests/test_selection_service.py tests/test_allocation_service.py tests/test_api.py -q` -> `32 passed`
  - 使用仓库 venv 的独立 `ResearchService` 验证 synthetic 场景时，推荐结果为 `paper_only`，并带有 `promotion_blocked=true` 与明确 `blocking_reasons`。
- Decisions:
  - 这一步只收紧“synthetic 不能静默当真”的闸门，不同时扩大到 universe / 策略重写，避免一次 session 改太多上下游。
  - 对运行中应用做 `TestClient` 烟雾时触发了 Futu 历史行情权限报错，这进一步证明显式 blocker 有必要；本次不顺带改行情权限/适配器策略。
- Remaining focus for next session:
  - feature #2 与 #11：把 scorecard / strategy detail / research report 的阻塞信息进一步对齐，并确保 dashboard/selection 消费这些状态时不误导。

## Session update — 2026-03-29
- Completed feature #2: 研究 `scorecard / report / strategy detail` 接口显式暴露 `synthetic / historical` 状态、阻塞原因与推广限制。
- Code changes:
  - `ResearchScorecardResponse` / `ResearchScorecardRowView` 现在显式包含 `blocked_count`、`blocked_strategy_ids`、`data_source`、`data_ready`、`promotion_blocked`、`blocking_reasons`。
  - `StrategyAnalysisService.summarize_strategy_report()` 现在返回顶层 `blocked_count`、`blocked_strategy_ids`、`ready_strategy_ids`，不需要调用方自己扫描整份 `strategy_reports`。
  - `StrategyAnalysisService.strategy_detail()` 现在把 `data_source`、`data_ready`、`promotion_blocked`、`blocking_reasons` 提升到顶层，避免前端只能从 `assumptions` 或 `recommendation` 里推断。
- Validation:
  - `.venv/bin/pytest tests/test_research_reporting.py tests/test_api.py -q` -> `28 passed`
  - 使用 `TestClient(app)` 验证 `/research/report/run`、`/research/scorecard/run`、`/research/strategies/{id}` 都能返回显式 blocker 字段。
  - 在当前本机 Futu 行情权限不足的情况下，接口会返回 `promotion_blocked=true` 和明确 `blocking_reasons`，而不是静默给出“看起来健康”的研究结果。
- Decisions:
  - 本 session 只做一个 feature，遵守仓库 harness 规则；虽然这次也触及了 report 侧的 blocker 汇总，但仍归属于“接口显式暴露阻塞语义”这一单一 feature。
  - 没有顺带改 dashboard 展示，以避免跨到下一个 UI feature；当前先保证 API 语义稳定，再让前端消费。
- Remaining focus for next session:
  - feature #11：让 `/research/report/run` 的“硬阻塞”语义更直观，避免调用方把 `blocked_count > 0` 但 `200 OK` 误解为研究通过。
