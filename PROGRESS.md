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
