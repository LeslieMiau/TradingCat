# TradingCat ANALYSIS.md Validation Review

生成日期：2026-04-29

验证对象：`.claude/worktrees/brave-archimedes-d72b1d/ANALYSIS.md`

范围：本 review 逐项验证 `ANALYSIS.md` 对 TradingCat 当前功能的删减、合并和数据库精简建议。结论基于当前主工作区代码静态阅读，没有执行交易、审批、撤单、对账或其他有副作用流程。

代码量说明：下文代码量是 `wc -l` 级别估算，按主要实现、路由、模板、前端和直接测试覆盖粗略合计。它用于判断影响面，不等同于精确可删除行数。

## Executive Opinion

我同意 `ANALYSIS.md` 的总体方向：TradingCat 已经从个人自动化交易系统扩展出偏机构级的 rollout、ops、acceptance、审计和研究自动化面，维护成本开始高于个人系统收益。

但我不同意 `ANALYSIS.md` 的两个 P0 删除建议的执行方式：

1. `rollout system` 不能直接砍，因为它已经进入执行门禁。可以大幅简化，但必须先替换 `execution_gate_summary()` 里的 rollout readiness 依赖。
2. `approval workflow` 不能直接砍，因为它不是纯 UI。它负责 A 股/人工单的 manual broker 分流、授权状态和 approved submit 链路。可以简化成确认/授权层，但不能删除核心状态。

建议的实际路线：

1. 先做兼容性收口：保留公共 API alias，内部合并服务。
2. 再做行为替换：用 `execution_mode`、`max_allocation_ratio`、`manual_confirmation_required` 替代 rollout/promotion/checklist 大系统。
3. 最后删冗余：删除 PG、ML runtime、自迭代 job、多余 dashboard 子页和部分新闻源。

## Findings

### 1. Rollout System

`ANALYSIS.md` 结论：重度过度设计，建议 P0 砍掉。

Reviewer stance：needs-discussion。

主要代码：

- `tradingcat/services/rollout.py`：99 行
- `tradingcat/services/acceptance_gates.py`：600 行
- `tradingcat/services/operations.py`：361 行，其中 rollout/acceptance/journal 混在一起
- `tradingcat/routes/ops.py`：160 行，包含 rollout、policy、promotions、go-live、acceptance evidence 等 endpoint
- `templates/operations.html`：283 行
- `static/operations.js`：403 行
- `static/dashboard_operations.js`：173 行
- 直接测试：`tests/test_rollout_policy.py`、`tests/test_rollout_promotion.py`、`tests/test_acceptance_gates.py`、`tests/test_operations_journal.py`，约 782 行

代码量估算：8-12 个核心文件，约 2,200-3,000 行。

实际影响：

- rollout 不只是展示面。`TradingCatApplication._build_operations_rollout()` 使用 readiness、compliance、alerts、acceptance gate 组合出 rollout 状态。
- `ReadinessQueryService.execution_gate_summary()` 会读取 `operations_rollout()`。当 rollout 未 ready 时，会把 blockers 加入 gate reasons，并使 `ready=false`。
- `POST /execution/run` 的 `enforce_gate=true` 会根据该 gate 阻塞执行。
- scheduler 默认调用 `run_execution_cycle(..., enforce_gate=False)`，因此当前定时执行不被 rollout 强阻塞；但人工触发或未来打开 gate 时会受影响。

删除后是否影响核心交易流水线：直接删除会影响。尤其是 `execution_gate_summary()`、go-live summary、dashboard summary 和 ops readiness 都要替换依赖。

建议：

- 不保留 promotion attempts、milestones、acceptance evidence timeline、go-live 大屏。
- 保留一个更小的 `ExecutionModePolicy`：
  - `mode`: `paper` / `manual_live` / `live`
  - `max_allocation_ratio`: `0.0-1.0`
  - `manual_confirmation_required`: bool
  - `reason`, `updated_at`
