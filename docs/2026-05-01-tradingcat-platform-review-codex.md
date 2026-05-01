# TradingCat 个人量化交易平台审查报告（Codex 第二版）

> 日期：2026-05-01
> 输入：`docs/2026-05-01-tradingcat-platform-review.md`（Opus 方案）、Codex 第一版、当前代码库核验
> 结论：Opus 的主线可以采纳，但必须修正若干代码事实；第二版以“先补安全和断链，再做交易日工作流产品化”为核心。

## 1. 总体判断

TradingCat 的底座方向是对的：本地优先、三市场、风控门禁、人工审批、审计日志、回测到模拟再到实盘的分阶段上线管线。这不是一个缺少策略数量或缺少 AI 的系统，当前最大瓶颈是“交易日闭环没有成为一个统一工作流”。

最终形态应是个人交易者的三市场量化交易工作台，而不是散落的功能集合：

- 盘前：市场状态、今日能否交易、可交易市场、风险边界、计划订单、待审批项、阻塞原因、观察清单。
- 盘中：持仓、订单、审批、风险、洞察和市场结构变化能关联起来。
- 盘后：逐条计划对照订单/成交/审批/偏差/TCA，并沉淀下一交易日调整。

第二版优先级：

1. P0：安全红线和断链修复。
2. P1：统一交易日驾驶舱和只读 workflow 聚合层。
3. P2：盘中洞察矩阵和盘后执行质量复盘。
4. P3：三市场真实交易基础设施。

## 2. 对 Opus 方案的 Review

Opus 方案的产品方向可采纳：从“自动交易系统”升级为“三市场交易工作台”、建设 `TradingDayCockpit`、把盘前简报和交易计划合并为盘前决策包、强化盘后执行对照，这些判断与当前代码形态一致。

需要纳入的内容：

- “交易日闭环分散”是当前最大产品问题。
- `TradingDayWorkflowService` 可以作为 read-model 聚合层，但必须不下单、不审批、不改组合。
- A 股半自动边界应在 execution/broker 层形成硬拦截，不能只依赖 `RiskEngine.requires_approval=True`。
- 盘后复盘需要从摘要型日报升级为计划到订单到成交的结构化对照。
- 市场日历、FX、Instrument 主数据和市场特定订单约束确实是三市场实用化短板。

需要修正或废弃的内容：

- Opus 写的 `Python 3.11+` 不准确；当前 `pyproject.toml` 要求 `>=3.12`，PLAN 也写的是 Python 3.12。
- `MarketStateService` 不是“已接入系统”。当前存在 `tradingcat/services/market_state.py`、`static/market_state.js`、`docs/market_state_review.md` 和相关测试，但 `app.py`/`runtime.py`/`facades.py`/`routes/research.py` 没有接通，`static/api.js` 也没有 `researchMarketState*` API 定义。
- `docs/market_state_review.md` 描述的是应有改造或残留设计，不代表当前代码事实。
- 合成数据问题不能一概说“readiness 标记正常”。研究 promotion 已经会阻塞 synthetic fallback；更准确的问题是 quote/FX fallback 的来源标注和执行/复盘引用仍不够硬。
- Opus 把 Polygon/CoinGecko 写成主行情源、把 InsightEngine 写成 4 个 detector、把调度写成 25+ jobs，都需要降级或核实。当前主链路仍以 Futu/yfinance/CN adapters/static fallback 为主；README 写的是三类 insight detector；scheduler 注册表与测试期望还存在漂移。
- Opus 说 Instrument 缺 `lot_size/tradable` 不准确。模型已有这些字段，真正问题是 DuckDB 不保真、风险引擎没有充分使用主数据、还缺 `exchange/sector/industry/data_source/quote_permission` 等字段。
- 默认策略“硬编码”也要精确表达：默认执行策略 ID 确实写在 `app.py`，但 active strategy 会优先读 allocations/selection；问题不是完全不能动态选择，而是默认执行集和 registry 构建仍不够配置化。
- WebSocket 不应进入 P0。当前轮询和 APScheduler 足够先做 cockpit v1；只有当盘中页面需要低延迟推送和多面板同步时，再引入 WebSocket/SSE。

