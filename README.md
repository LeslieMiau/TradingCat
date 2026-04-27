# TradingCat

TradingCat 是一个面向港股、美股和 A 股的本地优先交易系统基线。本仓库实现了 [PLAN.md](/Users/miau/Documents/TradingCat/PLAN.md) 中描述的 V1 架构：Python 控制平面、明确的领域模型、策略生成、风控检查、审批流程、执行适配器，以及最小事件驱动回测引擎。

## 已实现内容

- 类型化领域层：`Instrument`、`Signal`、`OrderIntent`、`ExecutionReport`、`ApprovalRequest`、`PortfolioSnapshot`。
- 计划中的核心接口：`MarketDataAdapter`、`BrokerAdapter`、`Strategy`、`RiskEngine`、`ApprovalService`。
- 三个 V1 策略基线：
  - ETF 趋势/轮动。
  - 港美高流动性股票动量。
  - 期权覆盖层基线，默认仅用于研究，执行禁用。
- FastAPI 本地控制台，覆盖 dashboard、journal、signals、portfolio、orders、broker、market data、execution、alerts、compliance、ops、reports、approvals、kill switch、reconcile、scheduler、research 等接口。主要 HTTP 面包括：
  - `GET /dashboard`
  - `GET /dashboard/summary`
  - `GET /dashboard/research`
  - `GET /dashboard/operations`
  - `GET /dashboard/strategies/{strategy_id}`
  - `GET /journal/plans`
  - `GET /journal/plans/latest`
  - `POST /journal/plans/generate`
  - `GET /journal/summaries`
  - `GET /journal/summaries/latest`
  - `POST /journal/summaries/generate`
  - `GET /signals/today`
  - `GET /portfolio`
  - `GET /audit/logs`
  - `GET /audit/summary`
  - `POST /portfolio/risk-state`
  - `POST /portfolio/reconcile`
  - `GET /orders`
  - `POST /orders/{broker_order_id}/cancel`
  - `GET /broker/status`
  - `POST /broker/validate`
  - `GET /broker/probe`
  - `POST /broker/recover`
  - `POST /market-data/smoke-test`
  - `GET /data/instruments`
  - `POST /data/instruments`
  - `POST /data/history/sync`
  - `GET /data/history/bars`
  - `GET /data/history/coverage`
  - `GET /data/history/sync-runs`
  - `GET /data/history/sync-status`
  - `GET /data/history/repair-plan`
  - `POST /data/history/repair`
  - `GET /data/quality`
  - `GET /data/history/corporate-actions`
  - `POST /data/fx/sync`
  - `GET /data/fx/rates`
  - `POST /execution/preview`
  - `GET /execution/gate`
  - `POST /execution/run`
  - `POST /execution/reconcile`
  - `GET /execution/quality`
  - `GET /execution/authorization`
  - `GET /alerts`
  - `GET /alerts/summary`
  - `POST /alerts/evaluate`
  - `GET /compliance/checklists`
  - `GET /compliance/checklists/summary`
  - `POST /compliance/checklists/{checklist_id}/items/{item_id}`
  - `GET /ops/readiness`
  - `GET /ops/execution-metrics`
  - `GET /ops/daily-report`
  - `GET /ops/weekly-report`
  - `GET /ops/postmortem`
  - `GET /ops/incidents/replay`
  - `POST /ops/journal/record`
  - `GET /ops/journal`
  - `GET /ops/journal/summary`
  - `GET /ops/acceptance`
  - `GET /ops/acceptance/timeline`
  - `GET /ops/rollout`
  - `GET /ops/rollout/milestones`
  - `GET /ops/rollout-policy`
  - `GET /ops/go-live`
  - `GET /ops/live-acceptance`
  - `GET /ops/rollout/checklist`
  - `GET /ops/rollout/promotions`
  - `GET /ops/rollout/promotions/summary`
  - `POST /ops/rollout-policy`
  - `POST /ops/rollout-policy/apply-recommendation`
  - `POST /ops/rollout-policy/promote`
  - `GET /preflight/startup`
  - `GET /diagnostics/summary`
  - `GET /reports/latest`
  - `GET /reports/{report_ref}`
  - `GET /reports/latest/dashboard`
  - `GET /reports/{report_ref}/dashboard`
  - `GET /approvals`
  - `POST /approvals/{id}/approve`
  - `POST /approvals/{id}/expire`
  - `POST /approvals/{id}/reject`
  - `POST /approvals/expire-stale`
  - `GET /kill-switch`
  - `POST /kill-switch`
  - `POST /kill-switch/verify`
  - `POST /reconcile/manual-fill`
  - `POST /reconcile/manual-fills/import`
  - `GET /market-sessions`
  - `GET /scheduler/jobs`
  - `POST /scheduler/jobs/{id}/run`
  - `POST /orders/cancel-open`
  - `POST /research/backtests/run`
  - `GET /research/backtests`
  - `GET /research/backtests/compare`
  - `POST /research/report/run`
  - `POST /research/stability/run`
  - `POST /research/scorecard/run`
  - `POST /research/candidates/scorecard`
  - `GET /research/strategies/{strategy_id}`
  - `POST /research/recommendations/run`
  - `POST /research/ideas/run`
  - `POST /research/news/summarize`
  - `POST /research/selections/review`
  - `GET /research/selections`
  - `GET /research/selections/summary`
  - `POST /research/allocations/review`
  - `GET /research/allocations`
  - `GET /research/allocations/summary`
  - `POST /portfolio/rebalance-plan`
