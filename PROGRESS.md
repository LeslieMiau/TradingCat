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

## Session update — 2026-03-29
- Completed feature #11: `/research/report/run` 对历史覆盖不足与 synthetic fallback 返回顶层硬阻塞语义，不再看起来“通过验证”。
- Code changes:
  - `StrategyAnalysisService.summarize_strategy_report()` 现在为每个策略返回 `validation_status`、`history_coverage` 与 `minimum_coverage_ratio`，让调用方直接看到 `blocked / failed / passed`，不必再从多个布尔字段拼语义。
  - 报告顶层新增 `hard_blocked`、`report_status`、`blocking_reasons`、`minimum_history_coverage_ratio`；只要有策略因数据未就绪被阻塞，`portfolio_passed` 就会被强制压成 `false`。
  - 新增 partial-history 场景测试，锁定“历史覆盖不足 => 顶层 blocked”这一行为，同时更新 API 测试校验新字段存在。
- Validation:
  - `.venv/bin/pytest tests/test_research_reporting.py tests/test_api.py -q` -> `29 passed`
  - `curl -sS http://127.0.0.1:8010/preflight/startup` -> `healthy=true`
  - `curl -sS -X POST http://127.0.0.1:8010/research/report/run` -> 返回 `strategy_c_option_overlay.validation_status=\"blocked\"`、`hard_blocked=true`、`report_status=\"blocked\"`、`portfolio_passed=false`
- Decisions:
  - 没有把 `/research/report/run` 改成非 `200` HTTP 状态；当前这一步只收紧 payload 语义，避免影响既有调用方，再把更激进的 transport 语义调整留给后续单独 feature。
  - 本机 `8000` 端口上已有旧进程，返回的是旧 payload；本次 E2E 改用新起的 `8010` 进程验证当前代码，避免被陈旧服务误导。
- Remaining focus for next session:
  - feature #12：在 `/research/strategies/{strategy_id}` 中把 `history_coverage` 收紧成更面向操作的摘要，显式给出 `minimum_coverage_ratio`、阈值与缺失 symbol 清单。

## Session update — 2026-03-29
- Completed feature #12: 策略详情现在显式展示历史覆盖率、覆盖阈值、缺失 symbol 清单与 coverage blockers。
- Code changes:
  - `StrategyAnalysisService.strategy_detail()` 现在把 `minimum_coverage_ratio`、`history_coverage_threshold`、`missing_coverage_symbols`、`history_coverage_blockers` 提升到顶层，detail 调用方不需要自己扫描 `history_coverage.reports`。
  - `StrategyAnalysisService._strategy_history_coverage()` 现在统一暴露 `minimum_required_ratio`，并复用 helper 生成缺失 symbol 清单与更可执行的 blocker 文案。
  - `static/strategy.js` 的覆盖率区域现在直接展示 threshold、missing symbols 和 blocker 摘要，真正把这些字段展示到策略详情页。
- Validation:
  - `.venv/bin/pytest tests/test_research_reporting.py tests/test_api.py -q` -> `30 passed`
  - `curl -sS http://127.0.0.1:8011/preflight/startup` -> `healthy=true`
  - `curl -sS "http://127.0.0.1:8011/research/strategies/strategy_c_option_overlay?as_of=2026-03-29"` -> 返回 `minimum_coverage_ratio`、`history_coverage_threshold`、`missing_coverage_symbols`、`history_coverage_blockers`
- Decisions:
  - 本机真实 HTTP 场景里 `strategy_c_option_overlay` 属于 synthetic blocked，但因为是 option-only 链路，`missing_coverage_symbols` 合理地为空；缺失 symbol 场景通过新增的 partial-history 测试覆盖。
  - 这一步顺手把 detail 前端渲染接上，避免字段只存在于 API 而没有被页面消费，符合“策略详情展示”而不只是“策略详情返回”的目标。
- Remaining focus for next session:
  - feature #13：研究筛选 review 在历史不完整时强制降级到 `paper_only`，并确保 `/research/selections/summary` 不把历史不足策略暴露成 `active`。

## Session update — 2026-03-29
- Completed feature #13: selection review 现在会对数据未就绪策略做下游强制降级，确保不会因为上游回归而误进 `active`。
- Code changes:
  - `StrategySelectionService.review()` 现在在 `promotion_blocked=true` 或 `data_ready=false` 时把非 `drop` recommendation 强制归一到 `paper_only`，并追加显式的 selection-review blocker 原因。
  - 新增 selection service 测试，锁定“即便上游误给 keep，selection 也必须压成 paper_only”的防线。
  - 新增 API 集成测试，验证 `/research/selections/review` 与 `/research/selections/summary` 在 blocked 策略场景下都不会出现 `active`。
- Validation:
  - `.venv/bin/pytest tests/test_selection_service.py tests/test_research_reporting.py tests/test_api.py -q` -> `37 passed`
  - `curl -sS -X POST "http://127.0.0.1:8012/research/selections/review?as_of=2026-03-29"` -> 返回 `strategy_c_option_overlay.decision=\"paper_only\"`
  - `curl -sS http://127.0.0.1:8012/research/selections/summary` -> 返回 `active=[]`、`paper_only=[\"strategy_c_option_overlay\"]`
- Decisions:
  - 这一层做的是 defense-in-depth：即使上游 recommendation 未来回归，这里也不会放 blocked 策略漏进 active selection。
  - 没有把 `drop` 强行改成 `paper_only`；如果策略本来就因别的原因该被拒绝，仍保持 `rejected`，只对“原本可能推进”的 blocked 策略做降级。
- Remaining focus for next session:
  - feature #14：allocation review 对数据不完整策略也做同样的硬降级，禁止拿到 `active target_weight`，只允许 `paper_only/shadow`。

## Session update — 2026-03-29
- Completed feature #14: allocation review 现在会对 blocked 策略强制保留 `paper_only/shadow`，不会分配 live `target_weight`。
- Code changes:
  - `StrategyAllocationService.review()` 现在在 `promotion_blocked=true` 或 `data_ready=false` 时把非 `drop` recommendation 强制归一到 `paper_only`，并追加 allocation-review 的 shadow-mode 原因。
  - blocked 策略在 allocation 层会得到 `target_weight=0`、`shadow_weight=0.05`，同时 `summary.active` 和 `total_target_weight` 不会把它算进 live 资金。
  - 新增 allocation service 与 API 集成测试，锁定“blocked keep -> paper_only/shadow”这条防线。
- Validation:
  - `.venv/bin/pytest tests/test_allocation_service.py tests/test_selection_service.py tests/test_api.py -q` -> `23 passed`
  - `curl -sS -X POST "http://127.0.0.1:8013/research/allocations/review?as_of=2026-03-29"` -> 返回 `strategy_c_option_overlay.decision=\"paper_only\"`、`target_weight=0.0`、`shadow_weight=0.05`
  - `curl -sS http://127.0.0.1:8013/research/allocations/summary` -> 返回 `active=[]`，`paper_only` 中保留 `strategy_c_option_overlay`
- Decisions:
  - 和 selection 一样，这里做的是下游防线而不是只依赖上游 recommendation，防止未来回归把 blocked 策略漏进 live allocation。
  - 继续保留 `drop -> rejected` 的原语义，只把“理论上可推进但数据未就绪”的策略强制压到 `paper_only/shadow`，避免过度宽松或过度保守。
- Remaining focus for next session:
  - feature #15：让 `/data/history/coverage` 返回更明确的最小覆盖率摘要与可执行 blocker，给后续 repair-plan / data-quality 链路打底。

## Session update — 2026-03-29
- Completed feature #15: `/data/history/coverage` 现在返回最小覆盖率、覆盖阈值、缺失 symbol / 窗口摘要与可直接执行的 blocker。
- Code changes:
  - `MarketDataService.summarize_history_coverage()` 现在在顶层返回 `minimum_coverage_ratio`、`minimum_required_ratio`、`missing_symbols`、`missing_windows`、`blocked`、`blocker_count`、`blockers`。
  - 新增 coverage blocker helper，把“最低覆盖率低于阈值”“哪些 symbol 缺失”“下一步该跑什么 sync 命令”直接拼成可执行提示。
  - 新增 market-data service 与 API 测试，锁定正常与缺失两条路径的 coverage 摘要字段。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py tests/test_api.py -q` -> `25 passed`
  - `curl -sS "http://127.0.0.1:8014/data/history/coverage?symbols=SPY&start=2026-03-02&end=2026-03-06"` -> 返回 `minimum_coverage_ratio=1.0`、`blockers=[]`
  - `curl -sS "http://127.0.0.1:8014/data/history/coverage?symbols=QQQ&start=2026-03-02&end=2026-03-06"` -> 返回新增的 coverage 摘要字段结构
- Decisions:
  - 先把 coverage 摘要接口做完整，再让 `repair-plan`、`sync-status`、`data-quality` 逐步复用这些顶层字段，避免后续 feature 各自再重复拼摘要。
  - 真实 HTTP 里 `QQQ` 在该窗口上仍然返回 `blocked=false`，说明当前本机数据状态比单测更完整；blocked 路径由新增的 partial-history service 测试覆盖。
- Remaining focus for next session:
  - feature #16：history sync run 需要把 symbol 级成功/失败/缺失统计落到 run 记录和列表里，为长期数据质量追踪做准备。

## Session update — 2026-03-29
- Completed feature #16: history sync run 现在保存 symbol 级成功/失败/缺失统计，`/data/history/sync-runs` 可直接用于长期数据质量追踪。
- Code changes:
  - `HistorySyncRun` 新增 `successful_symbols`、`failed_symbols`、`failed_symbol_count`、`missing_symbol_count`、`symbol_stats`。
  - `HistorySyncService.record_run()` 现在从 sync result / coverage result 组装 symbol 级 `ok / failed / missing` 状态，并把失败 symbol 纳入 partial 判定与 notes。
  - 新增 market-data service 与 API 测试，验证 sync-runs 列表会返回这些 symbol 级字段。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py tests/test_api.py -q` -> `27 passed`
  - `curl -sS -X POST http://127.0.0.1:8015/data/history/sync ...` -> 返回 `run.successful_symbols=[\"SPY\"]`、`symbol_stats=[{\"symbol\":\"SPY\",\"status\":\"ok\",...}]`
  - `curl -sS http://127.0.0.1:8015/data/history/sync-runs` -> 返回 `successful_symbols`、`failed_symbols`、`failed_symbol_count`、`missing_symbol_count`、`symbol_stats`
- Decisions:
  - 历史 run 的旧记录会自然缺少这些新字段或为空数组，这是兼容接受的；从这次开始的新 run 会带完整 symbol 级统计。
  - 这里先把 symbol 级统计落到 run 记录本身，下一步 repair-plan 就可以直接拿这些字段做优先级排序，不必再重新拼 sync/coverage 两份结果。
- Remaining focus for next session:
  - feature #17：让 repair-plan 按缺口严重程度排序，优先修最影响研究主链路的 symbol 与窗口。