## 3. 当前代码事实

### 3.1 已有能力

- FastAPI 控制面覆盖 dashboard、journal、signals、portfolio、orders、execution、alerts、compliance、ops、reports、approvals、kill-switch、reconcile、scheduler、research。
- `TradingCatApplication` 已有 preview、execution gate、daily trading plan、daily summary、operations readiness 和 rollout gate。
- `DailyLogService.run_briefing()` 已能做 market awareness、insight engine、AI briefing 的盘前链路。
- `generate_daily_trading_plan()` 已能把 execution preview、execution gate、market awareness 合成计划并归档。
- `DailyLogService.run_review()` 已能拿到计划、总结、未处理洞察和 AI journal。
- `InsightEngine`、alerts、intraday risk tick 和 `intraday_insight_scan` 已存在。
- 研究 readiness 已能把 synthetic fallback 数据作为 promotion blocker。
- A 股信号在 `RiskEngine` 里会默认 `requires_approval=True`，手动下单也会让 CN 订单走审批。

### 3.2 关键缺口

1. 交易日工作流仍然分散。

   `briefing`、`daily plan`、`review`、`insights`、`operations readiness`、`rollout` 各自存在，但没有一个统一的 today snapshot 回答“今天能不能交易、为什么、下一步是什么”。

2. `MarketStateService` 是断链状态。

   当前前端 `static/market_state.js` 调用 `API.researchMarketState(...)`、`API.researchMarketStateRun(...)`、`API.researchMarketStateTimeline(...)`，但 `static/api.js` 未定义这些方法，后端也没有 `/research/market-state*` 路由。测试 `tests/test_market_state.py` 还引用 `MarketStateSnapshot`，但当前 `domain/models.py` 没有该模型。

3. A 股半自动边界还不够硬。

   `ExecutionService.submit()` 只看 `intent.requires_approval` 决定走 manual broker 还是 live broker。`FutuBrokerAdapter` 初始化了 CN trade context，并且 `place_order()` 对 CN 没有额外禁止逻辑。一旦某个路径构造 CN `OrderIntent(requires_approval=False)`，就存在绕过半自动边界的风险。

4. 盘后复盘仍偏浅。

   `DailyLogService._compare_plan_to_actual()` 主要比较计划意图数和订单数，并标记 blocked 计划；它还没有做逐条 plan item 到 order/fill/approval 的对照，也没有结构化 TCA、未执行原因、额外订单和洞察处理结果。

5. Scheduler 是 UI/测试契约断链。

   `static/dashboard.js` 和 `static/dashboard_autonomous.js` 引用 `self_iteration_weekly`，`tests/test_scheduler_runtime.py` 还期望 `self_iteration_weekly` 和 `acceptance_evidence_capture`，但 `tradingcat/scheduler_runtime.py` 当前注册表没有这些 job。并行复核的定向测试显示实际注册 22 个 job、测试期望 24 个。

6. Journal 前端还有死 API。

   `static/journal.js` 使用 `/journal/daily` 和 `/journal/markdown/latest`，但 `tradingcat/routes/journal.py` 只有 plans/summaries 相关接口。

7. DuckDB instrument catalog 字段保真不足。

   `Instrument` 已有 `lot_size/enabled/tradable/liquidity_bucket/avg_daily_dollar_volume_m/tags`，但 `DuckDbMarketDataStore.instruments` 表只保存 `symbol/market/asset_class/currency/name`，加载后会丢掉筛选和交易属性。

8. 港股/A 股 lot size 主数据没有被充分使用。

   `Instrument` 虽有 `lot_size`，但风险引擎的 lot size 规则仍对 HK/CN 固定返回 `100.0`。这对港股真实每手股数、A 股 ETF/个股差异和未来标的扩展都不够可靠。

