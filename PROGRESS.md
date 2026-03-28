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