- `execution_gate_summary()` 改为依赖这个 policy，而不是 rollout readiness。
- `/ops/rollout*` endpoint 保留一版兼容 alias，返回 deprecated payload，后续前端迁移后删除。

### 2. Approval Workflow

`ANALYSIS.md` 结论：单人自我审批无意义，建议 P0 砍掉。

Reviewer stance：disagree。

主要代码：

- `tradingcat/services/approval.py`：76 行
- `tradingcat/routes/approvals.py`：71 行
- `tradingcat/services/execution.py`：371 行，其中 approval 与 submit/authorization/reconciliation 强耦合
- `tradingcat/services/order_state_machine.py`：61 行
- 多个 dashboard/research/account 页面读取 pending/recent approvals
- 相关测试分布在 `tests/test_api.py`、`tests/test_execution_reconciliation.py`、`tests/test_dashboard_facade.py` 等

代码量估算：10-15 个文件，约 800-1,400 行实际影响面。

实际影响：

- `ExecutionService.submit()` 在 `intent.requires_approval` 时创建 `ApprovalRequest`，登记 authorization 为 `manual_pending`。
- 同一方法根据 `requires_approval` 选择 `manual_broker.place_order(intent)` 或 `live_broker.place_order(intent)`。
- `/approvals/{request_id}/approve` 调用 `app.execution.submit_approved(request_id)`，这是批准后的提交路径。
- `authorization_summary()` 把 approval 状态纳入执行授权检查；ops readiness 会把 pending approval 当作 blocker。
- README 和 PLAN 明确 A 股半自动执行、人工确认链路是 V1 范围。

删除后是否影响核心交易流水线：会。直接删除会破坏 A 股半自动流程、人工单授权状态、执行 readiness、审计追踪和多处 UI。

建议：

- 不要删除核心 workflow。
- 可以把“审批”改名为更贴近单人系统的 `ManualConfirmationService`。
- 简化状态：`pending` / `confirmed` / `cancelled` / `expired` 足够。
- 删除 60 分钟自动过期作为强业务规则，改成 UI 提醒或 configurable TTL。
- 前端可以从“审批队列”降级成“待确认订单”。

### 3. Operations Console

`ANALYSIS.md` 结论：SRE 级运营面板过度设计，30+ endpoints 大多不会用。

Reviewer stance：agree with simplification, not full deletion。

主要代码：

- `tradingcat/routes/ops.py`：约 30 个 route decorator，其中 rollout/acceptance/go-live 占很大比例
- `tradingcat/services/operations.py`：readiness journal、acceptance、rollout milestones、recovery summary
- `tradingcat/services/operations_analytics.py`：execution metrics、TCA、incident period insights
- `templates/operations.html`、`static/operations.js`、`static/dashboard_operations.js`

代码量估算：6-10 个文件，约 1,000-1,600 行。

实际影响：

- UI 本身不影响下单。
- 但 operations readiness、execution metrics、authorization blockers 被 dashboard 和 execution gate 间接使用。
- `operations_execution_metrics()` 聚合 audit、execution quality、TCA、authorization，属于可保留的执行质量 read model。

删除后是否影响核心交易流水线：删除 ops 页面影响小；删除 readiness/analytics 服务会影响 gate、dashboard 和验证报告。

建议：

- 保留 `System / Settings` 页面，只展示：
  - broker/data health
  - kill switch
  - pending confirmations
  - execution quality/TCA
  - scheduler status
- 删除或隐藏：
  - incident replay
  - postmortem
  - rollout promotion
  - acceptance evidence timeline
  - go-live summary
- 把 `/ops/execution-metrics`、`/ops/tca` 合并到 `ExecutionAnalysisService`。

### 4. Compliance Checklists

`ANALYSIS.md` 结论：个人账户不需要 checklist。

Reviewer stance：needs-discussion。

主要代码：

- `tradingcat/services/compliance.py`：94 行
- `tradingcat/routes/compliance.py`：31 行
- `tests/test_compliance.py`：20 行
- operations/rollout/readiness 中读取 compliance summary