9. 市场日历仍然简化。

   `MarketCalendarService` 对 US/HK 基本按工作日处理；CN 只有 2026 假日近似表。HK/CN 午休、US 半日市、交易所假日和长期滚动维护都还不足。

10. FX 和 quote fallback 的来源等级还不够清晰。

   `sync_fx_rates()` 会在 adapter 无数据时生成 synthetic FX series，并把结果保存到历史库。`FxRate` 模型和覆盖检查不保留 source provenance，后续 `summarize_fx_coverage()` 只看是否有 rate。研究侧有 blocker，但 FX 一旦持久化后就可能被当作可用覆盖；执行参考价、manual order reference、复盘和 dashboard 也需要明确区分 real/cached/synthetic。

11. README 与实现存在文档漂移。

   README 写 `InsightAlertBridge` 订阅 EventBus 并把 urgent 洞察 record 到 `AlertService`，但当前实现更像 `AnalysisPipelineService` 显式发 alert。第二版不把 README 当作完全精确事实，应把这种漂移列入后续文档校准。

## 4. 目标架构

新增一个薄的 read-model 聚合层：

```python
class TradingDayWorkflowService:
    def today_snapshot(as_of: date) -> TradingDaySnapshot: ...
    def pre_market_package(as_of: date) -> PreMarketPackage: ...
    def intraday_matrix(as_of: date) -> IntradayMatrix: ...
    def post_market_report(as_of: date) -> PostMarketReport: ...
```

约束：

- 只读聚合，不直接下单、不审批、不撤单、不 reconcile、不改风险状态。
- 复用 `ReadinessQueryService`、`DashboardQueryService`、`ResearchQueryService`、`PortfolioProjectionService`、`StrategyReportingService`，不要继续扩大 `app.py`。
- routes 保持薄层，只做参数解析和 facade 调用。
- AI 只解释结构化结果；结构化字段必须由本地服务生成。

建议输出：

```json
{
  "as_of": "2026-05-01",
  "markets": {
    "CN": {"phase": "sleep", "status": "no_trade", "reason": "holiday_or_closed"},
    "HK": {"phase": "intraday", "status": "ready"},
    "US": {"phase": "pre_market", "status": "pending"}
  },
  "decision": {
    "status": "ready|blocked|observe_only|reduce_only|no_trade",
    "headline": "...",
    "blockers": [],
    "next_actions": []
  },
  "pre_market": {},
  "intraday": {},
  "post_market": {}
}
```

## 5. 实施路线图

### P0：安全和断链修复

1. CN live auto-order hard guard。

   在 `ExecutionService` 或 broker adapter 层增加不可绕过的规则：`Market.CN` 的 live broker 自动下单一律拒绝，除非显式进入未来受控 CN 自动化模式。测试应覆盖 `OrderIntent(requires_approval=False, market=CN)` 也不能触达 live broker。

2. 修复 `MarketStateService` 全链路。

   二选一：

   - 接回：补 domain models、store 注入、app property、facade methods、`/research/market-state*` routes、`static/api.js` 方法、页面入口和测试。
   - 废弃：删除/隐藏 `static/market_state.js` 引用、测试和 `docs/market_state_review.md` 中不再成立的说明。

   当前建议接回，但明确它是研究只读服务，不进入执行链路。

3. 修复 scheduler/UI/test 契约。

   对 `self_iteration_weekly` 和 `acceptance_evidence_capture` 做明确决策：要么实现注册和 handler，要么从 UI 与测试期望中移除。不要保留“按钮存在但 job 不存在”的状态。建议先做 endpoint/job inventory，逐项对齐 `static/api.js`、routes、scheduler registrations 和 tests。

4. 补齐 `/journal/daily` 和 `/journal/markdown/latest`，或清理 `static/journal.js` 对它们的引用。

5. 修复 DuckDB instrument catalog 保真。

   DuckDB schema 需要保存并回读 `lot_size/enabled/tradable/liquidity_bucket/avg_daily_dollar_volume_m/tags`。至少加一个 DuckDB round-trip 测试，覆盖 disabled/tradable=false/low liquidity/tags 不丢失。