- 模拟券商和手工执行适配器，符合 V1 中“港美自动执行、A 股人工确认”的分层。
- 审批流程支持显式过期和定时清理过期请求，适用于人工确认的 A 股建议单。
- 审计日志记录核心控制平面变更，支持本地 JSON 或本地 PostgreSQL。
- 最小事件驱动回测基线，包含换手率、市场别成本、滑点、汇率和公司行为处理。
- `data/` 下的本地 JSON 持久化，覆盖审批、订单、组合状态和回测实验。
- 市场时段服务和 APScheduler 本地后台任务，带启动/关闭生命周期。
- Futu 适配器工厂可选启用；当 `futu` SDK 或 OpenD 不可用时，自动降级到模拟适配器。
- 券商、行情、诊断、预检、执行门禁、运行就绪度、验收、分阶段上线和实盘验收等运维视图都已接入 dashboard。
- 研究面已包含 walk-forward 验证、策略相关性、稳定性分桶、推荐动作、候选策略评分、研究想法、资讯摘要、策略筛选和 allocation review。
- 策略 C 已能产出最小保护性看跌/备兑看涨研究信号；实盘执行仍限定股票和 ETF 腿。
- 执行状态支持重复成交去重、券商订单对账、券商持仓与本地快照核对、订单状态机和执行质量汇总。
- 风控引擎除权重和现金约束外，也执行单日期权权利金预算和组合期权总风险预算。
- Kill switch、合规清单、告警、恢复动作、验收证据、阶段升档历史和 rollout policy 都已持久化并进入控制台。
- 测试覆盖风险规则、审批流、回测成本、调度历史、dashboard facade、operations journal 和研究 runner 等关键路径。

## 股票池维护

持久化研究股票池位于 `data/instruments.json`，启用 DuckDB 时也可落地到 DuckDB。股票池通过 API 管理，不再依赖硬编码策略样本。

典型流程：

```bash
curl -X POST http://127.0.0.1:8000/data/instruments \
  -H 'Content-Type: application/json' \
  -d '{
    "instruments": [
      {
        "symbol": "IVV",
        "market": "US",
        "asset_class": "etf",
        "currency": "USD",
        "name": "iShares Core S&P 500 ETF",
        "enabled": true,
        "tradable": true,
        "liquidity_bucket": "high",
        "avg_daily_dollar_volume_m": 6200
      }
    ]
  }'
curl "http://127.0.0.1:8000/data/instruments?enabled_only=true&tradable_only=true&liquid_only=true"
```