代码量估算：4-6 个文件，约 150-250 行直接代码。

实际影响：

- checklist 本身不下单。
- 它会影响 rollout summary：blocked checklist 会成为 rollout blocker。
- PLAN 中把 A 股合规检查清单列为 Phase 0 内容；README 也把合规清单作为已实现控制面。

删除后是否影响核心交易流水线：如果先移除 rollout gate 依赖，则影响小；当前直接删除会影响 readiness/rollout 展示和测试。

建议：

- 不保留交互式 checklist。
- 改成静态 `Risk/Compliance Notes` 或 preflight warning。
- A 股半自动约束应放进 `RiskEngine` / `ExecutionPolicy`，而不是靠 checklist 状态控制。

### 5. Audit Log UI

`ANALYSIS.md` 结论：完整 audit 浏览功能过度；个人只需 CSV 导出 + 简单操作日志。

Reviewer stance：agree for UI, disagree for service deletion。

主要代码：

- `tradingcat/services/audit.py`：206 行
- `tradingcat/routes/audit.py`：19 行
- `tests/test_audit.py`：102 行
- `tradingcat/repositories/postgres_store.py`：125 行中包含 audit table 支持

代码量估算：4-6 个文件，约 250-450 行直接影响面。

实际影响：

- audit service 被 execution preview/run、manual fill、live reconcile、approval approve/reject/expire、risk config、kill switch 等路径写入。
- audit execution metrics 被 operations analytics 和 TCA summary 使用。

删除后是否影响核心交易流水线：删除 UI 不影响；删除 `AuditService` 会影响执行和对账可追溯性，也会破坏 operations metrics。

建议：

- 删除独立 audit browser 页面/复杂 endpoint。
- 保留 `AuditService.log()` 和最小查询。
- 增加 CSV/JSONL export，比完整 UI 更适合个人系统。
- 如果删除 PostgreSQL，audit 可落 DuckDB 或 JSONL。

### 6. ML Pipeline

`ANALYSIS.md` 结论：个人资金和样本量通常不支撑 ML 模型，建议删除。

Reviewer stance：agree。

主要代码：

- `tradingcat/services/ml_pipeline.py`：242 行
- runtime 构造 `MLPipeline(models_dir=config.data_dir / "models")`
- `TradingCatApplication.ml_pipeline` property 暴露 runtime 对象

代码量估算：2-4 个文件，约 250-350 行。

实际影响：

- 没看到 ML pipeline 接入 strategy signal generation、risk check、execution preview 或 routes。
- 目前更像未接线的实验能力，runtime 每次构造反而增加依赖面和启动复杂度。

删除后是否影响核心交易流水线：基本不影响。

建议：

- 从 runtime 移除 `MLPipeline`。
- 如需保留，移到 `tradingcat/research/experimental/` 或脚本层，不进入应用生命周期。
- 不要让 ML 输出进入默认执行候选池。

### 7. Self-Iteration Service

2026-05-01 决策：`self_iteration_weekly` 不属于当前产品面，已从 scheduler 期望、dashboard 按钮和测试契约中移除。未来如需自迭代能力，按新功能重新设计，不保留空按钮或假 job。

删除后是否影响核心交易流水线：不影响。

建议：

- 删除 scheduled job 和 dashboard 按钮。
- 若保留，改成离线 report script，由 trader 手动运行。
- 不要让 tuning hints 自动改 detector 或 strategy 参数。

### 8. LLM Budget Tracking + Cache

`ANALYSIS.md` 结论：DeepSeek 便宜，无需企业级 budget/cache。

Reviewer stance：needs-discussion。

主要代码：

- `tradingcat/services/llm_budget.py`：150 行
- `tradingcat/services/llm_cache.py`：54 行
- `tradingcat/adapters/llm/openai_compatible.py`：75 行
- `tradingcat/adapters/llm/base.py`：31 行
- `tradingcat/adapters/llm/fake.py`：40 行
- `tests/test_llm_budget.py`：144 行
- `tests/test_llm_cache_batch_research.py`：65 行