6. 梳理 synthetic source contract。

   quote、FX、history fallback 都应带 `source`/`quality`，readiness 和 execution reference 不能把 synthetic 当作实盘可用数据。

7. 校准 README 与实现。

   把 insight alert bridge、detector 数量、scheduler job 清单、行情源主链路等容易误导 reviewer 的描述改成当前实现事实，避免后续方案继续基于漂移文档决策。

### P1：统一交易日驾驶舱

新增：

- `TradingDayWorkflowService`
- `GET /dashboard/today/data`
- `/dashboard/today`

第一版 cockpit 只做聚合：

- market phase：来自 `TradingSessionService`/`MarketCalendarService`
- decision：来自 execution gate、operations readiness、rollout policy、kill switch、compliance
- pre-market：briefing + plan + pending approvals
- intraday：active insights + recent orders + risk tick summary
- post-market：latest summary + deviations + unresolved insights

验收口径：

- 打开一个页面能回答“今天能否交易、哪个市场、为什么、下一步是什么”。
- cockpit API 不产生订单、不创建审批、不触发 reconcile。
- 页面上所有阻塞项都可追溯到原服务字段。

### P2：盘中和盘后升级

1. 盘中洞察矩阵。

   新增 `GET /dashboard/intraday/data`，把 insight 关联到 market、position、plan item、order、approval 和 risk rule。先用轮询实现，不急着上 WebSocket。

2. 盘后执行质量复盘。

   新增结构化 report：

   - planned item
   - linked order intent
   - broker order / manual fill
   - approval latency/status
   - filled/not filled/extra order
   - slippage/TCA
   - deviation reason
   - unresolved insight impact

   AI 可以生成 narrative，但不能生成结构化事实。

### P3：三市场真实交易基础

- 引入可靠交易所日历或维护可审计假日数据库，覆盖 US/HK/CN 假日、半日市、午休、DST。
- 扩展 Instrument 主数据：`exchange/sector/industry/data_source/quote_permission/st_status/limit_up/limit_down` 等。
- FX 分级：`realtime`、`recent_cached`、`stale_cached`、`synthetic`，并进入 readiness 和报表。
- 港股订单类型与 lot size 约束：增强限价、竞价、市价限制、真实 lot size，并让风险和下单路径实际使用 Instrument 主数据。
- A 股价格合法性：涨跌停、ST、T+1、退市/停牌标记要能阻断订单。
- 三市场边界测试：时区、货币、交易日、订单约束、半自动边界。

## 6. 需要优先回答的工程问题

1. `MarketStateService` 是接回还是删掉？当前半接入状态会持续制造测试和 UI 断链。
2. CN hard guard 放在 `ExecutionService` 还是 `FutuBrokerAdapter`？建议两层都做：service 层给清晰业务错误，adapter 层做最后防线。
3. `/dashboard/today` 是新页面还是改造首页？建议新页面先做，避免把当前 dashboard 首页继续膨胀。
4. Synthetic quote/FX 是否允许用于 manual order reference？建议默认允许演示/诊断，但在 UI、审计和 readiness 明确标红，不允许通过实盘门禁。
5. `self_iteration_weekly` 和 `acceptance_evidence_capture` 是否属于当前产品？如果不是，删 UI 和测试期望；如果是，需要有明确只读任务定义。

## 7. 验证备注

本次审查做了代码级核验，并尝试运行市场状态相关窄测试：

- `pytest tests/test_market_state.py -q` 使用系统解释器失败：缺少 `numpy`。
- `.venv/bin/pytest tests/test_market_state.py -q` 进入仓库虚拟环境后失败：`ImportError: cannot import name 'MarketStateSnapshot' from 'tradingcat.domain.models'`。
- 并行复核运行 `tests/test_market_state.py::test_market_state_routes_are_read_only_research_endpoints`，同样在收集阶段因缺 `MarketStateSnapshot` 失败。
- 并行复核运行 `tests/test_scheduler_runtime.py::test_scheduler_runtime_registers_expected_jobs`，失败点是实际注册 22 个 job、测试期望 24 个。