操作说明：

- 只有真正希望进入研究/执行候选池的标的，才保持 `enabled=true` 和 `tradable=true`。
- 如果要保留标的但排除出默认个人交易池，可设置 `liquidity_bucket=low` 或 `enabled=false`。
- 修改股票池后，针对受影响标的运行 `POST /data/history/sync`，再用 `GET /data/history/coverage` 检查覆盖率。

## 洞察引擎 (InsightEngine v1)

把持仓 / 关注列表 / 市场感知 / 资金流和资讯观察压缩成可追溯的少量洞察,而不是又一个 K 线 / 排行榜面板。每条洞察必须能回答三个问题:**是什么 / 为什么我应该看 / 什么时候再看一眼**。

三类 detector(全部 EOD 跑批,不依赖盘中行情):

- `correlation_break` — 标的与 benchmark 的 30 日滚动相关性 ≥ 0.5,但当日返回差值 z-score ≥ 2.0
- `sector_divergence` — 同板块成员 ≥ 2,板块当日 ≥ 2%,标的位于板块内极端百分位且 60 日 beta ≥ 0.7
- `flow_anomaly` — 整市场北向 / 南向资金 5 日净流的 z-score ≥ 2.5,subjects 限定为该市场的持仓 / 关注 (v1 简化:per-sector / per-stock 留给付费数据源 v2)

输出:`/dashboard/insights` 的洞察 feed。每条卡片显示 severity + headline + subjects + 置信度 + triggered_at,展开看完整因果链(每段证据带 source / fact / value / observed_at)。提供 dismiss / acknowledge,持久化在 InsightStore(DuckDB 启用时落库,否则内存)。

板块映射:默认覆盖项目 sample_instruments 池;可放 `data/sector_map.json` 覆盖/扩展(`{"symbol_to_sector": {...}, "sector_benchmarks": {...}}`)。

EventBus 桥接:`InsightAlertBridge` 订阅 `EventType.INSIGHT`,把 urgent 洞察 record 到 `AlertService`,在已有的 `/alerts` 面板可见,无需主动打开洞察 tab。

### 主要 HTTP 接口

- `GET /insights` — list(支持 `?include_dismissed=true`、`?kind=correlation_break|sector_divergence|flow_anomaly`)
- `GET /insights/{id}` — 详情
- `POST /insights/{id}/dismiss` — 否决,可附 reason
- `POST /insights/{id}/ack` — 已读,可附 note
- `POST /insights/run` — 手动触发引擎(仅刷新洞察,不触发交易/审批/对账)

### 历史回放与精确率验证

`scripts/insight_replay.py` 在指定日期范围内逐日跑 detector,产出 jsonl,每行一个 candidate,带 `manual_judgement` 空字段供人工标注:

```bash
PYTHONPATH=. .venv/bin/python scripts/insight_replay.py \
    --start 2025-10-01 --end 2025-12-31 \
    --output data/reports/insight_replay/2025q4.jsonl
```

跑完后人工抽 50 条,把 `manual_judgement` 填 `true / false / edge`,据此评估精确率(目标 ≥ 70%)和假阳性密度(目标 ≤ 3 条/天)。引擎在 `dry_run=True` 模式下跑,不污染线上 store / 不发事件。

## 已吸收的研究能力

仓库包含从 `hsliuping/TradingAgents-CN` 第 01-15 轮吸收而来的研究层能力：A 股数据适配器（AKShare / BaoStock / Tushare）、中文资讯源（东方财富 / 财联社 / Finnhub / Alpha Vantage）、中国市场硬风控规则（涨跌停 / T+1 / ST）、技术特征、股票池筛选器，以及带预算门禁的 LLM 研究建议层。

除中国市场硬风控规则外，这些能力默认全部关闭，并且仅作为研究建议使用；它们不会生成 `Signal`、`OrderIntent`、审批或执行指令。操作手册见 [docs/ABSORB_CAPABILITIES.md](/Users/miau/Documents/TradingCat/docs/ABSORB_CAPABILITIES.md)。