代码量估算：7-10 个文件，约 550-800 行。

实际影响：

- 不影响核心交易执行。
- 影响 advisory research / analyst layer。
- 当前 `AIResearcher` 仍有 prompt 要求输出买卖建议、entry、target、stop，和 PLAN 的“AI 只做研究辅助不参与下单决策”存在张力。

删除后是否影响核心交易流水线：不影响。

建议：

- 保留一个轻量 token/cost guard，避免误配置导致循环调用。
- 删除独立 cache 服务，或把 cache 内聚到 LLM provider。
- 重点不是省钱，而是安全边界：统一改成 research-only prompt，不输出买卖/仓位/止损指令。

## Merge Candidates

### 1. Pre-Market Briefing + Post-Market Review + Trading Journal -> Daily Log

`ANALYSIS.md` 结论：同一工作流三阶段，应合并。

Reviewer stance：agree。

主要代码：

- `tradingcat/services/trading_journal.py`：58 行
- `tradingcat/services/post_market_reflection.py`：134 行
- `tradingcat/services/pre_market_orchestrator.py`：115 行
- `tradingcat/routes/journal.py`：40 行
- `tradingcat/routes/dashboard.py` 中 briefing/review 页面和 data endpoints
- `templates/journal.html`、`templates/briefing.html`、`templates/review.html`
- `static/journal.js`、`static/dashboard_briefing.js`

代码量估算：8-10 个文件，约 1,200-1,400 行。

合并策略：

- 新建 `DailyLogService`，统一模型：
  - `as_of`
  - `market`
  - `phase`: `pre_market` / `intraday` / `post_market`
  - `plan`
  - `summary`
  - `market_awareness`
  - `insights`
  - `ai_note`
  - `deviations`
- 页面合并为 `/dashboard/daily-log`，用 tabs/timeline 区分阶段。
- API 保留兼容：
  - `/journal/plans*`
  - `/journal/summaries*`
  - `/dashboard/briefing/data`
  - `/dashboard/review/data`
  这些 endpoint 内部转发到 `DailyLogService`。

接口兼容性影响：中等。前端页面可迁移，HTTP 公共面建议至少保留一个版本。

风险点：

- pre-market 有交易时段 phase check，非盘前会 skip；post-market 没有同样的强 skip。
- post-market 会调用 `summary_factory=self.generate_daily_trading_summary`，合并时不要重复生成 summary。
- AI note 必须保持 research-only，不得变成执行建议。

### 2. Insight Engine + AlertService + AI Researcher -> Analysis Pipeline

`ANALYSIS.md` 结论：detector -> insight -> alert_bridge -> ai_recommendation 应合并。

Reviewer stance：needs-discussion。

主要代码：

- `tradingcat/services/insight_engine.py`：334 行
- `tradingcat/services/insight_alert_bridge.py`：65 行
- `tradingcat/services/alerts.py`：172 行
- `tradingcat/services/ai_researcher.py`：342 行
- `tradingcat/routes/insights.py`：134 行
- `tradingcat/routes/alerts.py`：23 行
- insights templates/static：约 483 行

代码量估算：8-10 个文件，约 1,400-1,700 行。

合并策略：

- 不建议把 AlertService 完全吞进 InsightEngine；alert 还服务 broker/data/reconcile 风险。
- 建议新建 `AnalysisPipelineService`：
  - `run_detectors()`
  - `classify_severity()`
  - `record_insight()`
  - `emit_alert_if_actionable()`
  - `explain_research_only()`
- `AlertService` 保留为系统告警 sink。
- EventBus 可以保留，但 insight -> alert 的路径可从隐式 bridge 改成 pipeline 内显式调用，减少调试难度。

接口兼容性影响：中等。`/insights` 和 `/alerts` 面向不同使用场景，建议保留。

风险点：

- `AIResearcher.analyze_insight_trading_action()` 当前会输出 action/entry/target/stop，这不符合安全边界；合并前应删除或改为 explanation。
- urgent insight 进入 alert 是有价值的，但非 urgent insight 不应该污染系统告警。