这与本报告判断一致：市场状态链路目前不是“已接入”，而是处于残留/半实现状态。运行该测试时 Futu SDK 还尝试初始化连接，后续修复应避免测试导入路径触发真实网关上下文。

## 8. 结论

Opus 方案不应废弃，但要降噪和校正事实。TradingCat 下一步不应继续堆策略或堆 AI，而应先完成：

1. 硬安全边界。
2. 前后端和测试契约断链修复。
3. 统一交易日驾驶舱。
4. 盘中影响矩阵和盘后执行对照。
5. 三市场真实交易基础。

完成这些之后，系统才会从”模块完整”变成”每日可用”。

---

## 9. Opus 对 Codex 第二版的 Review

> Reviewer: Opus (原始方案作者)
> Date: 2026-05-01

### 9.1 总体评价

Codex 第二版在事实校正和工程精确性上明显优于 Opus 第一版。Codex 做了代码级核验（包括实际运行测试），修正了多项不够精确的表述。方案主线和优先级可采纳。

**两版共识**：交易日闭环分散是最大瓶颈 → P0 先修安全和断链 → P1 建 cockpit → P2 升级盘中盘后 → P3 夯实三市场基础。

### 9.2 对 Codex 校正的逐条回应

#### ✅ 接受

| Codex 校正 | 回应 |
|-----------|------|
| Python 版本应为 `>=3.12`，非 `3.11+` | **接受**。`pyproject.toml` 确实写 `requires-python = “>=3.12”`。第一版写了 `3.11+` 是不准确的。 |
| `MarketStateService` 是”断链状态”而非”存在未接入” | **接受**。Codex 更精确：`static/market_state.js` 调用的 API 在 `static/api.js` 和后端路由中都不存在，测试引用不存在的 `MarketStateSnapshot` 模型。这是残留/半实现状态。 |
| Instrument 已有 `lot_size/tradable` 字段，问题是 DuckDB 不保真 | **接受**。第一版说”缺少字段”不够准确。代码中 `Instrument` 模型确实有这些字段，是 `DuckDbMarketDataStore` 只保存 5 个字段导致加载后丢失。 |
| 默认策略硬编码的表述需要精确化 | **接受**。`active_execution_strategy_ids()` 已经会优先读 allocations/selection，默认值只是 fallback。第一版说”缺少动态注册能力”过度简化。 |
| Polygon/CoinGecko 不是主行情源 | **接受**。它们只是附加源，主链路是 Futu/yfinance/CN adapters。 |
| 合成数据问题的精确表述 | **接受**。Codex 指出研究 promotion 已经会 block synthetic fallback，问题是 quote/FX 的来源标注和执行/复盘引用不够硬。比第一版的宽泛表述更准确。 |
| WebSocket 不应进 P0 | **接受**。轮询足够 cockpit v1，WebSocket 留到后续。 |

#### ⚠️ 部分接受/需要讨论

| Codex 校正 | 回应 |
|-----------|------|
| InsightEngine detector 数量”需要降级或核实” | **部分接受**。代码 `insight_detectors/` 目录下确有 4 个 detector（`correlation_break.py`, `flow_anomaly.py`, `news_driven.py`, `sector_divergence.py`）加 1 个辅助文件 `sector_map.py`。如果 README 写的是 3 类，那是 README 过期，不是第一版数字错误。第一版的 4 个是正确的。 |
| Scheduler 注册 22 个 job 而非”25+” | **接受方向，数字需确认**。`_JOB_REGISTRATIONS` 列表有 20 个 + `register_jobs()` 中额外注册 `intraday_risk_tick` + `intraday_insight_scan` = 22 个基础 job。若 `advisory_report.enabled=true` 则额外注册 `advisory_research_daily` = 23 个。第一版写”25+”是高估了。Codex 的实测 22 个是正确的（测试环境未开启 advisory）。 |

#### ❌ 不接受的校正