离线冒烟运行：

```bash
.venv/bin/python scripts/absorb_dogfood.py
# 审计环境开关，然后用 fake LLM 运行离线端到端流程，
# 并把 Markdown 报告写到 data/reports/dogfood/
```

## 当前架构边界

- `tradingcat/routes/` 保持薄路由。路由处理器应委托给 `app.py` 属性、facade 或专用 service，不在路由内拼装研究/报表逻辑。
- `tradingcat/facades.py` 负责面向传输层的读模型。Dashboard 和 research facade 应从 query/projection/reporting service 组装响应，不直接进入重型编排代码。
- `tradingcat/services/query_services.py` 负责 readiness、数据质量、research query 等读侧聚合。
- `tradingcat/services/portfolio_projections.py` 负责账户持仓、现金、净值曲线和 allocation projection 等 dashboard 共用计算。
- `tradingcat/services/strategy_reporting.py` 负责研究报告、稳定性、推荐、scorecard 和策略详情组装。`StrategyAnalysisService` 保持为实验、相关性、benchmark 和历史数据辅助的底层分析核心。
- `tradingcat/strategies/simple.py` 放生产策略实现和共享元数据/辅助方法；研究候选策略放在 `tradingcat/strategies/research_candidates.py`。
- `sample_instruments()` 仅用于回退或诊断路径；持久化 instrument catalog 是研究和策略详情流程的默认事实来源。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
./scripts/bootstrap_env.sh disabled
./scripts/run_local.sh
```

然后打开：

```bash
http://127.0.0.1:8000/dashboard
```

当前 GUI 原型重点展示：

- 总资产、现金、持仓 allocation 和组合盈亏。
- 年化收益、Sharpe、最大回撤等策略指标。
- 来自 execution preview 的今日交易计划。
- 日报/周报摘要和当前阻塞项。

## 当前架构地图

- `tradingcat/main.py` 保持为薄 FastAPI 入口，负责注册 router 和错误处理。
- 运行时构建、broker/data recovery 位于 `tradingcat/runtime.py`；APScheduler 任务注册位于 `tradingcat/scheduler_runtime.py`。
- `tradingcat/app.py` 仍是主应用外壳，但 dashboard / research / operations / journal / alerts 编排已通过 `tradingcat/facades.py` 中的 facade 对象承接。
- 服务端渲染页面复用 `templates/base.html` 和 `templates/partials/` 下的 Jinja 布局片段，不再从 route handler 返回原始 HTML 字符串。
- Dashboard 前端保持无框架，但页面逻辑已按关注点拆分：
  - `static/dashboard_accounts.js`：账户 tab、概览和账户资产辅助逻辑。
  - `static/dashboard_strategy.js`：策略、候选和交易计划渲染。
  - `static/dashboard_operations.js`：摘要、阻塞项、优先动作和实时运维表格。
  - `static/dashboard.js`：编排外壳，持有共享状态和 API 加载。

## 后续接手

- 如果继续重构工作，先读 `PLAN.json` 和 `PROGRESS.md`；它们是 harness 状态、剩余任务和既有决策的权威来源。
- 重构内部实现时保持当前 HTTP 公共面不变；路由兼容性和 dashboard 响应兼容性由 `tests/test_api.py` 保护。
- 本仓库本地验证优先使用 `.venv/bin/pytest`；系统解释器可能因可选数据依赖缺失而产生假阴性。

准备后续 Futu 集成：

```bash
source .venv/bin/activate
pip install -e .[dev,futu]
```

把本地状态迁移到同机 PostgreSQL：

```bash
source .venv/bin/activate
pip install -e .
./scripts/bootstrap_env.sh simulate
# 编辑 .env：
# TRADINGCAT_POSTGRES_ENABLED=true
# TRADINGCAT_POSTGRES_DSN=postgresql:///tradingcat
./scripts/init_postgres.sh
```

把研究实验持久化到本地 DuckDB + Parquet：

```bash
# 编辑 .env：
# TRADINGCAT_DUCKDB_ENABLED=true
# TRADINGCAT_DUCKDB_PATH=data/research.duckdb
# TRADINGCAT_PARQUET_DIR=data/parquet
# TRADINGCAT_SCHEDULER_BACKEND=apscheduler
# TRADINGCAT_SCHEDULER_AUTOSTART=true
```

## 本地验证流程

```bash
./scripts/bootstrap_env.sh simulate
# OpenD 启动后，编辑 .env 并设置 TRADINGCAT_FUTU_ENABLED=true
# 只有环境支持文件监听时才设置 TRADINGCAT_RELOAD=true
./scripts/run_local.sh
```

另一个终端：

```bash
./scripts/checklist.sh
./scripts/opend_check.sh
./scripts/doctor.sh
./scripts/validate_broker.sh
./scripts/validate_all.sh
./scripts/post_validate.sh
./scripts/simulated_order_cycle.sh
```

注意：`post_validate.sh`、`simulated_order_cycle.sh`、带 `with-cycle` 的验证和任何会触发执行、撤单、审批、手工对账的流程都有真实副作用边界；只在明确需要该流程时运行。

归档验证运行到 `data/reports/<timestamp>/`：

```bash
TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/doctor.sh
TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/validate_broker.sh
TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/validate_all.sh
```

一条命令串联完整流程：

```bash
./scripts/opend_check.sh
./scripts/validate_all.sh
./scripts/validate_all.sh http://127.0.0.1:8000 with-cycle
./scripts/post_validate.sh
```

`./scripts/post_validate.sh` 会运行完整本地操作员闭环：

- validation summary。
- broker order smoke check。
- 取消当前打开的模拟/实盘订单。
- 执行一次 live cycle。
- 自动批准最新待处理 A 股请求。
- 对账一条 manual fill。
- 把完整结果归档到 `data/reports/<timestamp>/`。

查看归档运行：

```bash
./scripts/latest_report.sh
./scripts/compare_reports.sh 20260307-173723 20260307-173727
./scripts/report_markdown.sh latest
./scripts/cleanup_reports.sh 10
curl http://127.0.0.1:8000/reports/latest
curl http://127.0.0.1:8000/reports/latest/dashboard
```

`./scripts/validate_broker.sh` 会先调用 `GET /diagnostics/summary`，汇总最可能的失败类别：

- `futu_disabled`：`.env` 仍处于 simulated mode。
- `sdk_missing`：`.venv` 中未安装 `futu` 包。
- `opend_unreachable`：quote 和 trade 验证都失败，通常是 OpenD 未运行或未登录。
- `quote_channel_failed`：行情连接或行情权限失败。
- `trade_channel_failed`：交易连接、解锁或账户环境失败。
- `market_data_mapping_failed`：连接存在，但 quote/bar 解析失败。
- `risk_or_preview_failed`：执行前的策略或风控 preview 失败。
- `ready_for_validation`：只读检查已通过，下一步是模拟下单/撤单验证。

`./scripts/doctor.sh` 会打印紧凑摘要，并使用以下退出码：

- `0`：`info`
- `1`：`warning`
- `2`：`error`

## 说明

- 这是基线实现，不是生产级交易引擎。
- Futu OpenD 仍是外部依赖；本地 PostgreSQL、DuckDB/Parquet 和 APScheduler 已通过配置接入。
- V1 中 A 股执行按设计保持人工确认。
- 运行时状态和审计日志可迁移到本地 PostgreSQL；研究实验可迁移到本地 DuckDB + Parquet。
- Futu 集成当前是带回退能力的适配器层；真实交易仍依赖本地 OpenD 可用性、账户权限，以及对 live SDK 响应字段的最终验证。
- `AppConfig` 支持环境驱动启动，包括 `TRADINGCAT_FUTU_*`、本地 PostgreSQL、DuckDB/Parquet 和 scheduler backend 设置。