### 3. MarketAwareness + PreMarketOrchestrator + AI Briefing -> Pre-Market Pipeline

`ANALYSIS.md` 结论：AI briefing 本质是 awareness data 的总结，应合并。

Reviewer stance：agree。

主要代码：

- `tradingcat/services/market_awareness.py`：1,515 行
- `tradingcat/services/market_sentiment.py`：1,041 行
- `tradingcat/services/news_observation.py`：287 行
- `tradingcat/services/pre_market_orchestrator.py`：115 行
- `tradingcat/services/ai_researcher.py`：342 行
- market awareness tests 约 1,195 行

代码量估算：5 个核心服务 + 测试，约 4,000-4,500 行。

合并策略：

- `MarketAwarenessService` 体量大，不建议简单合并成一个巨类。
- 建议保留 awareness 作为底层 read model，新建 `PreMarketPipelineService` 取代 `PreMarketOrchestrator`：
  - session phase validation
  - awareness snapshot
  - overnight insight scan
  - optional AI summary
  - persisted daily log entry
- dashboard briefing data 直接读 Daily Log / PreMarketPipeline result。

接口兼容性影响：低到中。`/dashboard/briefing/data` 可保持 payload 结构。

风险点：

- 多市场 phase/日历不能简化成单一 CN 逻辑。
- AI briefing 当前 prompt 要求 “REQUIRED trading recommendations”，需要改为 research-only observations。

### 4. TCA + Execution Quality + Operations Analytics -> ExecutionAnalysisService

`ANALYSIS.md` 结论：应合并。

Reviewer stance：agree。

主要代码：

- `tradingcat/services/reconciliation.py`：339 行
- `tradingcat/services/execution.py`：371 行
- `tradingcat/services/operations_analytics.py`：187 行
- `tradingcat/routes/execution.py`：62 行
- `tradingcat/routes/ops.py`：160 行
- `tests/test_execution_reconciliation.py`：419 行

代码量估算：5-7 个文件，约 1,300-1,600 行。

合并策略：

- 新建 `ExecutionAnalysisService`：
  - `quality_summary()`
  - `tca_summary()`
  - `authorization_summary()`
  - `readiness_blockers()`
- `ExecutionService` 只保留 submit/cancel/reconcile/state。
- `/execution/quality`、`/execution/authorization`、`/ops/tca`、`/ops/execution-metrics` 继续保留 alias，但内部调用同一 service。

接口兼容性影响：低。主要是内部重构。

风险点：

- TCA 样本依赖 expected prices 和 fill reports，迁移时必须保持字段一致。
- readiness blockers 是 gate 的输入，不能只做展示逻辑。

### 5. News Adapters 精简

`ANALYSIS.md` 结论：6 个新闻 adapter 可能过多，应砍到 2-3 个。

Reviewer stance：agree, but measure first。

主要代码：

- `tradingcat/adapters/news/alpha_vantage.py`
- `tradingcat/adapters/news/cls.py`
- `tradingcat/adapters/news/eastmoney.py`
- `tradingcat/adapters/news/finnhub.py`
- `tradingcat/adapters/news/hkrss.py`
- `tradingcat/adapters/news/tushare_news.py`
- `tradingcat/services/news_observation.py`
- `tradingcat/services/news_filter.py`
- 加上 sentiment source adapters，相关代码约 2,200 行

合并策略：

- 先加 source health/usage 统计，观察 2-4 周。
- 默认保留：
  - EastMoney/CLS：A 股中文资讯
  - Finnhub/Alpha Vantage 二选一：美股资讯
  - HKRSS：如港股持仓确实活跃再保留
- 所有 adapter 统一 `NewsProvider` 协议，配置禁用未使用源。

接口兼容性影响：低。主要影响 data freshness 和 coverage。

风险点：

- 砍源会影响 insight/news-driven detector 的召回。
- 免费 API 的 rate limit 和稳定性差异需要实际运行数据支撑。