## Session update — 2026-03-29
- Completed feature #17: `/data/history/repair-plan` 现在会按研究优先级和缺口严重度排序，优先修最影响主链路的 symbol。
- Code changes:
  - `HistorySyncService.repair_plan()` 现在支持 `priority_symbols`，每个 repair 项新增 `coverage_ratio`、`priority_bucket`、`priority_rank`、`priority_reason`，并按优先级后再按缺口严重度排序。
  - `TradingCatApplication.history_sync_repair_plan()` 现在会从当前研究/候选策略信号里推导 `priority_symbols`，把 option 底层 symbol 也纳入优先级计算。
  - 新增 service 与 API 测试，锁定 repair-plan 的优先级排序和新字段。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py tests/test_api.py -q` -> `29 passed`
  - 在临时空数据目录上运行 `curl -sS "http://127.0.0.1:8016/data/history/repair-plan?symbols=SPY,0700&start=2026-03-02&end=2026-03-06"` -> 返回 `priority_symbols=[\"SPY\",\"0700\"]`，且 `repairs[0].symbol=\"SPY\"`
  - 同一临时环境下 `curl -sS "http://127.0.0.1:8016/data/history/coverage?symbols=SPY,0700&start=2026-03-02&end=2026-03-06"` -> 返回 `blocked=true`，证明 repair-plan 是基于真实 coverage 缺口排序
- Decisions:
  - 排序优先级先看研究主链路相关性，再看 `missing_count / coverage_ratio`；这样更符合“先修最影响研究的窗口”，而不是纯按缺口数量机械排序。
  - 用临时空数据目录做真实 HTTP 验证，避免被当前本地已有历史缓存掩盖 repair-plan 的排序效果。
- Remaining focus for next session:
  - feature #18：让 `/data/history/repair` 执行后自动返回 repair 前后 coverage 对比与复检结果，形成发现缺口 -> 修复 -> 复检闭环。

## Session update — 2026-03-29
- Completed feature #18: `/data/history/repair` 现在会返回 repair 前后 coverage 对比和复检结论，形成完整闭环。
- Code changes:
  - `MarketDataService.repair_history_gaps()` 现在返回 `coverage_before`、`coverage_after` 和 `recheck`，其中 `recheck` 会给出 `ready`、`improved_symbols`、`remaining_symbols` 与前后最小覆盖率。
  - 当没有 repair target 时，接口也会返回一份 no-op 的 recheck 结果，调用方不需要自己二次查询才能知道当前是否已 ready。
  - 新增 market-data service 与 API 测试，锁定 repair 闭环字段。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py tests/test_api.py -q` -> `30 passed`
  - 在临时空数据目录上运行 `POST /data/history/repair` for `SPY` -> 返回 `coverage_before.minimum_coverage_ratio=0.0`、`coverage_after.minimum_coverage_ratio=1.0`、`recheck.ready=true`
  - 紧接着顺序执行 `GET /data/history/coverage` for `SPY` -> 返回 `minimum_coverage_ratio=1.0`、`blocked=false`
- Decisions:
  - 这一步把“repair 后是否真的改善”直接放进 repair 响应本身，避免调用方必须自己手动对比两次 coverage。
  - 真实 HTTP 验证里我先并行打了 repair 和 coverage，读到的是修复前状态；随后按顺序重试确认了接口闭环本身没有问题。
- Remaining focus for next session:
  - feature #19：让 `data_quality_summary` / `/ops/readiness` 直接复用 coverage blockers，把研究主 universe 缺口抬升成显式 readiness blocker。

## Session update — 2026-03-29
- Completed feature #19: `data_quality_summary` 与 `/ops/readiness` 现在会把研究可推广性所需的数据就绪性抬升成显式 blocker。
- Code changes:
  - `TradingCatApplication.data_quality_summary()` 现在会优先检查 active execution symbols；如果当前没有 active 策略，则回退到研究主 universe 的优先 symbol，并返回 `scope`、`minimum_coverage_ratio`、`minimum_required_ratio`、`missing_symbols`、`blockers`。
  - `TradingCatApplication.operations_readiness()` 现在直接消费 `data_quality_summary()`，把 coverage blockers 暴露到顶层 `blockers`，同时把完整 `data_quality` 摘要挂进 readiness 响应。
  - `OperationsReadinessResponse` 与相关测试已更新，锁定 `/data/quality`、`/ops/readiness` 在 coverage 不足时都会返回 `ready=false` 与显式 blocker。
- Validation:
  - `.venv/bin/pytest tests/test_selection_service.py tests/test_api.py -q` -> `26 passed`
  - `curl -sS http://127.0.0.1:8018/preflight/startup` -> `healthy=true`
  - 在临时空数据目录上运行 `curl -sS http://127.0.0.1:8018/data/quality` -> 返回 `ready=false`、`scope="research_universe"`、`minimum_coverage_ratio=0.0`、显式 `blockers`
  - 同一临时环境下 `curl -sS http://127.0.0.1:8018/ops/readiness` -> 返回顶层 `blockers`，且 `data_quality.ready=false`
- Decisions:
  - 当没有 active execution strategy 时，这一步选择回退到研究主 universe，而不是返回“中性 ready”；这样 readiness 更符合“能不能把研究结果当真”的语义。
  - 顶层 readiness 当前只直接暴露数据 blocker 文案，不额外重复拼接 alerts/compliance 文案，避免一个响应里出现多套重复 blocker 文本。
- Remaining focus for next session:
  - feature #20：让公司行为覆盖率和缺失状态进入研究输出，避免个股/ETF 回测在拆股/分红场景下静默失真。

## Session update — 2026-03-29
- Completed feature #20: 公司行为覆盖率和缺失状态现在会进入研究输出，避免个股/ETF 回测在拆股/分红场景下静默失真。
- Code changes:
  - `MarketDataService` 新增公司行为覆盖摘要：会区分 `available / confirmed_none / missing`，并返回 `missing_symbols`、`blockers` 和 `actions_by_symbol`；`/data/history/corporate-actions` 也改为直接返回状态、阻塞信息和动作列表。
  - `ResearchService.run_experiment()` 现在把公司行为覆盖纳入 `data_ready` 判定，并把 `corporate_actions_ready`、`missing_corporate_action_symbols`、`corporate_action_blockers`、`corporate_action_coverage` 落进研究 assumptions。
  - `StrategyAnalysisService` 的 report/detail 现在会暴露这些公司行为字段，因此研究详情页与研究报告都能直接看到公司行为是否缺失、缺了谁、是否因此阻塞推广。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py tests/test_research_reporting.py tests/test_api.py -q` -> `52 passed`
  - `curl -sS http://127.0.0.1:8019/preflight/startup` -> `healthy=true`
  - 在临时空数据目录上运行 `curl -sS "http://127.0.0.1:8019/data/history/corporate-actions?symbol=SPY&start=2026-03-02&end=2026-03-06"` -> 返回 `status="confirmed_none"`、`ready=true`、`actions=[]`
  - 同一临时环境下 `curl -sS "http://127.0.0.1:8019/research/strategies/strategy_a_etf_rotation?as_of=2026-03-08"` -> 返回 `corporate_actions_ready`、`corporate_action_blockers`、`corporate_action_coverage`
- Decisions:
  - 对“窗口内确实没有公司行为”的场景，这一步显式标成 `confirmed_none`，避免把“没有动作”和“抓不到数据”混为一谈。
  - 缺失公司行为的强阻塞语义主要由新增单测锁定；真实 HTTP 则优先验证新字段已经稳定暴露，避免依赖外部行情源在当前时刻恰好返回缺失。
- Remaining focus for next session:
  - feature #21：让 FX 覆盖率与缺失状态进入研究输出，避免跨市场收益换算静默失真。

## Session update — 2026-03-29
- Completed feature #21: FX 覆盖率与缺失状态现在会进入研究输出，避免跨市场收益换算静默失真。
- Code changes:
  - `MarketDataService` 新增 FX 覆盖摘要：会返回 `available / missing` 状态、缺失 quote currencies、`blockers` 和 `rates_by_pair`；`/data/fx/rates` 也改为直接返回状态、阻塞信息和汇率列表。
  - `ResearchService.run_experiment()` 现在把 FX 覆盖纳入 `data_ready` 判定，并把 `fx_ready`、`missing_fx_pairs`、`fx_blockers`、`fx_coverage` 落进研究 assumptions，避免 FX 缺失时 backtest 静默走 synthetic FX fallback。
  - `StrategyAnalysisService` 的 report/detail 现在会暴露这些 FX 字段，因此策略详情和研究报告都能直接看到跨市场换算是否具备所需 FX 数据。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py tests/test_research_reporting.py tests/test_api.py -q` -> `56 passed`
  - `curl -sS http://127.0.0.1:8020/preflight/startup` -> `healthy=true`
  - 在临时空数据目录上运行 `curl -sS "http://127.0.0.1:8020/data/fx/rates?base_currency=CNY&quote_currency=USD&start=2026-03-02&end=2026-03-06"` -> 返回 `status="available"`、`ready=true`、`rate_count=1`
  - 同一临时环境下 `curl -sS "http://127.0.0.1:8020/research/strategies/strategy_a_etf_rotation?as_of=2026-03-08"` -> 返回 `fx_ready`、`fx_blockers`、`fx_coverage`
- Decisions:
  - 这一步把 FX 缺失 blocker 放在 research assumptions 层统一生成，而不是只在 route 层拼文案，这样 report/detail/scorecard 后续都能复用同一套语义。

## Harness cycle reset — 2026-03-30
- New cycle goal: 清理 resident/fresh 不一致与控制面工程阻塞，不把这轮扩展到真实券商权限、compliance 审批关闭或 4-8 周 paper-trading 证据累积。
- Existing work kept as history:
  - 上一轮 48 项 feature 已完成并留在 git 历史中，当前不再沿用旧 `PLAN.json`。
  - 这轮只围绕新的 12 项 blocker 计划推进，每个 session 继续只做一个 feature。
- Key decisions:
  - `data/quality=green` 与 `research_ready=false` 被视为允许存在的语义差异，前提是 blocker 解释清楚且各控制面一致。
  - 当前最优先修的是 resident `:8000` 与 fresh 进程不一致，因为它会污染后续所有 blocker 判断。

## Session update — 2026-03-30
- Completed feature #1: resident `:8000` core gate 健康检查现在可被稳定探测，旧引用/response 正规化问题不会再把 readiness 链路误判成坏服务。
- Code changes:
  - 新增 `tradingcat/services/service_health.py`，用 `http.client` 探测 `/preflight/startup`、`/ops/readiness`、`/ops/go-live`、`/ops/live-acceptance` 四个核心端点，输出 JSON 健康摘要并以 exit code 表达健康状态。
  - `init.sh` 现在用 core-health 代替单一 `/preflight` 探测；若 8000 上存在 repo 内的异常 TradingCat 进程，会优先识别并尝试重启，而不是把“只活端口”的服务当成正常。
  - `OperationsFacade.readiness()` 现在会把 `preflight / research_readiness / diagnostics / data_quality / alerts / compliance` 做默认壳层正规化，避免部分 stub、域模型对象或旧状态结构直接把 `/ops/readiness` 压成 400。
  - `TradingCatApplication` 初始化 `ReadinessQueryService` 时改为使用动态 getter，而不是绑定初始化时的方法引用，避免 `reset_state()`、monkeypatch 或长生命周期 resident 进程继续读取旧 rollout/data-quality 方法。
- Validation:
  - `.venv/bin/pytest tests/test_service_health.py tests/test_api.py::test_readiness_and_execution_gate_surface_execution_and_mismatch_blockers tests/test_api.py::test_preflight_and_readiness_align_research_blockers tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers -q` -> `5 passed`
  - 在持久 `run_local.sh` 会话上运行 `.venv/bin/python -m tradingcat.services.service_health --base-url http://127.0.0.1:8000 --timeout 5` -> `healthy=true`，四个核心端点全部 `status_code=200`
  - 同一 resident `:8000` 上运行 `curl -m 8 -sS http://127.0.0.1:8000/ops/readiness` -> 返回 `200 OK` 与当前 blocker JSON，不再出现 `Remote end closed connection without response`
- Decisions:
  - 把 probe 底层从 `urllib` 改成 `http.client`，因为前者在当前 uvicorn/reload 场景下会误报 `Remote end closed connection without response`，而 `curl` 与 `http.client` 都能稳定拿到 200。
  - 这一步没有尝试清掉任何 research blocker、本地公司行为缺失或 rollout 时间 gate；只把“控制面判断是否可信”的基础设施先修稳。
- Remaining focus for next session:
  - feature #2：resident 与 fresh 进程 blocker 结果对齐，确认当前 7 个 blocked strategy 是真实阻塞还是候选策略/公司行为检查放大出来的回归。

## Session update — 2026-03-30
- Completed feature #2: resident 与 fresh 进程的 blocker 语义现在可对齐，长生命周期服务不会继续吃旧 instrument catalog；对已经运行的非 reload resident，受控重启后四个核心 gate 与 fresh 进程完全一致。
- Code changes:
  - `InstrumentCatalogRepository` 新增 `version_token()`；`MarketDataService` 现在会在 `list_instruments()`、`fetch_option_chain()`、`_resolve_instrument()` 等 catalog 读取路径前按版本戳轻量刷新 `_catalog`，避免别的 session/进程更新 `instruments.json` 后，resident 继续沿用旧 universe。
  - `OperationsFacade.readiness()` 现在也会 deep-normalize `preflight.research_readiness`，最小嵌套快照不再把 `/ops/readiness` 压成 400，补齐 `#1` 里 typed-contract 的剩余薄弱点。
  - 新增 `test_reset_state_refreshes_readiness_and_rollout_callables()`，锁定 `reset_state()` 清缓存后 `/ops/readiness`、`/execution/gate`、`/ops/go-live` 会读取最新 data-quality / rollout getter，而不是继续吃旧绑定引用。
  - 新增 `test_market_data_service_refreshes_catalog_after_external_repo_update()`，直接覆盖“另一个进程改写 catalog 文件后，长生命周期 service 也会刷新 universe”这条 resident/fresh 一致性回归。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py::test_market_data_service_refreshes_catalog_after_external_repo_update tests/test_api.py::test_reset_state_refreshes_readiness_and_rollout_callables tests/test_api.py::test_ops_readiness_typed_contract_accepts_minimal_nested_snapshots tests/test_api.py::test_readiness_and_execution_gate_surface_execution_and_mismatch_blockers tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers tests/test_service_health.py -q` -> `7 passed`
  - `.venv/bin/python -m tradingcat.services.service_health --base-url http://127.0.0.1:8000 --timeout 5` -> `healthy=true`
  - 先对旧 resident 做结构化 diff，确认 mismatch 真因来自非 reload 常驻进程保留旧 catalog / 旧 blocker 语义；随后受控重启 `:8000`，再次对比 resident `:8000` vs fresh `:8048` 的 `/preflight/startup`、`/ops/readiness`、`/ops/go-live`、`/ops/live-acceptance` -> `SUMMARY {"mismatches": []}`
- Decisions:
  - 这一步把“代码已修好”和“常驻进程还没重启”明确区分开：对已经在跑的非 reload resident，需要一次受控重启才能吃到当前代码；重启后 resident/fresh 已经对齐。
  - 没有在这一步提前清理 7 个 blocked strategies；目前只是证明 resident/fresh 看的 blocker 集一致，下一步再进入 blocker 本体分类与 scope 收缩。
- Remaining focus for next session:
  - feature #3：逐个分类 7 个 blocked strategies，拆清哪些是研究真实阻塞，哪些是 candidate strategy / corporate-action / FX scope 被放大的回归。

## Session update — 2026-03-29
- Completed feature: 架构治理 Feature 1，修复 persistent-universe 回归，确保研究详情/报告不会被 bootstrap sample 和研究长窗口缓存污染。
- Code changes:
  - `MarketDataService.research_universe()` 现在在存在 operator/custom 标的时优先返回这些持久化标的，不再把 bootstrap sample silently 混进研究主链路。
  - `MarketDataService` 新增 `history_snapshot()`，并让 `ResearchService` 的长窗口 walk-forward 读取走非持久化快照；研究报告/详情里的只读历史加载不再回写共享短窗缓存。
  - `summarize_corporate_actions_coverage()` 改为直接抓公司行为而不复用 `sync_history()`，避免为了确认 `confirmed_none` 把长窗口 price bars 写回本地缓存。
  - `StrategyAnalysisService._benchmark_comparison()` 改为读取非持久化历史快照，避免策略详情 benchmark 计算污染后续信号生成。
  - 新增两个回归测试：一个锁定 `research_universe()` 对 custom symbol 的优先级，另一个锁定“研究报告不会把股票动量策略从 `AAPL` 污染回 `VTI` fallback”。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py -q` -> `16 passed`
  - `.venv/bin/pytest tests/test_research_reporting.py::test_research_report_does_not_pollute_short_window_stock_signals -q` -> `1 passed`
  - `.venv/bin/pytest tests/test_api.py::test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots -q` -> `1 passed`
  - 真实 HTTP 验证：
    - `curl -sS http://127.0.0.1:8022/preflight/startup` -> `healthy=true`
    - `POST /data/instruments` upsert `IVV` / `VOO` / `AAPL`
    - `GET /research/strategies/strategy_a_etf_rotation?as_of=2026-03-08` -> `signals=["IVV","VOO"]`，`signal_source="historical_momentum_rotation"`
    - `GET /research/strategies/strategy_b_equity_momentum?as_of=2026-03-08` -> `symbol="AAPL"`，`signal_source="historical_equity_momentum"`，`blackout_active=false`
  - `GET /research/strategies/strategy_c_option_overlay?as_of=2026-03-08` -> `underlying_symbol="IVV"`，`signal_source="historical_option_overlay"`
  - `POST /research/report/run?as_of=2026-03-08` -> ETF `signal_insights[0]` 返回 `symbol="IVV"`、`signal_source="historical_momentum_rotation"`、`indicator_snapshot`

## Session update — 2026-03-29
- Completed feature: 架构治理 checkpoint，继续收紧 `/diagnostics/summary` 与 `/ops/readiness` 的 typed contract，去掉 `diagnostics / alerts / compliance / preflight / research_readiness` 这些核心嵌套对象上的裸 `dict` 边界。
- Code changes:
  - `tradingcat/api/view_models.py` 新增 `PreflightCheckView`、`DiagnosticsSummaryView`、`AlertEventView`、`AlertsSummaryView`、`ComplianceCountsView`、`ComplianceChecklistSummaryView`、`ComplianceSummaryView`。
  - `StartupPreflightResponse.checks` 改为 `PreflightCheckView[]`，`OperationsReadinessResponse` 现在显式 typed 化 `diagnostics`、`preflight`、`research_readiness`、`alerts`、`compliance`，并给这些嵌套对象补了默认值，保证旧的最小 monkeypatch snapshot 仍能通过 response model 校验。
  - `tests/test_api.py` 扩展了 OpenAPI 合同断言，锁定这些嵌套对象已经发布成独立 schema；同时新增兼容测试，验证最小 readiness snapshot 仍能返回完整默认结构，不会因为缺字段直接炸掉。
- Validation:
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_preflight_and_diagnostics_publish_response_models_in_openapi tests/test_api.py::test_ops_readiness_typed_contract_accepts_minimal_nested_snapshots -q` -> `2 passed`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress -q` -> `1 passed`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_runtime_recovery.py -q` -> `6 passed`
  - `.venv/bin/python -m compileall tradingcat/api/view_models.py tests/test_api.py` -> passed
  - 真实 HTTP / contract 验证：
    - `curl -sS http://127.0.0.1:8037/preflight/startup` -> `checks` 返回 typed `name/ok/detail` 结构，且 `research_readiness.report_status="blocked"`
    - `curl -sS http://127.0.0.1:8037/diagnostics/summary` -> `diagnostics.category="manual_pending"`、`alerts.count=1`、`compliance.pending_count=1`
    - `curl -sS http://127.0.0.1:8037/ops/readiness` -> 与 `/diagnostics/summary` 一致返回 typed 嵌套对象，保留 `execution` 和 `latest_report_dir`
    - `curl -sS http://127.0.0.1:8037/broker/status` -> `backend="simulated"`、`healthy=true/false` broker detail 正常可读
- Decisions:
  - 当前机器上的真实 `preflight/startup` / `ops/readiness` 聚合仍然可能因环境检查过慢而拖住长时间验证，所以这次 HTTP contract 继续沿用临时 stub server 方式，只替换重聚合入口，保留 FastAPI route/response-model/curl 链路不变。
  - `broker_status` / `broker_validation` / `execution` 这几块暂时保持宽结构；这次先收口最容易漂移、又被前后端直接消费的嵌套对象，避免一次 session 把整个 readiness payload 全部硬编码死。

## Session update — 2026-03-29
- Completed feature: 架构治理 checkpoint，把研究实验运行状态从 `ResearchService` 中拆出到独立的 `StrategyExperimentService`，为后续 reporting / facade 继续瘦身打底。
- Code changes:
  - 新增 `tradingcat/services/strategy_experiments.py`，承接实验运行、strategy registry、历史/公司行为/FX 覆盖检查、replay fingerprint、list/compare/clear 这整组 experiment 生命周期逻辑。
  - `tradingcat/services/research.py` 现在收紧成更清晰的 application service：`run_experiment/list_experiments/compare_experiments/clear/register_strategies` 全部委托给 `experiment_service`，而 report/detail/scorecard 仍由既有 `strategy_analysis` 承接。
  - `tests/test_research_reporting.py` 新增委托测试，锁定 `ResearchService.clear()` 和 `list_experiments()` 会与底层 `experiment_service` 保持同一份状态，不会再次回流出第二套 experiment store。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/services/research.py tradingcat/services/strategy_experiments.py tests/test_research_reporting.py` -> passed
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_research_reporting.py::test_research_experiment_records_replay_fingerprint_and_compare tests/test_research_reporting.py::test_research_service_delegates_experiment_storage_to_experiment_service tests/test_research_reporting.py::test_research_report_applies_walk_forward_thresholds -q` -> `3 passed`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_research_backtest_endpoints -q` -> `1 passed`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_runtime_recovery.py -q` -> `6 passed`
  - 真实 HTTP / E2E 验证：
    - `curl -sS http://127.0.0.1:8038/broker/status` -> `backend="simulated"`、`healthy=true`
    - `POST /data/instruments` upsert `IVV/VOO/AAPL`
    - `POST /research/report/run?as_of=2026-03-08` 与 `POST /research/report/run?as_of=2026-03-09` -> 两次都返回完整研究报告，说明新 experiment service 能正常承接 report 侧实验落库
    - `GET /research/backtests` -> 返回多条 `strategy_a_etf_rotation` / `strategy_b_equity_momentum` / `strategy_c_option_overlay` 实验记录
    - `GET /research/backtests/compare?left_id=34d382ac-8056-4a9d-b53d-ab7480dadfc1&right_id=0f243b2a-eb26-4a98-b293-31be0319ce6a` -> 返回 `same_inputs=false`，并正确暴露 `as_of` 与 signal indicator snapshot 差异
- Decisions:
  - 这一步先拆 experiment 生命周期，而没有同时把 `StrategyAnalysisService` 再拆成新的 reporting 类，是为了把变更面控制在单一 feature 内，先消除 `ResearchService` 里“既管实验存储又管应用门面”的职责混杂。
  - 某些 `TestClient` / real-app 研究详情回归在这台机器上仍会偶发卡在环境链路，因此这次 E2E 验证优先选择 `/research/report/run` + `/research/backtests` + `/research/backtests/compare` 这一条更直接覆盖 experiment service 的 HTTP 主链。
- Remaining focus for next session:
  - 继续新的 architecture harness：优先把 `StrategyAnalysisService` 的 reporting/detail 组装继续抽薄，或者进一步收紧 `ResearchFacade` 对 `app.py`/runtime 的直接依赖。
- Remaining focus for next session:
  - 继续新的 architecture harness：优先考虑进一步瘦身 `ResearchFacade` / `DashboardFacade`，或者把 `StrategyAnalysisService` 再往 experiment/reporting 两层拆。
- Decisions:
  - 这次没有改 `PLAN.json`；仓库里的现有 harness plan 是上一轮 48 个 feature 的已完成状态，且该文件按规则不能重写描述。本轮新架构治理任务只在 `PROGRESS.md` 追加 checkpoint，避免污染旧 plan。
  - 根因不是单纯 universe 过滤，而是“研究只读路径回写共享缓存”导致短窗信号被长窗样本污染；因此这一步优先切断读写耦合，而不是继续在策略层补更多 fallback 特判。
  - 真实 HTTP 当前验证到的是 `available` 正常路径；“FX 缺失时必须阻塞”的强语义由新增 service/research/API 测试锁定，避免依赖运行时临时制造空 FX。
- Remaining focus for next session:
  - feature #22：为主 universe 提供最小可复现的历史回填基线，降低长期依赖样例数据的概率。

## Session update — 2026-03-29
- Completed feature #22: 主 universe 现在有了最小可复现的历史回填基线，降低了长期依赖样例数据的概率。
- Code changes:
  - `TradingCatApplication.sync_market_history()` 现在在未指定 `symbols` 时会自动回填研究主 baseline，而不是盲目走全 catalog；当前 baseline 会按研究优先级选出 `SPY/0700/QQQ/300308/510300` 这一组核心标的。
  - 同一入口会把基线所需 FX 一并同步，并在响应里返回 `baseline_applied`、`baseline_symbols` 和 `fx_sync`，这样“初始化或同步后”就能直接得到最小研究基线。
  - 新增 app/API 测试锁定：空历史目录下跑一次 `/data/history/sync` 后，ETF 轮动研究会走 `historical` 而不是 synthetic fallback。
- Validation:
  - `.venv/bin/pytest tests/test_selection_service.py tests/test_api.py -q` -> `30 passed`
  - `curl -sS http://127.0.0.1:8021/preflight/startup` -> `healthy=true`
  - 在临时空数据目录上运行 `POST /data/history/sync` with `{"end":"2026-03-08"}` -> 返回 `baseline_applied=true`、`baseline_symbols=["SPY","0700","QQQ","300308","510300"]`、`fx_sync.rate_count=198`
  - 同一临时环境下 `GET /research/strategies/strategy_a_etf_rotation?as_of=2026-03-08` -> 返回 `data_source="historical"`、`data_ready=true`
- Decisions:
  - 这一步复用了现有 `/data/history/sync` 作为 baseline 入口，没有再额外发明一个新 bootstrap endpoint，减少了运维入口分叉。

## Session update — 2026-03-29
- Completed feature: 架构治理 Feature 2，把 `TradingCatApplication` 的策略访问改成 runtime 内稳定 registry，不再每次查询都临时 new 一批策略实例。
- Code changes:
  - `ApplicationRuntime` 现在在初始化时一次性构建 `strategy_registry`，并把这批稳定策略实例注册到 `ResearchService`；runtime recover 时会整体重建这份 registry。
  - `TradingCatApplication.research_strategies`、`strategy_by_id()`、`active_execution_strategies()`、`strategy_signal_map()` 现在都复用 runtime registry，不再通过 property 每次 new 新策略对象。
  - 新增 runtime recovery 测试，锁定“同一 runtime 内同一个 strategy_id 返回同一对象；recover 后才会换成新实例”。
- Validation:
  - `.venv/bin/pytest tests/test_runtime_recovery.py -q` -> `4 passed`
  - `.venv/bin/pytest tests/test_research_reporting.py::test_research_report_does_not_pollute_short_window_stock_signals -q` -> `1 passed`
  - `TRADINGCAT_DATA_DIR=$(mktemp -d) TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots -q` -> `1 passed`
- Decisions:
  - 这一步只做“稳定 registry”，没有顺手把 `StrategyRegistry` / `StrategySignalProvider` 单独抽成新 service，避免在一个 session 里同时跨 Feature 2 和 Feature 3。
  - 验证时对 API 定点用例显式用了隔离 `TRADINGCAT_DATA_DIR`，因为默认 data/runtime 路径在并发测试下会互相踩状态；先保证 feature 语义稳定，再把更系统化的测试隔离策略留给后续 session。

## Session update — 2026-03-29
- Completed feature: 架构治理 Feature 3，正式抽出 `StrategyRegistry / StrategySignalProvider`，把策略 lookup 和 signal-map 生成从 `app.py` 中移走。
- Code changes:
  - 新增 [tradingcat/services/strategy_registry.py](/Users/miau/Documents/TradingCat/tradingcat/services/strategy_registry.py)，提供 `StrategyRegistry` 和 `StrategySignalProvider` 两个 runtime 协作对象。
  - `ApplicationRuntime` 现在持有 `strategy_registry` 和 `strategy_signal_provider`；构建 runtime 时会一次性装配这两个对象并注册到 `ResearchService`。
  - `TradingCatApplication` 的 `strategy_by_id()`、`active_execution_strategies()`、`get_signals()`、`_strategy_signal_map()` 现在都只做 delegation，不再自己维护 lookup/filter/generate 逻辑。
  - 新增 runtime 测试，锁定 signal provider 会复用 registry 中的稳定策略实例。
- Validation:
  - `.venv/bin/pytest tests/test_runtime_recovery.py -q` -> `5 passed`
  - `.venv/bin/pytest tests/test_research_reporting.py::test_research_report_does_not_pollute_short_window_stock_signals -q` -> `1 passed`
  - `TRADINGCAT_DATA_DIR=$(mktemp -d) TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots -q` -> `1 passed`
- Decisions:
  - 这一步只抽 runtime registry/provider，不继续把 facade 和 route 一起改薄，避免把 Feature 3 和后续 facade/query-service feature 混在同一个 session。
  - `scheduler_runtime.py` 和 facade 侧暂时继续通过 `app.research_strategies` / `app.strategy_signal_map()` 访问策略，但这些入口现在已经是对 registry/provider 的薄代理，后续再进一步削掉 `app.py` 的编排重量。
  - baseline 目前按“研究优先级最高的 5 个 symbol”固定下来，先解决个人交易主链路的最小可复现性，而不是一次把全 universe 都做厚。
- Remaining focus for next session:
  - feature #23：把 smart order 的 RSI 条件改成真实指标计算，而不是 mock 常量。

## Session update — 2026-03-29
- Completed feature #23: smart order 的 RSI 条件现在使用真实价格序列计算，而不是 mock 常量。
- Code changes:
  - `RuleEngine._metric_value()` 里的 `RSI_*` 分支现在会按最近历史 bars 计算真实 RSI 值，并支持从指标名里解析周期参数，例如 `RSI_14`。
  - 当 smart order 条件未满足时，rule engine 会记录带有 `metric / value / target / operator` 的日志，至少能从日志里看到真实 RSI 值而不是黑箱常量。
  - 新增 `tests/test_rule_engine.py`，分别锁定上涨序列下 RSI 高位触发、下跌序列下 RSI 低位不触发且日志暴露真实值；API 测试也锁定 `/ops/evaluate-triggers` 使用的 RSI 不是旧的 `30.0` 常量。
- Validation:
  - `.venv/bin/pytest tests/test_rule_engine.py tests/test_api.py -q` -> `26 passed`
  - `.venv/bin/pytest tests/test_rule_engine.py -q` -> `2 passed`
- Decisions:
  - 这一步只替换 RSI 指标，不顺手把 SMA 和完整 trigger diagnostics 一起做掉，避免把 `#24-#26` 的范围提前揉进来。
  - 没有做真实 HTTP 的 `/ops/evaluate-triggers` 触发演练，因为那会进入订单提交路径；当前按仓库 side-effect 边界，用 API/engine 测试完成完整验证。
- Remaining focus for next session:
  - feature #24：把 smart order 的 SMA 条件改成真实指标计算，而不是 `price * 0.95`。

## Session update — 2026-03-29
- Completed feature #24: smart order 的 SMA 条件现在使用真实均线计算，而不是 `price * 0.95`。
- Code changes:
  - `RuleEngine._metric_value()` 里的 `SMA_*` 分支现在会按最近历史 bars 计算真实简单均线，并支持从指标名里解析周期参数，例如 `SMA_10`。

## Session update — 2026-03-29
- Completed features #3-#10: 持久化 universe、基础流动性过滤、市场驱动策略信号与指标快照现在已经接上同一条研究主链路，并顺手清掉了这轮 harness 造成的两处测试/数据边界腐化。
- Code changes:
  - `MarketDataService` 现在支持持久化 instrument catalog 的 upsert/list/filter/research-universe，并在 `ensure_history()` 里自动把明显过稀的月度残片升级成窗口所需的密历史，避免 baseline sync 之后策略又被旧缓存拖回 fallback。
  - `EtfRotationStrategy`、`EquityMomentumStrategy`、`OptionHedgeStrategy` 现在都能消费持久化 universe 和真实历史窗口；股票动量的流动性排序改成同一量纲，避免把 `avg_daily_dollar_volume_m` 和 20 日美元成交额混着比较。
  - `TradingCatApplication.research_strategies` 统一注入 runtime market-data；`/data/instruments`、研究 detail/report 和 README universe runbook 也已经接上新字段与维护入口。
  - 测试侧把这轮 harness 引入的“全局 app_state 串味”单独收掉了：`tests/support.py` 的 `reset_runtime_state()` 现在直接走 `app_state.reset_state()`，不再只清 execution/audit 造成后续 API 测试误读旧 catalog/history。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py tests/test_research_reporting.py tests/test_selection_service.py -q` -> `44 passed`
  - `.venv/bin/pytest tests/test_api.py::test_data_instruments_endpoint_persists_and_filters_universe_entries tests/test_api.py::test_data_history_sync_without_symbols_bootstraps_research_baseline tests/test_api.py::test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots -q` -> `3 passed`
  - `.venv/bin/pytest tests/test_backtest.py -q` -> `7 passed`
  - 隔离 HTTP `8036` 上验证：
    - `POST /data/instruments` 后默认 universe 里保留 `IVV/VOO/AAPL`，不会把被禁用的 `SPY/QQQ/0700` 当成默认研究候选。
    - `GET /research/strategies/strategy_a_etf_rotation?as_of=2026-03-08` 返回 `data_source="historical"`，信号来自 `IVV/VOO/VTI`，且 `signal_source="historical_momentum_rotation"`。
    - `GET /research/strategies/strategy_b_equity_momentum?as_of=2026-03-08` 返回 `data_source="historical"`，主信号为 `AAPL`，`signal_source="historical_equity_momentum"`。
    - `POST /research/report/run?as_of=2026-03-08` 中 ETF / 股票策略的 `data_source` 与 `signal_insights.signal_source` 已经对齐到历史链路。
    - `POST /data/history/sync` 返回 `baseline_applied=true`，并给出新的 `baseline_symbols` 与 `fx_sync.rate_count`。
- Decisions:
  - 没有给 `/data/instruments` 增加“隐式替换默认 universe”的魔法语义，仍然保持显式 upsert；这比在 route 层偷偷清 catalog 更稳，也更不容易继续腐化边界。
  - 期权覆盖策略在真实 HTTP 下已经返回 `historical_option_overlay` 的底层信号和 `IVV` 底仓，但研究报告顶层 `data_source` 仍保留 `synthetic` blocker，因为当前没有真实期权历史回放数据；这一步先不伪装成 fully historical。
- Remaining focus for next session:
  - feature #43：把 diagnostics summary 和研究 blocker 对齐，让 synthetic / history incomplete 直接出现在 `/diagnostics/summary`。

## Session update — 2026-03-29
- Completed features #37-#42: acceptance / rollout / go-live / report archive 现在会把连续 clean day/week 证据与 blocker 链路串完整，周报和归档都能直接消费这些状态。
- Code changes:
  - `OperationsJournalService` 现在会在 acceptance summary / timeline / rollout summary 中暴露 `current_clean_day_streak`、`current_clean_week_streak`、`blocked_days` 和 `next_requirement`，rollout blocker 也会直接消费 incident-day 与 clean-week gate。
  - `TradingCatApplication.go_live_summary()` 与 `live_acceptance_summary()` 现在会汇总 gate reason、rollout blocker 和 acceptance evidence，明确给出统一 blocker 列表、next actions 与 `acceptance_evidence`。
  - `build_operations_period_report()` 现在会输出 `acceptance_window`、周报 highlight 和 blocker-derived next actions；`load_report_summary()` 兼容 validate archive 写出的 unwrapped diagnostics payload，不再让 `/reports/latest` 因 `summary` 包装差异炸掉。
  - 归档脚本 `validate_broker.sh`、`latest_report.sh`、`report_markdown.sh` 现在都会写入/读取 `ops_acceptance` 快照；dashboard report summary 也开始消费 acceptance ready weeks、blocked days 和 clean-week streak。
- Validation:
  - `.venv/bin/pytest tests/test_operations_journal.py tests/test_reports_helper.py tests/test_api.py tests/test_dashboard_facade.py -q` -> `58 passed`
  - 隔离 HTTP `8033`:
    - `GET /ops/weekly-report` -> `acceptance_window.clean_day_count=6`、`incident_day_count=1`，highlight 含 `Acceptance evidence`
    - `GET /ops/acceptance/timeline?window_days=21` -> 返回逐日 `clean_day_streak / clean_week_streak` 和 `next_requirement.explanation`
    - `GET /ops/rollout` -> 返回 evidence counts，blockers 含 `incident day` 与 `Need 4 more clean week(s)`
    - `GET /ops/live-acceptance` / `GET /ops/go-live` -> 返回 `acceptance_evidence`、统一 blockers 和 `Resolve rollout blocker` next actions
  - 隔离 HTTP `8035` + `TRADINGCAT_ARCHIVE_REPORTS=true bash scripts/validate_broker.sh http://127.0.0.1:8035`:
    - `GET /reports/latest` -> 返回 `ops_acceptance`、`selection_summary`、`allocation_summary`、`ops_go_live`、`ops_live_acceptance`
    - `GET /reports/latest/dashboard` -> `cards.operations.acceptance_ready_weeks=2`、`cards.rollout.current_clean_week_streak=0`、`cards.live_acceptance.current_clean_week_streak=0`
- Decisions:
  - 没有把 acceptance / rollout 计算塞进 route；所有新逻辑继续留在 `services/operations.py`、`services/reporting.py` 和 `app.py` 编排层，避免再加新的 route-level orchestration。
  - archive 验证过程中顺手修掉了一个真实兼容性 bug：`validate_broker.sh` 写出的 diagnostics JSON 不是所有场景都会包 `summary`，所以 report loader 改成兼容 wrapped / unwrapped 两种格式。
- Remaining focus for next session:
  - features #3-#10：补齐持久化 universe、真实研究 signal 链路、策略指标快照和 sample-only 主链路移除。
  - 当 SMA 条件未满足时，rule engine 同样会记录带有 `metric / value / target / operator` 的日志，能直接看到真实均线值。
  - `tests/test_rule_engine.py` 新增上涨/下跌序列下的 SMA 触发与日志断言，API 测试也锁定 `/ops/evaluate-triggers` 使用的 SMA 不是旧的 `95.0` 假值。
- Validation:
  - `.venv/bin/pytest tests/test_rule_engine.py tests/test_api.py -q` -> `29 passed`
- Decisions:
  - 这一步延续了 `#23` 的实现框架，只替换 SMA 指标，不提前把 trigger diagnostics / rejection reasons 的完整输出格式一起改掉。
  - 没有做真实 HTTP 的 `/ops/evaluate-triggers` 触发演练，原因与 `#23` 相同：避免在没有显式指令的情况下进入订单提交 side-effect 路径。
- Remaining focus for next session:
  - feature #25：trigger 评估记录指标快照与执行上下文，便于复盘为什么触发或未触发。

## Session update — 2026-03-29
- Completed feature #25: trigger 评估现在会记录指标快照与执行上下文，便于复盘为什么触发或未触发。
- Code changes:
  - `SmartOrder` 现在持久化 `last_evaluated_at` 与 `evaluation_summary`，每次评估都会记录每个条件的 `metric / operator / target / value / passed`。
  - `OrderIntent` 新增 `metadata`，rule engine 在触发时会把同一份 `trigger_context` 带进 execution intent；`ExecutionService` 的 intent metadata 也会保留这份上下文。
  - rule-engine 与 API 测试现在都会校验 `/orders/triggers` 能看到 evaluation snapshot，且 execution intent context 里也带有来自 trigger 的条件快照。
- Validation:
  - `.venv/bin/pytest tests/test_rule_engine.py tests/test_execution_reconciliation.py tests/test_api.py -q` -> `32 passed`
- Decisions:
  - 这一步先把 trigger 快照落到持久化模型和 execution context，本身还不强求 route 层输出“未触发原因”的专门格式，给 `#26` 留出清晰边界。
  - 没有做真实 HTTP trigger 执行演练，继续遵守当前无显式 side-effect 授权的边界；完整链路由 API/engine 测试覆盖。
- Remaining focus for next session:
  - feature #26：trigger 评估接口/结果显式给出未触发原因，避免个人交易者靠猜测排错。

## Session update — 2026-03-29
- Completed feature #26: trigger 评估接口/结果现在会显式给出未触发原因，避免个人交易者靠猜测排错。
- Code changes:
  - `RuleEngine.evaluate_all()` 现在会返回 `results`，包含每个 smart order 的条件结果和 `reasons` 列表。
  - 条件级结果新增 `reason_type / reason / data_ready / source`，目前会区分 `price_not_reached`、`indicator_not_met`、`data_missing`，从而把“价格没到”“指标不满足”“数据不够”拆开。
  - rule-engine 与 API 测试现在锁定：`/ops/evaluate-triggers` 对未触发的 smart order 会返回显式原因；指标历史缺失时会明确标成 `data_missing`。
- Validation:
  - `.venv/bin/pytest tests/test_rule_engine.py tests/test_api.py -q` -> `32 passed`
- Decisions:
  - 这一步把未触发原因直接放进 `/ops/evaluate-triggers` 返回值本身，而不是只依赖 `/orders/triggers` 里的快照字段，优先解决“评估完立刻知道为什么没触发”的体验。
  - 仍然没有做真实 HTTP trigger 执行演练，继续遵守当前无显式 side-effect 授权的边界；原因分类和结果结构由 API/engine 测试完成闭环验证。
- Remaining focus for next session:
  - feature #27：执行记录持久化 expected price、realized price 与参考来源，支持个人可用的成交偏差追踪。

## Session update — 2026-03-29
- Completed feature #27: 执行记录现在会持久化 expected price、realized price 与参考来源，支持个人可用的成交偏差追踪。
- Code changes:
  - `ExecutionService.register_expected_prices()` 现在会保存参考价来源，并支持直接接收 `{price, source}` 结构；同时新增 `resolve_price_context()`，统一返回 `expected_price`、`realized_price`、`reference_source` 与已记录 slippage。
  - `/orders` 与 dashboard recent orders 现在都会带上订单上下文和价格上下文，所以查询订单时就能直接看到预期价、成交价以及参考价来自 `trigger_quote`、`execution_preview_quote` 还是 `manual_order_reference`。
  - `ReconciliationService.execution_quality_summary()` 样本明细现在也会携带 `reference_source`；execution/API 测试新增了“价格上下文持久化”和“orders endpoint 暴露 expected vs realized”断言。
- Validation:
  - `bash ~/.codex/scripts/global-init.sh` -> 先暴露出 `tests/test_api.py` 的语法错误；已在本 feature 收口时修复并重新通过验证。
  - `.venv/bin/pytest tests/test_execution_reconciliation.py tests/test_api.py -q` -> `32 passed`
- Decisions:
  - 这一步优先把价格上下文统一落在 execution/reconciliation/order-query 共享模型上，而不是只在单一报表接口里临时拼字段，给后续 `#28/#29` 的 execution quality 和 TCA 继续复用。
  - 没有做真实 HTTP 的 `/reconcile/manual-fill` 演练，因为仓库规则把该接口列为需要显式批准的 side-effect 路径；本次改用 API pytest 完成完整链路验证，并在这里显式记录这个边界。
- Remaining focus for next session:
  - feature #28：execution quality 按资产类别给出偏差等级与样本数，帮助个人识别实现拖累。

## Session update — 2026-03-29
- Completed feature #28: execution quality 现在会按资产类别给出偏差等级与样本数，帮助个人识别实现拖累。
- Code changes:
  - `ReconciliationService.execution_quality_summary()` 现在会额外返回 `stock_samples`、`etf_samples`、对应 breach 计数以及 `asset_class_summary`，把股票、ETF、期权拆开看，而不是只剩 equity/option 两团粗粒度统计。
  - `asset_class_summary` 里每个资产类别都会暴露 `sample_count`、`breach_count`、`breach_ratio`、`metric_name`、`threshold`、`average_metric`、`max_metric`、`severity` 和 `message`；当没有成交样本时，会明确标成 `insufficient_data` 而不是给一堆空洞零值。
  - execution/API 测试新增了资产类别分层断言，锁定“小样本 breach 先 warning、无样本返回 insufficient_data”这两条个人交易者更可用的语义。
- Validation:
  - `.venv/bin/pytest tests/test_execution_reconciliation.py tests/test_api.py -q` -> `34 passed`
  - 在临时只读实例上运行 `curl -sS http://127.0.0.1:8022/execution/quality` -> 返回 `asset_class_summary.stock/etf/option`，且空样本场景明确给出 `severity="insufficient_data"` 与对应 message
- Decisions:
  - 这一步只把 `/execution/quality` 做成按资产类别可读的质量摘要，不提前把完整 TCA 样本拆解塞进来，避免和 `#29` 范围重叠。
  - 偏差等级规则收敛为“小样本 breach 先 warning、样本够多且多数 breach 再 error”，避免单笔噪声把个人交易者误导成系统性故障。
- Remaining focus for next session:
  - feature #29：ops TCA 输出样本拆解，至少覆盖预期价、成交价、偏差、方向与样本量。

## Session update — 2026-03-29
- Completed feature #29: `/ops/tca` 现在会输出样本拆解，覆盖预期价、成交价、偏差、方向与样本量。
- Code changes:
  - `ExecutionService` / `ReconciliationService` 现在会把 `side` 与 `filled_quantity` 一并带进成交质量样本，并新增 `transaction_cost_summary()`，输出 `sample_count`、`filled_quantity`、`direction_summary`、`asset_class_summary` 和逐笔 `samples`。
  - `/ops/tca` 路由现在保留原有 audit 聚合字段，同时叠加真正的 TCA 样本明细，因此既不会丢掉旧的运行统计，也能直接复盘每笔执行的 `expected_price`、`realized_price`、`deviation_metric`、`direction`。
  - execution/API 测试新增了 buy/sell 双方向样本断言，锁定 `/ops/tca` 可以区分方向并返回逐笔样本拆解。
- Validation:
  - `.venv/bin/pytest tests/test_execution_reconciliation.py tests/test_api.py -q` -> `36 passed`
  - 在临时 seeded 数据目录上运行 `curl -sS http://127.0.0.1:8023/ops/tca` -> 返回 `sample_count=2`、`direction_summary.buy/sell.sample_count=1`，并包含逐笔 `expected_price`、`realized_price`、`deviation_metric`、`direction`
- Decisions:
  - 这一步让 `/ops/tca` 兼容保留旧的 audit 统计字段，避免现有消费方直接断掉；新增的 sample breakdown 则从 execution 实际状态生成，而不是继续堆在 audit log 上做猜测。
  - 样本聚合先按方向输出 `average_slippage_bps` / `average_premium_deviation`，让股票/ETF 与期权的量纲不被强行揉成一个数字；更高层的“主要拖累摘要”留给 `#30`。
- Remaining focus for next session:
  - feature #30：日报/周报/运营摘要高亮主要成交拖累与主要异常来源，支持快速复盘。

## Session update — 2026-03-29
- Completed feature #30: 日报/周报/运营摘要现在会高亮主要成交拖累与主要异常来源，支持快速复盘。
- Code changes:
  - `operations_execution_metrics()` 现在把 `execution_tca` 带进运营指标；`build_operations_period_report()` 会从窗口内 TCA 样本里提炼 `top_execution_drags`，并从 alerts / execution errors / risk violations / recoveries 聚合 `top_anomaly_sources`。
  - daily/weekly report 的 `highlights` 现在会直接写出 “Top execution drag” 和 “Top anomaly source”；同时新增 `metrics.tca_sample_count`，便于一眼看出这些摘要基于多少成交样本。
  - dashboard summary 继续内嵌 daily/weekly report，因此 `/dashboard/summary` 现在也能直接读到这些拖累/异常摘要；reporting helper 也新增了 dashboard card 对应字段，给归档 dashboard 预留了消费位。
- Validation:
  - `.venv/bin/pytest tests/test_reports_helper.py tests/test_api.py tests/test_execution_reconciliation.py -q` -> `47 passed`
  - 在临时 seeded 数据目录上运行 `curl -sS http://127.0.0.1:8024/ops/daily-report` -> 返回 `highlights` 中的 `Top execution drag: SPY buy 25.0 slippage_bps.` 与 `Top anomaly source: alert:trade_channel_failed (1).`，同时包含 `top_execution_drags` 与 `top_anomaly_sources`
- Decisions:
  - 这一步把 period report 的拖累/异常摘要建立在现有 execution TCA 和 alerts/audit/recovery 之上，没有额外发明一套新的事件存储，先把“快速复盘”的主链路打通。
  - `reports/latest/dashboard` 侧先补了消费位，不强行要求归档 summary 立刻拥有完整 period payload；当前用户可直接从 `/dashboard/summary` 读到 daily/weekly 的新摘要。
- Remaining focus for next session:
  - feature #31：authorization summary 关联 approval request、manual fill external source 与最终授权模式。

## Session update — 2026-03-29
- Architecture remediation checkpoint: 单独收口本轮 harness 加重的架构腐化，再继续 `PLAN.json` 主线。
- Scope:
  - 只处理本轮 harness 明显推软的边界：`app.py` 中的运营汇总编排、`reporting.py` 中新增的 TCA/异常分析逻辑，以及新增 API 测试里重复扩散的内部状态操作。
  - 不回滚已交付 feature，不改动 `PLAN.json` 通过状态，只做等价重构和边界保护。
- Code changes:
  - 新增 `tradingcat/services/operations_analytics.py`，把 execution metrics 组装、TCA summary 合并、period insights（`top_execution_drags` / `top_anomaly_sources`）从 `app.py` / `reporting.py` 抽离出去。
  - `routes/ops.py` 的 `/ops/tca` 不再直接内联合并 audit 与 execution summary，改走 `OperationsFacade.tca()`；`reporting.py` 现在只消费 `period_insights`，不再自己持有最近这轮新增的分析实现。
  - 新增 `tests/support.py`，把本轮新增 API 测试里反复出现的 execution seed / alert seed / reset 操作收进 helper；同时补了 `tests/test_architecture_boundaries.py`，防止 route 层再次直接内联 `audit.execution_metrics_summary()` 和 `execution.transaction_cost_summary()`。
- Validation:
  - `.venv/bin/pytest tests/test_api.py tests/test_reports_helper.py tests/test_architecture_boundaries.py tests/test_execution_reconciliation.py -q` -> `49 passed`
  - `.venv/bin/pytest tests/test_dashboard_facade.py tests/test_audit.py -q` -> `3 passed`
  - 临时只读实例验证：
    - `GET /ops/tca` -> `200`, 返回 TCA summary
    - `GET /ops/daily-report` -> `200`, 返回 daily report
    - `GET /dashboard/summary` -> `200`, dashboard summary 正常返回
- Decisions:
  - 这次只清理“本轮 harness 继续推软”的边界，没有趁机大范围重构 `TradingCatApplication` 全体积，避免把架构修复变成另一轮失控改造。
  - 后续继续 harness feature 时，默认先判断改动应落在现有 service/facade/builder 哪一层；如果只能继续把逻辑堆回 `app.py` 或 route，就先停下来重分层再实现。

## Session update — 2026-03-29
- Completed feature #31: authorization summary 现在会关联 approval request、manual fill external source 与最终授权模式。
- Code changes:
  - `ManualFill` 新增 `external_source` 字段；`ExecutionService` 现在会在手工成交回填时合并授权状态，保留初始 `authorization_mode`，同时新增 `final_authorization_mode` 和 `external_source`，从而区分“原本待审批”与“最终以外部回填完成”。
  - `authorization_summary()` 现在会返回 `final_authorization_mode`、`external_source`，并在已有审批请求的外部回填场景下保留 `approval_request_id`，不再把授权链路截断成一段模糊状态。
  - 这一步的逻辑继续落在 `ExecutionService` 内部，没有把授权状态拼装推回 route 或 `app.py`，符合刚做完的架构修复边界。
- Validation:
  - `.venv/bin/pytest tests/test_execution_reconciliation.py tests/test_api.py -q` -> `39 passed`
  - 在临时预置授权状态的数据目录上运行 `curl -sS http://127.0.0.1:8026/execution/authorization` -> 返回 `authorization_mode="manual_pending"`、`final_authorization_mode="manual_fill_external"`、`approval_request_id=<id>`、`approval_status="external_fill"`、`external_source="broker_statement"`
- Decisions:
  - `authorization_mode` 保留“最初怎么过授权”的语义，`final_authorization_mode` 表示最终落地路径，避免一个字段同时承载“初始模式”和“终态”而再次变糊。
  - 对已存在审批请求的外部回填场景，保留原 `approval_request_id`，这样后续审计/复盘还能把审批链和成交链重新串起来。
- Remaining focus for next session:
  - feature #32：reconciliation 输出关联订单、成交、组合快照影响，形成可追责闭环。

## Session update — 2026-03-29
- Completed feature #32: reconciliation 现在会返回订单上下文、价格上下文、授权上下文以及组合前后快照影响，形成可追责闭环。
- Code changes:
  - `TradingCatApplication.reconcile_execution_cycle()` 现在统一处理 live reconcile 的组合应用与 trace 收集，`/execution/reconcile` route 不再自己循环订单并直接操作组合状态；`reconcile_manual_fill()` / import 路径也会返回同一结构的 `reconciliation` / `reconciliations`。
  - `ExecutionService` 新增 `resolve_authorization_context()` 和 `build_reconciliation_trace()`；trace 里会带上 `authorization_mode`、`final_authorization_mode`、`approval_request_id`、`external_source`，同时把 `expected_price` / `realized_price` 和 order intent metadata 一起串起来。
  - `ReconciliationService` 现在负责 reconciliation trace 的 payload 组装与组合快照摘要；这一步特意把新 trace builder 放回 execution/reconciliation 服务侧，而不是继续把序列化逻辑堆进 `app.py`，避免刚修复的架构边界再次变软。
  - API 测试新增手工回填与 live reconcile 的 trace 断言，架构边界测试新增对 route 层 `apply_fill_to_portfolio(` 的禁止，防止对账编排重新泄漏回接口层。
- Validation:
  - `.venv/bin/pytest tests/test_api.py tests/test_execution_reconciliation.py tests/test_architecture_boundaries.py -q` -> `43 passed`
  - 隔离 HTTP 验证：
    - `GET /preflight/startup` on `http://127.0.0.1:8027` -> `healthy=true`, `data_dir=/tmp/tradingcat-reconcile-rsS1nT`
    - `POST /execution/reconcile` on `http://127.0.0.1:8027` -> 返回 `reconciliations[0].pricing.expected_price=100.0`、`realized_price=100.2`、`authorization.authorization_mode="risk_approved"`、`portfolio_effect.cash_delta=-200.4`、`portfolio_after.position_count=1`
  - 手工回填 trace 继续通过 API pytest 覆盖；没有对真实 `/reconcile/manual-fill` 做 HTTP 演练，因为仓库规则把该接口列为需要显式批准的 side-effect 路径。
- Decisions:
  - 这一步没有让 route 直接操作 portfolio，也没有把 trace 组装继续塞进 `TradingCatApplication`；应用层只负责前后快照与调用协调，具体 trace payload 留在 execution/reconciliation 服务。
  - live reconcile 的真实 HTTP 验证使用了临时数据目录和预置 broker fill，确保是完整 FastAPI 链路，同时不污染主数据目录，也不引入真实交易副作用。
- Remaining focus for next session:
  - feature #33：审计日志记录每笔订单的授权上下文、对账来源与关键状态迁移。

## Session update — 2026-03-29
- Completed feature #33: 审计日志现在会记录每笔订单的授权上下文、对账来源与关键状态迁移，并且可按 `order_intent_id` 直接查询。
- Code changes:
  - `AuditService` 新增 `build_order_details()`、`list_events(..., order_intent_id=...)` 和 `order_activity_summary()`；`/audit/summary` 现在会返回 `tracked_order_count`、`order_transition_count` 和最近订单链路摘要，里面会带 `authorization_mode`、`final_authorization_mode`、`approval_request_id`、`approval_status`、`external_source`、`reconciliation_sources` 与 `status_transitions`。
  - `submit_manual_order()`、approval routes、`reconcile_manual_fill()`、`reconcile_execution_cycle()` 现在都会把统一的 order-audit details 写入审计，不再各自散落不同字段名；live/manual reconcile 事件会一起带上价格上下文和组合影响摘要。
  - 审计查询逻辑继续落在 `AuditService`，route 只负责透传 query 参数，没有把订单汇总逻辑塞回接口层，保持了这轮架构修复后的边界。
- Validation:
  - `.venv/bin/pytest tests/test_audit.py tests/test_api.py tests/test_execution_reconciliation.py tests/test_architecture_boundaries.py -q` -> `47 passed`
  - 隔离 HTTP 验证：
    - 在 `http://127.0.0.1:8028` 的临时实例上执行 `POST /execution/reconcile` -> 审计写入 `live_reconcile` 事件，包含 `authorization_mode="risk_approved"`、`previous_order_status="submitted"`、`order_status="filled"`
    - `GET /audit/logs?limit=100&order_intent_id=http-audit-order` -> 返回该订单的审计事件，含 `reconciliation_source="live_reconcile"`
    - `GET /audit/summary` -> 返回 `tracked_order_count=1`、`order_transition_count=1`，并在 `orders[0]` 中汇总该订单的授权与状态迁移链
- Decisions:
  - 审计侧这一步优先保证“按订单可追链”，所以把 order-level 聚合放进 `AuditService` 而不是额外新建 route-only payload builder，避免接口层再次长胖。
  - 手工审批路径在现有状态机下不会把订单显式推进到 `submitted`，因此测试断言按真实状态链路锁定“待审批 -> 成交”或“submitted -> filled”的现状，而没有强行伪造一个更理想化但不真实的状态。
- Remaining focus for next session:
  - feature #34：手工成交回填后组合快照必须一致更新，并可通过接口直接验证影响结果。

## Session update — 2026-03-29
- Completed feature #34: 手工成交回填后，订单、组合和审计三处状态现在都有明确的一致性回归覆盖，并可通过现有接口直接验证结果。
- Code changes:
  - 没有新增新的生产接口层；这一步刻意复用已有 `/portfolio`、`/orders`、`/audit/logs` 和 `reconcile_manual_fill()` 返回值，把“manual fill 后三处状态一致”补成明确测试与持久化保证，避免为了验证再引入新的 payload builder。
  - API 测试新增了 manual fill 一致性断言：回填后立即查询 `/portfolio`、`/orders`、`/audit/logs`，要求现金/持仓、订单成交状态、审计里的 `reconciliation_source` 和 `portfolio_effect` 同时对齐。
  - 持久化测试不再手动拆开 `execution.reconcile_manual_fill() + _apply_fill_to_portfolio()`，改成走 `TradingCatApplication.reconcile_manual_fill()` 完整路径，锁定应用层真实行为。
- Validation:
  - `.venv/bin/pytest tests/test_api.py tests/test_persistence.py tests/test_execution_reconciliation.py -q` -> `46 passed`
  - 隔离 HTTP 验证：
    - 在 `http://127.0.0.1:8029` 的临时实例里预置一笔 manual fill 后，`GET /portfolio` -> `cash=999797.0` 且持有 `SPY x 2`
    - `GET /orders` -> 同一 `order_intent_id` 返回 `status="filled"`、`realized_price=101.5`、`broker_order_id="http-manual-fill"`
    - `GET /audit/logs` -> 同一订单的 `manual_fill` 审计事件包含 `reconciliation_source="broker_statement"` 与 `portfolio_effect.cash_delta=-203.0`
- Decisions:
  - 这一步选择“加强一致性验证”而不是再造一个 manual fill summary endpoint，因为现有接口已经足够表达结果，新增接口只会把验证逻辑扩散到更多边界。
  - 真实 HTTP 验证依旧使用临时数据目录和预置状态，不直接调用需要显式批准的 `/reconcile/manual-fill` 路由，继续遵守仓库 side-effect 边界。
- Remaining focus for next session:
  - feature #35：订单状态、对账状态与 broker/portfolio mismatch 进入 readiness/blocker，避免带病运行。

## Session update — 2026-03-29
- Completed feature #35: 订单状态、对账状态与 broker/portfolio mismatch 现在会进入 readiness/gate blocker，避免带病运行。
- Code changes:
  - `OperationsAnalyticsService` 新增 `execution_readiness()`，统一把 `pending_approval`、待对账订单、未清洁授权状态，以及 `cash_mismatch / position_mismatch / unmatched_broker_orders / duplicate_fills_detected` 这类关键执行告警折叠成可读 blocker。
  - `operations_readiness()` 和 `execution_gate_summary()` 现在共用这份执行健康摘要，并把它直接暴露到响应里的 `execution` 字段；这样 `/ops/readiness` 和 `/execution/gate` 不再只是“红灯”，而会明确说出为什么挡住。
  - 这一步沿用了上一轮架构修复的原则，没有在 route 或 facade 里各自拼 blocker 文案，而是继续把共享判断放在 service 层复用。
- Validation:
  - `.venv/bin/pytest tests/test_api.py tests/test_dashboard_facade.py tests/test_reports_helper.py -q` -> `48 passed`
  - 隔离 HTTP blocked 场景：
    - 在 `http://127.0.0.1:8030` 的临时实例里预置 `pending approval` 订单和 `cash_mismatch` 告警后，`GET /ops/readiness` -> `ready=false`，`blockers` 包含 `1 order(s) remain pending approval.` 和 `Broker cash differs from local snapshot by 500.00.`
    - 同一实例上 `GET /execution/gate` -> `should_block=true`，`reasons` 同样包含上述两条 blocker
  - 隔离 HTTP clean 场景：
    - 在 `http://127.0.0.1:8031` 的干净实例上，`GET /ops/readiness` -> `ready=true`, `blockers=[]`
    - 同一实例上 `GET /execution/gate` -> `should_block=false`, `reasons=[]`
- Decisions:
  - 这一步没有新增独立“执行健康接口”，而是把 blocker 直接接进现有 readiness/gate，减少运维入口分叉。
  - 对 alert blocker 的处理先聚焦于真正会影响交易安全的 mismatch / unmatched / duplicate fills；如果只有别的普通告警，仍会给出泛化 review 文案，但不把所有告警都硬编码成专门类别。
- Remaining focus for next session:
  - feature #36：每日 acceptance 证据持久化 clean day、manual day、incident day 等关键标签。

## Session update — 2026-03-29
- Completed feature #36: 每日 acceptance 证据现在会以 `clean_day`、`manual_day`、`incident_day`、`blocked_day` 标签持久化到 operations journal，并能被 acceptance 接口直接消费。
- Code changes:
  - `OperationsJournalEntry` 新增 `evidence_tags` 字段；`OperationsJournalService.record()` 会根据 readiness 快照里的 `ready`、alert 数量和 execution pending 状态生成当日证据标签。
  - `acceptance_summary()` 现在返回 `evidence.counts` 和 `latest_tags`；`acceptance_timeline()` 的每日点位也会带 `evidence_tags`，给后续周报、timeline、rollout 直接复用。
  - 顺手修复了 `/ops/acceptance/timeline` 的真实接口 bug：route 之前把 keyword-only 的 `window_days` 错当成位置参数传递，导致真实 API 会报 `TypeError`。
- Validation:
  - `.venv/bin/pytest tests/test_operations_journal.py tests/test_api.py -q` -> `43 passed`
  - 隔离 HTTP 验证：
    - `POST /ops/journal/record` on `http://127.0.0.1:8032` -> 返回 `evidence_tags=["manual_day","incident_day","blocked_day"]`
    - `GET /ops/acceptance` on the same instance -> 返回 `evidence.counts.manual_day=1` 与 `latest_tags`
    - `GET /ops/acceptance/timeline?window_days=1` -> 返回当日 `evidence_tags=["blocked_day","incident_day","manual_day"]`
- Decisions:
  - 这一步把 acceptance 证据落成 journal entry 的显式字段，而不是藏在 `notes` 或每次接口现算，目的是让后续周报、rollout、live acceptance 都共享同一份可追溯证据。
  - 标签规则先保持简单直接：`clean_day` 看 readiness + 无告警，`manual_day` 看 pending approval，`incident_day` 看告警/错误，`blocked_day` 看 readiness=false；后续 feature 再逐步把这些标签消费到周报和 rollout 门槛里。
- Remaining focus for next session:
  - feature #37：周报聚合过去 7 天 acceptance 证据，帮助个人交易者判断是否维持 paper-trading 纪律。

## Session update — 2026-03-29
- Completed features #43-#48: diagnostics / preflight / readiness / dashboard / regression 收尾完成，`PLAN.json` 全部 48 项已完成。
- Code changes:
  - `TradingCatApplication` 新增短时 summary cache，并把 `research_readiness_summary()`、`startup_preflight_summary()`、`_base_validation_snapshot()`、`execution_gate_summary()`、`operations_readiness()`、`operations_rollout()`、`go_live_summary()`、`live_acceptance_summary()`、`operations_period_report()` 改成复用缓存，避免 dashboard / readiness 在同一请求里重复做整套重计算。
  - `preflight/startup` 现在返回带 `research_ready`、`research_blockers`、`research_readiness`、`system_ready` 的聚合结果；`/diagnostics/summary` 与 `/ops/readiness` 统一复用这套 research blocker 语义，不再一个接口说健康、另一个接口才报 blocked。
  - `DashboardFacade` 去掉了循环内重复读取 selection/allocation summary 的坏味道；`dashboard/summary` 也不再在 GET 链路里偷偷生成并落盘新的日报/计划，而是在缺少归档时返回显式 fallback note，避免只读接口带副作用。
  - `dashboard/summary` 改成复用单次 `strategy_signal_map + build_profit_scorecard()` 结果，不再对同一组 strategy signals 额外重复跑一次完整 report；`build_profit_scorecard()` 也补上 `portfolio_metrics`，让 dashboard 不必再额外拉一次 report。
  - dashboard 前端和 API 现在完整消费 `blocked_by_data` / `paper_only` / `status_reason` / `acceptance_progress`；策略卡片会明确区分“数据阻塞”和“仅纸面”，operations 区也能直接看到 clean week streak 和距离下一门槛的剩余天数。
- Validation:
  - `.venv/bin/pytest tests/test_research_reporting.py tests/test_selection_service.py tests/test_allocation_service.py tests/test_dashboard_facade.py tests/test_reports_helper.py tests/test_operations_journal.py tests/test_api.py::test_preflight_and_readiness_align_research_blockers tests/test_api.py::test_dashboard_page_and_assets tests/test_api.py::test_dashboard_summary_endpoint tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress -q` -> `53 passed`
  - 隔离 HTTP 验证（`TRADINGCAT_DATA_DIR=/tmp/tradingcat-harness-http-final.7u2ntO`, `http://127.0.0.1:8037`）：
    - `GET /preflight/startup` -> `healthy=true`, `research_ready=false`, `system_ready=false`，并返回 `research_blockers`
    - `GET /diagnostics/summary` -> `ready=false`，`blockers` 包含 synthetic fallback / missing history blocker，且返回 `research_readiness`
    - `GET /ops/readiness` -> `ready=false`，顶层 `blockers` 与 `research_readiness.blocking_reasons` 对齐
    - `GET /dashboard/summary` -> 返回 `details.acceptance_progress`、`strategies.blocked_by_data_count=1`，且 `strategy_c_option_overlay.display_status="blocked_by_data"`
- Decisions:
  - 为了避免这次 harness 再次把 `app.py` / facade 推成大对象，这轮优先做“复用已有 service + 缓存聚合 + 去掉 GET 副作用”，而不是继续往 route 或 dashboard facade 里硬塞新判断。
  - 老的 `tests/test_api.py::test_preflight_and_broker_recovery_endpoints` 单跑仍然非常慢，当前没有把它作为这轮 feature 收尾的 gating；相应功能由更窄的 API 回归测试和真实 HTTP 验证覆盖。后续若要继续优化，可单独把 broker recovery 测试拆开做轻量化。

## Session update — 2026-03-29
- Completed architecture harness feature: 抽出 `DataQualityQueryService` 与 `ReadinessQueryService`，把 readiness / data-quality 聚合从 `TradingCatApplication` 收口到独立 query service。
- Code changes:
  - 新增 `tradingcat/services/query_services.py`，集中承接 `data_quality_summary`、`repair_priority_symbols`、`history_baseline_symbols`、`baseline_quote_currencies`，以及 `research_readiness`、`startup_preflight`、`base_validation`、`execution_gate`、`operations_readiness` 的读模型聚合。
  - `TradingCatApplication` 现在主要保留缓存与 delegation：`data_quality_summary()`、`_repair_priority_symbols()`、`history_baseline_symbols()`、`_baseline_quote_currencies()`、`_build_base_validation_snapshot()`、`_build_research_readiness_summary()`、`_build_startup_preflight_summary()`、`_build_execution_gate_summary()`、`_build_operations_readiness()` 都改成委托给新 query service。
  - query service 的依赖全部通过 getter / callable 注入，避免 runtime recovery 后继续偷绑旧的 registry / execution / strategy-analysis 对象；新增 `tests/test_runtime_recovery.py::test_data_quality_queries_follow_recovered_strategy_registry` 锁定这一点。
- Validation:
  - `.venv/bin/pytest tests/test_runtime_recovery.py tests/test_selection_service.py -q` -> `13 passed`
  - `TRADINGCAT_DATA_DIR=$(mktemp -d) TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots -q` -> `1 passed`
  - 隔离 HTTP 验证：
    - 在 `http://127.0.0.1:8032` 的临时实例上，`GET /data/quality` -> `200 OK`，返回 `ready=true`、`scope="research_universe"`、以及基于 query service 生成的 `target_symbols` / `reports`
- Decisions:
  - 这一步先收口 query 读模型，不顺手去碰 `DashboardFacade` / `ResearchFacade`，避免一次 session 同时拆编排层和 facade，导致边界重新变糊。
  - 真实 `preflight/startup`、`ops/readiness`、`execution/gate` 在空数据目录下仍会被当前研究/验证链路拖慢；本次把它们的结构性回归交给 focused pytest 和 runtime-safe 边界测试兜住，下一轮若继续优化会优先处理这条重链路的启动成本。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先做 `PortfolioProjectionService` 与 facade 瘦身，把账户投影、cash map、curve / allocation mix 从 `app.py` 和 `facades.py` 的重复逻辑里收口出来。

## Session update — 2026-03-29
- Completed architecture harness feature: 抽出 `PortfolioProjectionService`，把账户投影、cash map、nav curve 和 allocation mix 从 `app.py` / `DashboardFacade` 的重复 helper 里收口出来。
- Code changes:
  - 新增 `tradingcat/services/portfolio_projections.py`，集中承接 `serialize_position`、`account_positions`、`account_cash_map`、`account_curves`、`allocation_mix` 这组账户投影逻辑。
  - `TradingCatApplication` 现在只持有 `portfolio_projections` 服务，不再保留自己那套 `_account_keys / _account_positions / _account_cash_map / _account_curves` 重复 helper。
  - `DashboardFacade` 现在显式消费 `self._app.portfolio_projections` 来构建 `assets` 和 `accounts`，不再自己重复实现账户切片、曲线和 allocation mix 规则；新增 focused 测试锁定 facade 通过 projection service 取数。
- Validation:
  - `.venv/bin/pytest tests/test_portfolio_projections.py tests/test_dashboard_facade.py -q` -> `3 passed`
  - `.venv/bin/pytest tests/test_runtime_recovery.py tests/test_selection_service.py -q` -> `13 passed`
  - `TRADINGCAT_DATA_DIR=$(mktemp -d) TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots -q` -> `1 passed`
  - 隔离 HTTP 验证：
    - 在 `http://127.0.0.1:8033` 的临时实例上 stub 掉不相关的重型 dashboard 上游聚合后，`GET /dashboard/summary` -> `200 OK`，返回 `accounts.total.nav_curve`、`allocation_mix`、`details.acceptance_progress.remaining_clean_days=25`，证明 dashboard summary 经过新 projection service 后账户结构仍正常。
- Decisions:
  - 这一步只收口“账户投影”这层共享读模型，不顺手把 `ResearchFacade` 或 dashboard 其它聚合一并重写，避免 facade 瘦身和研究编排拆分互相缠住。
  - 真实未 stub 的 dashboard API 在空数据目录下仍会被完整 research/report 聚合拖慢，所以本次 HTTP gating 使用临时实例 + 上游轻 stub，只验证 projection/facade 改动本身的链路正确性。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先做 typed response model 收口，先覆盖 `/data/quality`、`/data/history/coverage`、`/data/fx/rates`、`/data/history/corporate-actions` 这组 read endpoint。

## Session update — 2026-03-29
- Completed architecture harness feature: 为关键 data read endpoint 补上显式 `response_model`，开始把 transport contract 从裸 dict 收口成 typed payload。
- Code changes:
  - `tradingcat/api/view_models.py` 新增 `HistoryCoverageResponse`、`DataQualityResponse`、`FxRatesResponse`、`CorporateActionsResponse` 及其 report/item view model，保持 `extra="allow"` 兼容现有字段，同时把关键结构显式化。
  - `tradingcat/routes/market_data.py` 现在为 `/data/quality`、`/data/history/coverage`、`/data/fx/rates`、`/data/history/corporate-actions` 声明了 `response_model`，不再让这些 read endpoint 漂在裸 dict 契约上。
  - `tests/test_api.py` 新增 OpenAPI 断言，锁定上述四个 endpoint 已经真正挂上 response model，而不只是代码里定义了 model。
- Validation:
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_data_history_coverage_endpoint_exposes_summary_fields tests/test_api.py::test_data_history_corporate_actions_endpoint_exposes_status tests/test_api.py::test_data_fx_rates_endpoint_exposes_status tests/test_api.py::test_data_read_endpoints_publish_response_models_in_openapi -q` -> `4 passed`
  - 隔离 HTTP 验证（`TRADINGCAT_DATA_DIR=$(mktemp -d)`, `http://127.0.0.1:8034`）：
    - `GET /data/history/coverage?symbols=SPY&start=2026-03-02&end=2026-03-06` -> 返回 typed coverage 字段，含 `minimum_coverage_ratio`、`missing_windows`、`blockers`
    - `GET /data/fx/rates?base_currency=CNY&quote_currency=USD&start=2026-03-02&end=2026-03-06` -> 返回 `status="available"`、`rate_count=1`、`rates=[...]`
    - `GET /data/history/corporate-actions?symbol=SPY&start=2026-03-02&end=2026-03-06` -> 返回 `status="confirmed_none"`、`action_count=0`
    - `GET /data/quality` -> 返回 typed `scope/target_symbols/reports` 结构
- Decisions:
  - 这一步先收口 data read endpoint，因为它们 payload 边界最稳定、回归面最小，适合作为 typed contract 的第一批落点。
  - `test_data_quality_and_readiness_surface_coverage_blockers` 仍会被现有 readiness 重链路拖慢，所以本次不把它作为 typed contract feature 的 gating；语义兼容由更窄的 API 回归和真实 HTTP 覆盖。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先把 typed payload 继续推进到 research/report 与 strategy detail，再考虑把 `OperationsReadinessResponse` 里的 `data_quality` 等嵌套字段收紧成 typed model。

## Session update — 2026-03-29
- Completed architecture harness feature: 为 `/research/report/run` 和 `/research/strategies/{id}` 补上显式 `response_model`，把 research 主读链路也收口到 typed contract。
- Code changes:
  - `tradingcat/api/view_models.py` 新增 `ResearchReportResponse`、`ResearchStrategyReportView`、`StrategyDetailResponse`、`StrategyDetailSignalView` 等兼容型 model，只锁定页面和测试已经依赖的关键字段，其余字段继续允许扩展。
  - `tradingcat/routes/research.py` 现在为 `/research/report/run` 和 `/research/strategies/{strategy_id}` 声明了 `response_model`，不再让 report/detail 停留在隐式 dict 契约。
  - `tests/test_api.py` 新增 OpenAPI 断言，锁定这两个 research read endpoint 已经真正发布 typed schema。
- Validation:
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_research_read_endpoints_publish_response_models_in_openapi -q` -> `1 passed`
  - `TRADINGCAT_DATA_DIR=$(mktemp -d) TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_research_strategy_details_follow_persistent_universe_and_expose_indicator_snapshots -q` -> `1 passed`
- Decisions:
  - 这一步继续采用“兼容型 model”策略，只把已被测试与前端消费的表面字段钉住，避免一次性把 detail/report 里仍在演化的长尾字段硬编码死。
  - `test_research_interfaces_expose_data_blockers` 和 `test_research_scorecard_and_strategy_detail_endpoints` 在当前研究链路下仍然很重，所以本次不把它们作为 response-model feature 的 gating；关键兼容性由 persistent-universe API 回归和 OpenAPI 断言覆盖。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先把 `OperationsReadinessResponse` 里的 `data_quality` 等嵌套字段收紧成 typed model，并评估是否继续把 `ResearchFacade` 向更薄的协调层收口。

## Session update — 2026-03-29
- Completed architecture harness feature: 把 preflight / diagnostics 入口也补进 typed contract，避免 readiness 相关 surface 一边 typed、一边裸 dict。
- Code changes:
  - `tradingcat/api/view_models.py` 新增 `ResearchReadinessResponse`、`ResearchReadinessStrategyView`、`StartupPreflightResponse`，并把 `OperationsReadinessResponse.data_quality` 收紧为 `DataQualityResponse`，同时显式挂出 `research_readiness`。
  - `tradingcat/routes/preflight.py` 现在为 `/preflight/startup` 声明 `StartupPreflightResponse`，为 `/diagnostics/summary` 声明 `OperationsReadinessResponse`。
  - `tests/test_api.py` 新增 OpenAPI 断言，锁定这两个 readiness 相关入口也已经真正发布 schema。
- Validation:
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_preflight_and_diagnostics_publish_response_models_in_openapi -q` -> `1 passed`
  - 隔离 HTTP 验证（`http://127.0.0.1:8035`，临时实例对上游重链路做轻 stub）：
    - `GET /preflight/startup` -> 返回 `healthy=true`、`research_ready=false`、`research_readiness.blocked_count=1`
    - `GET /diagnostics/summary` -> 返回 `ready=false`、`data_quality.scope="research_universe"`、`research_readiness.report_status="blocked"`
- Decisions:
  - 这一步优先把 preflight/diagnostics 与现有 readiness model 对齐，而不是继续扩散新的轻量临时 payload，避免又出现一组“看着像 readiness 但 schema 不同”的端点。
  - 真实未 stub 的 diagnostics/readiness 仍会被当前研究/验证链路拖慢，所以本次 HTTP gating 使用临时实例 + 轻 stub，重点确认 transport contract 和嵌套 typed payload 没有破坏。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先评估 `OperationsReadinessResponse` 里剩余裸 dict 嵌套（如 `diagnostics`、`alerts`、`compliance`）是否值得继续 typed 化，以及是否开始把 `ResearchFacade` 进一步收口成更薄的协调层。

## Session update — 2026-03-29
- Completed architecture harness feature: 抽出 `ResearchQueryService`，把 `ResearchFacade` 收紧成更薄的读模型协调层，不再直接堆 report/detail/backtest 编排。
- Code changes:
  - `tradingcat/services/query_services.py` 新增 `ResearchQueryService`，集中承接 `scorecard`、`report`、`stability`、`recommendations`、`ideas`、`run_backtests`、`strategy_detail`、`asset_correlation`、`review_selections`、`review_allocations` 这组研究读链路。
  - `tradingcat/app.py` 现在装配 `self.research_queries`，并通过 getter 注入 runtime-sensitive 依赖，确保 runtime recovery 后 research query 仍跟随最新 strategy registry / signal provider。
  - `tradingcat/facades.py` 里的 `ResearchFacade` 现在把主研究查询统一委托给 `self._app.research_queries`，自身只保留 transport-level 协调与响应校验。
  - `tests/test_runtime_recovery.py` 新增 `test_research_queries_follow_recovered_strategy_registry`，锁定 research query 路径不会在 runtime recovery 后继续绑住旧 strategy 实例。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/services/query_services.py tradingcat/app.py tradingcat/facades.py tests/test_runtime_recovery.py`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_runtime_recovery.py::test_research_queries_follow_recovered_strategy_registry tests/test_runtime_recovery.py::test_data_quality_queries_follow_recovered_strategy_registry tests/test_api.py::test_research_backtest_endpoints -q` -> `3 passed`
  - `TRADINGCAT_DATA_DIR=$(mktemp -d) TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_research_reporting.py::test_research_report_does_not_pollute_short_window_stock_signals -q` -> `1 passed`
  - 隔离 HTTP 验证（`TRADINGCAT_DATA_DIR=$(mktemp -d)`, `http://127.0.0.1:8039`）：
    - `GET /broker/status` -> `200 OK`，返回 simulated broker healthy payload
    - `POST /data/instruments` 写入 `IVV` / `VOO` / `AAPL`
    - `POST /research/backtests/run?as_of=2026-03-08` -> `200 OK`，返回 `count=7`
    - `GET /research/strategies/strategy_a_etf_rotation?as_of=2026-03-08` -> `200 OK`，返回 `signals=["IVV", "VOO"]`、`signal_source="historical_momentum_rotation"`
- Decisions:
  - 这一步只收口 research query 编排，不顺手把 `summarize_news` 或更深的 reporting/detail 组装也挪走，避免一次 session 同时改 facade 边界和 strategy-analysis 内部职责。
  - `ResearchQueryService` 统一采用 getter 注入 runtime-sensitive 依赖，和已有 query service 模式保持一致，这样 runtime recovery 时不会出现 facade 偷绑旧 registry 的回潮。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先继续拆 `StrategyAnalysisService` 的 reporting/detail 聚合，评估是否把 report/detail/scorecard 进一步拆成更清晰的 reporting service。

## Session update — 2026-03-29
- Completed architecture harness feature: 抽出 `StrategyReportingService`，把 `StrategyAnalysisService` 从“既做分析底座又做读模型组装”收口成兼容型 analysis core + reporting layer。
- Code changes:
  - 新增 `tradingcat/services/strategy_reporting.py`，把 `summarize_strategy_report`、`summarize_strategy_stability`、`recommend_strategy_actions`、`build_profit_scorecard`、`strategy_detail` 这组 reporting/detail 组装逻辑迁到独立 service。
  - `tradingcat/services/strategy_analysis.py` 现在只保留 experiment/correlation/history/benchmark/helper 这组分析底座方法，上述 reporting API 变成薄代理并统一委托给 `self.reporting`。
  - `tradingcat/services/research.py` 显式暴露 `strategy_reporting`，并让 research app service 与 `ResearchIdeasService` 优先消费 reporting layer，而不是继续直接绑定 analysis core。
  - `tradingcat/runtime.py` 与 `tradingcat/app.py` 补出 `strategy_reporting` 挂点，为后续继续瘦身 facade / app 编排层留出稳定接口。
  - `tests/test_research_reporting.py` 新增 `test_research_service_exposes_reporting_service_separately`，锁定 experiment service、analysis core、reporting layer 这三个角色已经显式分开。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/services/strategy_analysis.py tradingcat/services/strategy_reporting.py tradingcat/services/research.py tradingcat/runtime.py tradingcat/app.py tests/test_research_reporting.py`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_research_reporting.py::test_research_service_exposes_reporting_service_separately tests/test_research_reporting.py::test_research_report_applies_walk_forward_thresholds tests/test_research_reporting.py::test_research_strategy_detail_returns_curve tests/test_api.py::test_research_backtest_endpoints tests/test_runtime_recovery.py -q` -> `11 passed`
  - 隔离 HTTP 验证（`TRADINGCAT_DATA_DIR=$(mktemp -d)`, `http://127.0.0.1:8040`）：
    - `GET /broker/status` -> `200 OK`
    - `POST /data/instruments` 写入 `IVV` / `VOO` / `AAPL`
    - `POST /research/report/run?as_of=2026-03-08` -> `200 OK`，返回 `blocked_count=1`、`strategy_a_etf_rotation.signal_insights[0].symbol="IVV"`
    - `GET /research/strategies/strategy_a_etf_rotation?as_of=2026-03-08` -> `200 OK`，返回 `signals=["IVV", "VOO"]`、`signal_source="historical_momentum_rotation"`、detail 曲线结构完整
- Decisions:
  - 这一步采用“先拆职责、再逐步迁移调用点”的兼容路径：`StrategyAnalysisService` 仍保留原 public API，因此现有 patch/test/route 调用不需要一起改名，但重逻辑已经不再堆在同一个类里。
  - `ResearchQueryService` 与 readiness 相关 query service 暂时继续通过 `strategy_analysis` 入口调用，这样现有测试里对 `app.strategy_analysis` 的 monkeypatch 仍然有效；后续若继续收口，可在兼容层稳定后再切到 `strategy_reporting`。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先看 `DashboardFacade` / `app.py` 里剩余 orchestrator 逻辑还能否继续下沉到 query/projection/reporting service，或者补更明确的 architecture boundary test 防止回潮。

## Session update — 2026-03-29
- Completed architecture harness feature: 把 `app.py` / `DashboardFacade` 里剩余的 research reporting 编排继续下沉到 `ResearchQueryService`，并补上 facade/app 层的架构边界测试。
- Code changes:
  - `tradingcat/app.py` 里的 `review_strategy_selections()` 与 `review_strategy_allocations()` 现在通过 `self.research_queries.recommendations(as_of)` 获取推荐结果，不再自己直接调用 `strategy_analysis.recommend_strategy_actions(...)`。
  - `tradingcat/facades.py` 的 `DashboardFacade.build_summary()` 现在通过 `self._app.research_queries.scorecard(..., include_candidates=True)` 取得 candidate scorecard，不再直接触碰 `strategy_analysis.build_profit_scorecard(...)`。
  - `tests/test_architecture_boundaries.py` 新增 app/facade 边界检查，禁止 `app.py` 与 `facades.py` 再直接出现 `strategy_analysis.` 编排调用。
  - `tests/test_selection_service.py` 新增 `test_app_strategy_reviews_delegate_to_research_queries`，锁定 app 层 selection/allocation review 已经统一走 research query service。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/app.py tradingcat/facades.py tests/test_architecture_boundaries.py tests/test_selection_service.py`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_architecture_boundaries.py tests/test_dashboard_facade.py tests/test_selection_service.py::test_app_strategy_reviews_delegate_to_research_queries -q` -> `6 passed`
  - 隔离 HTTP 验证（`TRADINGCAT_DATA_DIR=$(mktemp -d)`, `http://127.0.0.1:8042`，对 research/operations 重链路做轻 stub）：
    - `GET /broker/status` -> `200 OK`
    - `GET /dashboard/summary` -> `200 OK`，返回 `strategies.blocked_by_data_count=1`、`strategies.paper_only_count=1`、`details.acceptance_progress.remaining_clean_days=25`，证明 dashboard summary 已通过 `research_queries` 路径消费 candidate scorecard
  - 真实未 stub 的 `GET /dashboard/summary` 在 `http://127.0.0.1:8041` 上 60 秒超时，说明当前 dashboard 仍受历史 research/readiness 重链路拖慢；本次将其记录为既有性能阻塞，而不是本 feature 的功能回归。
- Decisions:
  - 这一步优先消除 app/facade 对 `strategy_analysis` 的直接编排依赖，并用边界测试防止回潮；没有同时去重写 dashboard 上游的重聚合路径。
  - dashboard 的真实 HTTP 仍然偏慢，所以沿用“真实路由 + 轻 stub 上游重链路”的 E2E gating 策略，只验证这次 candidate scorecard / acceptance 透传改动本身。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先看 dashboard/readiness 重链路能否继续分层或缓存化，或者转去处理 `strategies/simple.py` 中生产策略与 research candidate / fallback template 混居的问题。

## Session update — 2026-03-29
- Completed architecture harness feature: 把 `strategies/simple.py` 中的 research candidate 策略拆到独立模块，开始把生产策略和 research candidate 的代码边界拉开。
- Code changes:
  - 新增 `tradingcat/strategies/research_candidates.py`，承接 `MeanReversionStrategy`、`DefensiveTrendStrategy`、`AllWeatherStrategy`、`Jianfang3LStrategy` 四个 research candidate 策略实现。
  - `tradingcat/strategies/simple.py` 现在只保留生产策略（ETF rotation / equity momentum / option overlay）、共享 indicator helper 和 metadata，并 re-export research candidate 策略，保持现有 import 兼容。
  - `tradingcat/runtime.py` 现在显式从 `research_candidates.py` 装配 candidate registry，避免 runtime 继续把所有策略都当作 `simple.py` 里的同质实现。
  - `tests/test_architecture_boundaries.py` 新增模块边界断言，禁止 `simple.py` 再重新定义 candidate strategy class。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/strategies/simple.py tradingcat/strategies/research_candidates.py tradingcat/runtime.py tests/test_architecture_boundaries.py tests/test_research_reporting.py`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_architecture_boundaries.py tests/test_research_reporting.py::test_research_profit_scorecard_supports_candidate_pool tests/test_runtime_recovery.py -q` -> `12 passed`
  - 隔离 HTTP 验证（`TRADINGCAT_DATA_DIR=$(mktemp -d)`, `http://127.0.0.1:8043`）：
    - `GET /broker/status` -> `200 OK`
    - `GET /research/strategies/strategy_d_mean_reversion?as_of=2026-03-08` -> `200 OK`，返回 `strategy_id="strategy_d_mean_reversion"`、`metadata.name="ETF 均值回归"`、`signals[0].metadata.execution_mode="research_candidate"`，证明 candidate 策略拆模块后仍能被 runtime registry 与 research detail 路径识别
  - `POST /research/backtests/run?as_of=2026-03-08` 在真实空数据目录下仍会触发全量实验重链路，本次没有把它作为模块拆分 feature 的 gating，而是用更贴边的单策略 detail HTTP 验证 candidate registry 可达性。
- Decisions:
  - 这一步先做“代码物理分层 + import 边界”而不强行修改所有下游 import，`simple.py` 继续 re-export candidate 策略，减少大面积改引用的风险。
  - fallback/sample 路径本身还没完全抽成显式诊断策略；本次只先把“生产策略”和“research candidate”从文件层面拆开，给下一步继续治理 sample 回退留出结构空间。
- Remaining focus for next session:
  - 新 architecture harness 的下一步优先考虑补 README / AGENTS 级架构约束，或者继续治理 dashboard/readiness 的真实重链路性能与 `app.py` 最后几段 orchestration。

## Session update — 2026-03-29
- Completed architecture harness feature: 补齐 README / AGENTS 级架构约束，把这轮落地的 query/reporting/strategy-module 边界写成可持续规则。
- Code changes:
  - `README.md` 新增 `Current Architecture Boundaries`，明确 routes、facades、query services、portfolio projections、strategy reporting、strategy modules 和 persistent universe 的职责边界。
  - `AGENTS.md` 新增 `Architecture Boundaries`，把 agent 级落地约束写清楚：新读链路优先落到 query/projection/reporting service，facade 不要直接回到 `strategy_analysis`，新 candidate strategy 不要再混回 `simple.py`。
- Validation:
  - `rg -n "Current Architecture Boundaries|## Architecture Boundaries|sample_instruments\\(\\)|strategy_reporting.py|research_candidates.py" README.md AGENTS.md` 能命中新增约束段落与关键边界关键词。
- Decisions:
  - 这一步保持文档最小增量，只补“防回潮”的操作性规则，不在 README/AGENTS 里重复长篇产品说明或历史背景。
  - 文档规则直接对应本轮已完成的代码边界：query/reporting/projection service、candidate strategy 独立模块、persistent universe 优先，而不是额外发明一套与代码不一致的新术语。
- Remaining focus for next session:
  - 新 architecture harness 剩下更像“性能和尾部收尾”工作：dashboard/readiness 真正的重链路优化、`app.py` 剩余 orchestration 再收口，以及 fallback/sample 路径是否继续做显式诊断隔离。

## Session update — 2026-03-29
- Completed architecture harness feature: 把生产策略 fallback 与 app 的 smoke-test sample 路径收口到显式 helper，避免 `sample_instruments()` 继续藏在主链路里。
- Code changes:
  - 新增 `tradingcat/strategies/fallbacks.py`，把 ETF rotation / equity momentum / option overlay 的 fallback signal 生成集中到显式 fallback helper。
  - `tradingcat/strategies/simple.py` 现在通过 fallback helper 生成生产策略的 sample fallback，不再在主策略模块里直接调用 `sample_instruments()`。
  - `tradingcat/services/market_data.py` 新增 `diagnostic_targets()`，把 smoke-test 的目标选择显式定义为“优先 catalog -> research universe -> sample fallback”。
  - `tradingcat/app.py` 的 `run_market_data_smoke_test()` 现在统一通过 `market_history.diagnostic_targets()` 取目标，不再自己拼 `research_universe() or sample_instruments()`。
  - `tests/test_architecture_boundaries.py` 新增边界约束，禁止 `app.py` / `simple.py` 再直接出现 `sample_instruments(`；`tests/test_market_data_service.py` 新增 diagnostic helper 回归测试。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/app.py tradingcat/services/market_data.py tradingcat/strategies/simple.py tradingcat/strategies/fallbacks.py tests/test_architecture_boundaries.py tests/test_market_data_service.py`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_architecture_boundaries.py tests/test_market_data_service.py::test_market_data_service_diagnostic_targets_reuse_catalog_before_sample_fallback tests/test_runtime_recovery.py -q` -> `13 passed`
  - 真实 HTTP 验证（临时 `uvicorn` + 受限环境下提权执行本机 `curl`）：
    - `POST /market-data/smoke-test` with `{}` -> `200 OK`
    - 返回 `successful_symbols`、`quote_count=13`、`failed_symbols={}`，证明 app 端 smoke-test 仍可用，且走的是显式 diagnostic target 选择路径
- Decisions:
  - 这一步优先治理“隐式 sample fallback”而不是彻底移除所有 sample 数据；sample 仍保留在 bootstrapping、diagnostic helper 与 research-only candidate 模板中，但已经不再埋在生产策略与 app 主链路里。
  - 当前执行环境对本机端口访问有限制，所以真实 HTTP 用了临时 server + 提权 `curl`；这次把限制明确记录下来，避免后续误判为接口自身不通。
- Remaining focus for next session:
  - 新 architecture harness 现在主要剩下 dashboard/readiness 的真实重链路性能与 `app.py` 最后的 orchestration 瘦身；结构性边界已经基本收紧完一轮。

## Session update — 2026-03-29
- Completed architecture harness feature: 收紧 readiness/preflight 重链路，让研究 readiness 只依赖本地持久化数据快照，不再隐式触发完整 strategy report、全年 probe 扫描或远端 market-data 补抓。
- Code changes:
  - `tradingcat/services/query_services.py` 的 `research_readiness_summary()` 不再通过 `summarize_strategy_report()` 生成 readiness，而是走 `StrategyExperimentService.inspect_strategy_readiness()`；同时 `base_validation_snapshot()`、`startup_preflight_summary()`、`execution_gate_summary()`、`operations_readiness()` 都支持复用 app 侧已缓存的 preflight / validation snapshot。
  - `tradingcat/services/strategy_experiments.py` 新增轻量 `inspect_strategy_readiness()` 路径，并把 experiment 的 data snapshot 拆成可配置模式：report/backtest 保留 `include_probes=True` + 可抓取缺失数据；readiness 改成 `include_probes=False` + `fetch_missing=False`，只看当前信号和本地覆盖。
  - `tradingcat/services/market_data.py` 新增 `local_history_only()` / `local_history_snapshot()`，并给 corporate action / FX coverage 增加 `fetch_missing` 开关；readiness 链路不会再因为缺口去隐式抓 bars / actions / FX。
  - `tradingcat/services/strategy_registry.py` 的 `strategy_signal_map()` 新增 `local_history_only=True` 模式，让策略在 readiness/preflight 场景下通过本地历史快照生成 signals，而不是走 `ensure_history()` 的远端补抓语义。
  - `tradingcat/app.py` 把 readiness 相关 builder 改成显式复用 app cache，避免 query service 内部再绕回未缓存路径。
  - `tests/test_runtime_recovery.py` 新增边界回归：research readiness 不再调用完整 strategy report，不再触发远端 bars / corporate actions / FX 获取；`tests/test_api.py` 新增 API 回归，锁定 `/preflight/startup` 与 `/diagnostics/summary` 不依赖 full strategy report 生成。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/services/market_data.py tradingcat/services/strategy_registry.py tradingcat/services/strategy_experiments.py tradingcat/services/query_services.py tradingcat/app.py tests/test_runtime_recovery.py tests/test_api.py`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_runtime_recovery.py tests/test_architecture_boundaries.py -q` -> `15 passed`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_api.py::test_preflight_and_diagnostics_do_not_require_full_strategy_report_generation tests/test_api.py::test_preflight_and_readiness_align_research_blockers tests/test_api.py::test_ops_readiness_typed_contract_accepts_minimal_nested_snapshots -q` -> `3 passed`
  - app 直连 timing：
    - `startup_preflight_summary(date(2026, 3, 8))` -> `blocked`, `blocked_count=7`, `~5.539s`
    - `operations_readiness()` -> `ready=False`, `blockers=18`, `~10.188s`
  - 真实 HTTP 验证（本地 `uvicorn`）：
    - `GET /broker/status` -> `200`, `~0.336s`
    - `GET /preflight/startup` -> `200`, `~10.958s`
    - `GET /diagnostics/summary` -> `200`, `~15.578s`
- Decisions:
  - readiness/preflight 继续保留“保守阻断”语义，但不再在读链路里偷偷做远端补数据；如果本地 history / corporate actions / FX 不完整，就明确反映为 blocker，而不是通过隐式抓取把慢路径藏进健康检查里。
  - experiment/reporting 仍然保留全年 probe signal + 缺口补抓，因为那条链路本来就是研究重路径；本次只把 readiness 改成轻量快照，避免把 report 语义和 preflight 语义再次混在一起。
- Remaining focus for next session:
  - 新 architecture harness 剩余重点现在更像尾部收口：`/dashboard/summary` 这类组合读模型的进一步瘦身，以及 `app.py` 最后几段 orchestration 的继续下沉。

## Session update — 2026-03-29
- Completed architecture harness feature: 抽出 `DashboardQueryService`，把 dashboard 上游的 heavy reads 从 `DashboardFacade` 里继续下沉，收紧成“query service 聚合 + facade 纯 assembler”的结构。
- Code changes:
  - `tradingcat/services/query_services.py` 新增 `DashboardQueryService`，统一聚合 dashboard 所需的 `execution_gate`、daily/weekly report、live acceptance、rollout、operations readiness、data quality、candidate scorecard、active strategy context 和 recent order read-model。
  - `tradingcat/app.py` 新增 `self.dashboard_queries`，把 dashboard 所需的 app/runtime getter 都集中到 query service 的装配阶段；runtime 相关依赖使用 lambda 延迟绑定，避免初始化时提前触发 `self.execution`。
  - `tradingcat/facades.py` 的 `DashboardFacade.build_summary()` 现在优先消费 `dashboard_queries.summary_context()`，不再自己直接串 `execution_gate_summary()`、`operations_period_report()`、`live_acceptance_summary()`、`operations_rollout()`、`operations_readiness()`、`data_quality_summary()`、selection/allocation/active strategy lookup 这些重读链路。
  - `tests/test_dashboard_facade.py` 新增 `test_dashboard_facade_build_summary_delegates_dashboard_reads_to_query_service`，锁定 facade 在构建 summary 时已经真正通过 `dashboard_queries` 取重读模型。
  - `tests/test_architecture_boundaries.py` 新增 `test_dashboard_facade_uses_dashboard_query_service_for_heavy_reads`，禁止 `DashboardFacade` 回流到上述 app-level heavy reads。
- Validation:
  - `.venv/bin/python -m compileall tradingcat/app.py tradingcat/facades.py tradingcat/services/query_services.py tests/test_dashboard_facade.py tests/test_architecture_boundaries.py`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_dashboard_facade.py tests/test_architecture_boundaries.py tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress -q` -> `10 passed`
  - 基线确认：`TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_runtime_recovery.py tests/test_architecture_boundaries.py tests/test_api.py::test_preflight_and_diagnostics_do_not_require_full_strategy_report_generation -q` -> `16 passed`
  - 真实 HTTP：
    - `GET /broker/status` -> `200`, `~0.343s`
    - `GET /dashboard/summary` 在当前本地 `uvicorn` 进程上等待 35s+ 仍未返回；说明 facade/query 边界已经收紧，但 dashboard 真实慢点还在上游 candidate scorecard / analytics 聚合链路里，尚未通过这一步彻底解决。
- Decisions:
  - 这一步优先做“dashboard orchestration ownership”治理，而不是在同一轮里继续重写 scorecard / analytics / report 生成逻辑；这样能先锁住 facade 不再继续腐烂。
  - 因为真实 `/dashboard/summary` 仍然慢，所以这一步的 E2E 以真实本地 server 探活 + API/TestClient 回归双轨记录：结构抽取已经生效，但性能尾项依然存在，不能假装已经解决。
- Remaining focus for next session:
  - `/dashboard/summary` 现在剩下的主要热点大概率在 candidate scorecard / report 生成与 operations analytics 组合链路，需要继续做 dashboard-specific caching 或 query service 级轻量快照。

## Session update — 2026-03-30
- Completed architecture harness feature: `/dashboard/summary` 改为消费 persisted dashboard scorecard snapshot，不再在请求链路里同步触发 research/report/backtest 级重计算。
- Code changes:
  - `tradingcat/domain/models.py`、`tradingcat/repositories/research.py` 新增 `DashboardScorecardSnapshot` 与 `DashboardSnapshotRepository`，把 dashboard 所需的 scorecard read-model 持久化到独立 snapshot 存储。
  - `tradingcat/services/dashboard_snapshots.py` 新增 `DashboardSnapshotService`，提供三条稳定路径：缺快照时快速返回 `snapshot_status="missing"`、从 persisted experiments 重建 snapshot、以及直接持久化 live candidate scorecard。
  - `tradingcat/services/strategy_reporting.py` 抽出“从 experiments 组装 report/recommendations/scorecard”的可复用 helper，让 research 端继续保留 live compute，而 dashboard 可以只读持久化结果；`tradingcat/services/strategy_experiments.py` 也补存了 `missing_history_symbol_list`，避免 detail/dashboard 再用不稳定的 coverage 推断缺失 symbol。
  - `tradingcat/app.py`、`tradingcat/services/query_services.py`、`tradingcat/facades.py` 改成把 dashboard scorecard 读路径收口到 `dashboard_snapshot_service.load()`；`/research/candidates/scorecard` 会直接持久化 ready snapshot，`/research/report/run` 与 `/research/backtests/run` 会基于最新 persisted experiments 刷新 snapshot。
  - `static/dashboard_strategy.js` 增加最小前端跟随：当 dashboard 使用 `missing/stale` snapshot 时，会在研究动作区域提示当前快照状态和原因。
  - 新增 `tests/test_dashboard_snapshots.py`，并扩展 `tests/test_api.py`，锁定 snapshot 缺失快速返回、candidate scorecard 持久化 snapshot、report-run 刷新 snapshot、以及 dashboard 不再触发 live scorecard 重算。
- Validation:
  - `.venv/bin/pytest tests/test_dashboard_snapshots.py tests/test_dashboard_facade.py tests/test_architecture_boundaries.py tests/test_api.py::test_dashboard_summary_endpoint tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress tests/test_api.py::test_dashboard_summary_returns_missing_snapshot_without_live_scorecard_recompute tests/test_api.py::test_research_candidate_scorecard_persists_dashboard_snapshot tests/test_api.py::test_research_report_run_refreshes_dashboard_snapshot_from_persisted_experiments -q` -> `17 passed`
  - `TRADINGCAT_FUTU_ENABLED=false .venv/bin/pytest tests/test_runtime_recovery.py tests/test_research_reporting.py tests/test_selection_service.py tests/test_allocation_service.py tests/test_dashboard_snapshots.py tests/test_dashboard_facade.py tests/test_architecture_boundaries.py tests/test_api.py::test_dashboard_summary_endpoint tests/test_api.py::test_dashboard_summary_surfaces_strategy_status_and_acceptance_progress tests/test_api.py::test_dashboard_summary_returns_missing_snapshot_without_live_scorecard_recompute tests/test_api.py::test_research_candidate_scorecard_persists_dashboard_snapshot tests/test_api.py::test_research_report_run_refreshes_dashboard_snapshot_from_persisted_experiments -q` -> `62 passed, 1 warning`
  - `python3 -m py_compile tradingcat/services/dashboard_snapshots.py tradingcat/services/strategy_reporting.py tradingcat/services/strategy_experiments.py tradingcat/app.py tradingcat/facades.py tradingcat/repositories/research.py tests/test_dashboard_snapshots.py tests/test_api.py`
  - 真实 HTTP（隔离 `TRADINGCAT_DATA_DIR`, `TRADINGCAT_FUTU_ENABLED=false`, fresh `uvicorn :8042`）：
    - `GET /broker/status` -> `200`, `~0.004s`
    - 首次 `GET /dashboard/summary?as_of=2026-03-08` -> `200`, `~1.574s`, `snapshot_status="missing"`
    - `POST /research/candidates/scorecard?as_of=2026-03-08` -> `200`, `~12.195s`
    - 再次 `GET /dashboard/summary?as_of=2026-03-08` -> `200`, `~0.524s`, `snapshot_status="ready"`, `snapshot_generated_at` 已存在
- Decisions:
  - dashboard 现在默认只读最近一次 persisted snapshot；没有 snapshot 时显式返回 `missing`，不再偷偷触发 live scorecard。
  - candidate scorecard 仍然保留重计算能力，但那条慢路径只在 research 端点上发生；dashboard 请求本身只做快照读取和现有 readiness/ops 聚合。
  - 这一步没有继续把 `/dashboard/summary` 里其他 readiness/ops 聚合全部做成 snapshot，因为最重的 candidate scorecard 已经被切出主请求链路，当前真实耗时已经降到可接受范围。
- Remaining focus for next session:
  - 如果继续收尾 architecture harness，下一步更像是优化 `operations/readiness` 等剩余读模型的尾延迟，以及把 `app.py` 最后几段 orchestration 再往 service 层下沉。

## Session update — 2026-03-31
- Completed features #3/#4/#5: research readiness 只再对默认 execution strategies 建 gate，base/candidate strategy 的 blocker 范围都收紧到真实输入依赖。
- Code changes:
  - `tradingcat/services/query_services.py` 的 `ReadinessQueryService.research_readiness_summary()` 现在只请求默认 execution strategy ids，不再把 `strategy_d/e/f/g` 候选策略混入 production readiness gate。
  - `tradingcat/app.py` 把默认 execution strategy ids 作为显式依赖传给 readiness query service，resident 与 fresh 进程都会按同一 execution universe 生成 blocker。
  - `tests/test_runtime_recovery.py` 新增回归，锁定 readiness 只会向 signal provider 请求 `strategy_a_etf_rotation`、`strategy_b_equity_momentum`、`strategy_c_option_overlay`，并继续坚持 `local_history_only=true`。
  - `tests/test_research_reporting.py` 新增 blocker scope 回归，锁定 corporate-action / FX blocker 只针对当前 signal symbols 生效；`strategy_a_etf_rotation` 只会看到 `QQQ, SPY, VTI` 与 `USD` 的真实依赖。
- Validation:
  - `.venv/bin/pytest tests/test_market_data_service.py::test_market_data_service_refreshes_catalog_after_external_repo_update tests/test_api.py::test_reset_state_refreshes_readiness_and_rollout_callables tests/test_api.py::test_ops_readiness_typed_contract_accepts_minimal_nested_snapshots tests/test_api.py::test_readiness_and_execution_gate_surface_execution_and_mismatch_blockers tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers tests/test_service_health.py -q` -> `7 passed`
  - `.venv/bin/pytest tests/test_runtime_recovery.py::test_research_readiness_limits_gate_to_default_execution_strategies tests/test_research_reporting.py::test_strategy_readiness_limits_blockers_to_current_signal_symbols tests/test_runtime_recovery.py::test_research_readiness_uses_experiment_inspection_instead_of_full_reporting tests/test_runtime_recovery.py::test_research_readiness_avoids_remote_market_data_fetches tests/test_api.py::test_preflight_and_readiness_align_research_blockers -q` -> `5 passed`
  - `.venv/bin/pytest tests/test_selection_service.py tests/test_allocation_service.py tests/test_dashboard_facade.py tests/test_api.py::test_rollout_live_acceptance_and_go_live_surface_acceptance_blockers -q` -> `16 passed`
  - `curl -sS --max-time 5 http://127.0.0.1:8000/preflight/startup` -> `research_readiness.blocked_count=3`，`blocked_strategy_ids=["strategy_a_etf_rotation","strategy_b_equity_momentum","strategy_c_option_overlay"]`
  - `curl -sS --max-time 5 http://127.0.0.1:8000/ops/readiness` -> `research_readiness.blocked_strategy_ids` 与 `/preflight/startup` 对齐，同时 `data_quality.ready=true`
- Decisions:
  - 顶层 readiness gate 现在代表“默认 execution set 是否可推广”，而不是“整个 research candidate 池是否完全无 blocker”；候选策略的 blocker 继续保留在各自研究输出里。
  - resident `:8000` 需要受控重启才能反映这次语义收紧；重启后 live payload 已从 7 个 blocked strategies 收敛为 3 个真实 execution blockers。
- Remaining focus for next session:
  - feature #6/#7/#8/#9/#10/#11：继续把 synthetic honesty、go-live/live-acceptance、rollout policy、dashboard summary 与 selection/allocation 的控制面语义彻底对齐。