| Codex 校正 | 回应 |
|-----------|------|
| 无 | 所有校正均有合理依据。 |

### 9.3 Codex 遗漏但应纳入的内容

1. **测试策略**。P0-P3 实施路线没有提到测试策略。建议每个 Phase 都有对应的测试要求：
   - P0: CN guard 必须有不通过则 CI 失败的硬测试；DuckDB round-trip 测试；scheduler 注册表 snapshot 测试。
   - P1: Cockpit API 集成测试（验证 read-only 约束）。
   - P2: 执行对照报告的 fixture 测试。

2. **前端架构问题**。当前 `static/` 下是 vanilla JS 零构建系统，`api.js` 与其他 JS 文件之间缺乏明确的依赖管理。随着 cockpit 页面复杂度上升，前端可维护性会成为瓶颈。建议在 P1 中至少做一次前端 JS 模块整理（不一定要引入构建工具，但应理清 API 层、组件层、页面层的边界）。

3. **数据迁移策略**。Instrument 主数据扩展和 DuckDB schema 变更会影响已有持久化数据。P0-5 修复 DuckDB 保真时需要处理已有数据迁移（drop & re-sync 还是 schema migration）。

### 9.4 对 P0 优先级的微调建议

Codex 的 P0 有 7 项，建议细分为两级：

**P0-blocking（必须立即修）**:
1. CN live auto-order hard guard（安全红线）
2. Scheduler/UI/test 契约对齐（目前按钮 dead、测试失败）
3. `/journal/daily` + `/journal/markdown/latest` 补齐或前端清理
4. DuckDB instrument catalog 保真 + 数据迁移

**P0-nonblocking（本迭代修但不阻塞其他工作）**:
5. MarketStateService 接回（可以独立并行）
6. Synthetic source contract 标注（P3 前驱，但不必阻塞 P1 cockpit）
7. README 校准（文档债，不影响功能）

这样 P0-blocking 做完就可以开始 P1，不必等全部 7 项完成。

### 9.5 对 Codex 工程问题的回答

| Codex 问题 | Opus 建议 |
|-----------|----------|
| 1. MarketStateService 接回还是删掉？ | **接回**。该服务已有较完整的市场结构快照逻辑，可作为盘中 cockpit 的实时市场状态数据源。但明确它是只读研究服务，不进入执行链路。 |
| 2. CN hard guard 放哪层？ | **两层都做**。`ExecutionService.submit()` 层给清晰业务拒绝原因（”CN 市场自动下单被拦截”），`FutuBrokerAdapter.place_order()` 层做最后防线。测试覆盖：构造 `OrderIntent(market=CN, requires_approval=False)` 仍无法到达 `place_order()`。 |
| 3. `/dashboard/today` 新页面还是改造首页？ | **新页面**。当前 `dashboard.html` 已容纳过多功能，继续膨胀会恶化可维护性。新页面 `/dashboard/today` 独立路由和模板，共享 `api.js` 中的 API 方法但有自己的页面 JS。 |
| 4. Synthetic quote/FX 是否允许用于 manual order？ | **允许但标红**。演示/诊断场景需要。Rule: (1) UI 中标注”⚠️ 合成数据”黄色告警，(2) 审计日志记录 `source=synthetic`，(3) 实盘 readiness 检查中 synthetic 一律不通过。 |
| 5. self_iteration_weekly 是否保留？ | **删除**。当前无实现、无注册、无运行记录。从 UI (`dashboard_autonomous.js`)、测试期望 (`test_scheduler_runtime.py`) 和文档中一并移除。若未来需要自迭代，按新功能重新设计和测试。 |

### 9.6 总结

Codex 第二版是一份质量更高的方案，事实校正准确，代码核验充分（第 7 节的实际测试失败记录很有说服力）。Opus 第一版的主线可以继续使用，但具体事实应以 Codex 第二版为准。

建议以 Codex 第二版为实施基准，吸收上述 9.3（遗漏项）和 9.4（P0 分级）的建议后进入 P0 实施。