### 6. Strategy Count 精简

`ANALYSIS.md` 结论：个人资金通常只够跑 2-3 个策略。

Reviewer stance：agree with production scope, not deleting research candidates immediately。

主要代码：

- `tradingcat/strategies/simple.py`：419 行
- `tradingcat/strategies/research_candidates.py`：362 行
- `tests/test_research_candidate_technical_features.py`：75 行
- `tests/test_research_reporting.py`：873 行

代码量估算：3-5 个文件，约 1,000-1,700 行影响面。

合并策略：

- 保留 `simple.py` 中的 production V1 策略。
- `research_candidates.py` 保留为 disabled-by-default research pool，不能进入默认 execution strategy ids。
- 对 dashboard 展示做分组：Production / Research / Disabled。

接口兼容性影响：低到中。研究页面可能需要隐藏或折叠候选策略。

风险点：

- 删除候选策略会减少回测/报告测试覆盖。
- 更好的做法是控制执行入口，而不是马上删代码。

### 7. 三个数据库后端 -> DuckDB + JSON

`ANALYSIS.md` 结论：去掉 PostgreSQL。

Reviewer stance：agree。

当前依赖：

- `tradingcat/repositories/state.py` 的 `_build_store()` 在 `config.postgres.enabled` 时把所有状态 bucket 交给 `PostgresStore`。
- 状态 bucket 包括 approvals、orders、alerts、compliance、operations_journal、daily plans/summaries、recovery_attempts、strategy selections/allocations、history sync/audit、scheduler runs、trade ledger reconciliation、portfolio history、portfolio、rollout policy、execution_state、audit_events。
- `tradingcat/repositories/research.py` 中 `BacktestExperimentRepository` 支持 DuckDB 优先，其次 PostgreSQL，再 JSON。
- `scripts/init_postgres.sh`、README setup、preflight diagnostics、`tests/test_postgres_store.py` 都依赖 PG。

代码量估算：

- PG 直接实现和测试：约 245 行
- state/research/config/preflight/docs/scripts 间接影响：约 500-900 行
- DuckDB 相关现有 repository：market data、insights、sentiment、market state、research 已存在，约 1,300 行

迁移工作量：中等。

建议迁移路径：

1. 新建 `DuckDbStateStore`，实现与 `PostgresStore` 相同接口：
   - `load(bucket, default)`
   - `save(bucket, payload)`
   - `append_audit(bucket, action, payload)`
   - `list_audit(bucket=None, limit=100)`
2. `state.py` 的 `_build_store()` 增加 `config.duckdb.enabled` 分支，用 DuckDB 承接 runtime state。
3. 保持 JSON fallback。
4. 删除 `PostgresConfig`、`PostgresStore`、`scripts/init_postgres.sh`、`psycopg` 依赖和 README PG setup。
5. 提供一次性迁移脚本：PG buckets -> DuckDB `state_buckets` / `audit_log`。

删除后是否影响核心交易流水线：如果先实现 DuckDB state store，则不影响；直接删除 PG 分支不会影响默认 JSON 模式，但会破坏已启用 PG 的本地环境和 tests。

### 8. Dashboard 7+ 子页面 -> 4 页

`ANALYSIS.md` 结论：合并为 Overview / Daily Log / Research / Settings-System。

Reviewer stance：agree。

当前页面：

- dashboard overview
- accounts
- strategy
- research
- operations
- insights
- briefing
- review
- journal
- market state 等近期新增页面

合并策略：

- Overview：账户、风险、pending confirmation、urgent insight、今日计划摘要。
- Daily Log：briefing、intraday notes、post-market review、journal。
- Research：backtest、strategy report、market awareness、insight details。
- Settings/System：broker、data health、scheduler、kill switch、manual policy。

接口兼容性影响：主要是前端路由和 sidebar；后端 API 可以保留。

风险点：

- Dashboard 当前无框架，静态 JS 分散。合并页面前应先建立 shared render helpers，避免更大 JS 文件。

## Priority Reassessment

### 原 P0：砍 rollout system

Reviewer opinion：修改为 P0a “替换 gate 依赖并简化”，不是直接删除。

推荐步骤：

1. 加 `ExecutionPolicyService`。
2. `execution_gate_summary()` 改读 policy，不读 rollout readiness。
3. operations 页面只显示 policy 当前状态。
4. 删除 rollout promotions/milestones/go-live/evidence timeline。

### 原 P0：砍 approval workflow

Reviewer opinion：disagree。

推荐步骤：

1. 保留核心 confirmation workflow。
2. 改名和简化模型。
3. 删除过度审批 UI 和 expiry sweep 的强业务含义。
4. 保留 A 股/manual broker 分流和 authorization summary。

### 原 P1：合并 Daily Log

Reviewer opinion：agree。

推荐步骤：

1. 新增 `DailyLogService` 和统一 model。
2. 后端 endpoint alias 兼容旧前端。
3. 前端合并 briefing/review/journal 页面。

### 原 P1：合并 Analysis Pipeline

Reviewer opinion：agree with narrower design。

推荐步骤：

1. Insight detection 和 alert sink 之间改显式 pipeline。
2. `AIResearcher` 删除交易建议 prompt。
3. 保留 `/alerts` 作为系统告警，不和 `/insights` 完全合并。

### 原 P1：砍 PostgreSQL

Reviewer opinion：agree。

推荐步骤：

1. 先实现 DuckDB state store。
2. 再删 PG config/scripts/dependency/docs。
3. 更新 preflight 和 tests。

### 原 P2：新闻源、策略、dashboard 精简

Reviewer opinion：agree。

推荐步骤：

1. 新闻源先统计，再删。
2. 策略先限制 production set，再考虑删 research code。
3. dashboard 先收口导航，再合并 JS。

## Concrete Code Recommendations

1. 新增 `tradingcat/services/execution_policy.py`，替代 rollout policy 的执行门禁职责。
2. 将 `TradingCatApplication.execution_gate_summary()` 的 rollout dependency 替换成 execution policy dependency。
3. 将 `ApprovalService` 重命名或包装成 `ManualConfirmationService`，但保留 `ApprovalRepository` 兼容迁移。
4. 删除 `AIResearcher.analyze_insight_trading_action()`，或改成 `explain_insight_evidence()` 风格，不输出 action/entry/target/stop。
5. 从 runtime 移除 `MLPipeline` 构造，避免应用启动默认加载实验 ML 依赖。
6. 保持 `self_iteration_weekly` 从 scheduler、dashboard 和测试契约中移除。
7. 新建 `ExecutionAnalysisService`，让 `/execution/quality`、`/execution/authorization`、`/ops/tca`、`/ops/execution-metrics` 共享同一 read model。
8. 新建 `DailyLogService`，把 trading plan、daily summary、pre-market briefing、post-market reflection 收到同一聚合。
9. 新建 `DuckDbStateStore` 后移除 PostgreSQL 分支。
10. Dashboard sidebar 收口为 4 个主要入口，旧页面以 redirect/alias 过渡。

## Verification Notes

本次只做静态验证和文档记录，没有运行 pytest。原因是没有代码行为变更，且本 review 不需要触发任何交易、审批、撤单或对账流程。

如果后续按本文建议实际改代码，最小验证建议：

```bash
.venv/bin/pytest tests/test_api.py tests/test_execution_reconciliation.py tests/test_dashboard_facade.py
.venv/bin/pytest tests/test_rollout_policy.py tests/test_rollout_promotion.py tests/test_acceptance_gates.py
.venv/bin/pytest tests/test_llm_budget.py tests/test_llm_cache_batch_research.py
```

涉及 PostgreSQL -> DuckDB 迁移时，再增加：

```bash
.venv/bin/pytest tests/test_postgres_store.py tests/test_research_duckdb.py tests/test_duckdb_sentiment_store.py tests/test_market_state.py
```
