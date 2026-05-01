# TradingCat 个人量化交易平台 —— 全面审查与改进方案

> **审查日期**: 2026-05-01
> **审查范围**: 全代码库（Python 后端 / 前端模板与静态资源 / 配置与调度）
> **目标**: 从"自动交易系统"升级为"三市场量化交易工作台"

---

## 1. 目标定义

TradingCat 的最终形态应支持一个交易者完成完整的每日交易闭环：

| 阶段 | 核心需求 |
|------|---------|
| **盘前** | 市场状态判断 → 是否交易决策 → 交易计划 → 风险边界 → 待审批项 → 观察清单 |
| **盘中** | 实时/准实时盯盘 → 洞察关联持仓/订单 → 风险告警 → 订单管理 |
| **盘后** | 计划执行对照 → 成交质量分析 → 偏差原因 → 洞察处理 → 参数调整 → 明日准备 |

支持市场：**A股（半自动）/ 港股 / 美股**，三市场并行。

---

## 2. 当前架构总览

### 2.1 技术栈
- **后端**: Python 3.11+ / FastAPI / Pydantic / APScheduler
- **数据**: DuckDB (研究/回测) + 本地 JSON/Parquet (运行时状态)
- **交易网关**: Futu OpenD (主券商，港美自动 / A股半自动)
- **行情源**: yfinance + AKShare + TuShare + BaoStock + Polygon + CoinGecko
- **通知**: Telegram / Email / SMTP
- **AI**: DeepSeek / OpenAI-compatible（仅研究/解释/复盘，不下单）
- **前端**: Jinja2 模板 + vanilla JS + ECharts

### 2.2 模块清单

```
tradingcat/
├── adapters/          # 行情/券商/新闻/LLM 适配器
│   ├── cn/            # AKShare, TuShare, BaoStock (A股行情)
│   ├── llm/           # OpenAI-compatible LLM
│   ├── news/          # CLS, EastMoney, Finnhub, AlphaVantage, HkRss, TuShare
│   └── sentiment_sources/  # CNN Fear&Greed, CN market flows
├── api/               # API 响应模型
├── repositories/      # 数据持久化层（JSON 为主）
├── routes/            # FastAPI 路由（~20 个模块）
├── services/          # 核心业务逻辑（~60 个服务文件）
│   └── insight_detectors/  # 关联断裂/资金流向异常/新闻驱动/板块背离
├── domain/            # 领域模型
├── strategies/        # 策略实现
└── backtest/          # 回测引擎
```

### 2.3 现有能力清单

| 能力域 | 已有能力 | 成熟度 |
|--------|---------|--------|
| 市场感知 | MarketAwarenessService (趋势/广度/动量/回撤/波动率多维评分) | 🟢 高 |
| 市场情绪 | MarketSentimentService (VIX/VXN/CNN F&G/CN flows/HK VHSI) | 🟢 高 |
| 盘中洞察 | InsightEngine (4个检测器 + 事件总线) | 🟡 中 |
| 信号生成 | 3个策略 (ETF轮动/动量选股/期权对冲) + 回测 | 🟢 高 |
| 风险控制 | RiskEngine (多级阈值 + kill switch + 盘中巡检) | 🟢 高 |
| 订单执行 | ExecutionService + 审批流 + 算法下单 | 🟢 高 |
| 盘前简报 | DailyLogService.run_briefing() → 市场感知 + AI简报 | 🟡 中 |
| 交易计划 | generate_daily_trading_plan() → 信号预览 + 门禁检查 | 🟡 中 |
| 盘后复盘 | DailyLogService.run_review() → 计划vs实际 + AI日志 | 🔴 低 |
| 数据同步 | 历史行情同步 + 缺口修复 + 覆盖审计 | 🟢 高 |
| 运营报告 | 运营日报/周期报告/事后分析/事件回放 | 🟢 高 |
| 交易流水 | TradeLedger + 对账 | 🟢 高 |
| 前端控制台 | Dashboard + Journal + Insights + Research + Operations | 🟡 中 |
| 调度系统 | APScheduler (25+ 定时任务，覆盖三市场盘前/盘中/盘后) | 🟢 高 |

---

## 3. 不合理之处（需修正）

### 3.1 🔴 交易日闭环断裂

**问题**: 交易者的每日工作流被分散在至少 6 个不同的页面/模块中：

- Dashboard 首页 → 组合/信号/风险状态
- Dashboard Briefing → 盘前简报
- Dashboard Review → 盘后复盘
- Dashboard Insights → 盘中洞察列表
- Journal 页面 → 计划归档
- Operations 页面 → 执行动态/运营指标

**后果**: 交易者需要手动在多个页面间跳转拼凑信息：
- 「今天能不能交易？」→ 需要查看 briefing + plan + execution gate
- 「哪个市场能交易？」→ 需要查看 market awareness + calendar
- 「盘中发生了什么？」→ 需要同时看 insights + orders + risk
- 「今天表现如何？」→ 需要看 review + execution analysis + operations

**根因**: 缺少一个统一的 `TradingDayCockpit` 聚合层。

### 3.2 🔴 盘前简报和交易计划是两套独立链路

**问题**: 
- `run_briefing()` (daily_log.py:121) 负责市场感知 + AI 简报
- `generate_daily_trading_plan()` (app.py:736) 负责信号预览 + 交易计划
- 两者没有组合成"盘前作业包"，各跑各的

**应该是**: 盘前一次性输出市场状态 + 是否交易 + 可交易市场 + 关键风险 + 计划订单 + 待审批项 + 阻塞原因 + 观察清单 + 触发价位/条件。

### 3.3 🔴 MarketStateService 存在但未接入系统

**证据**:
- `tradingcat/services/market_state.py` 存在且实现完整
- `static/market_state.js` 存在，引用 API 端点
- 但 `tradingcat/routes/` 中没有任何路由接入 `MarketStateService`
- `app.py` 中未创建 `MarketStateService` 实例
- 前端 JS 请求的 API 端点不存在

**这是高优先级的前后端断链**。

### 3.4 🔴 盘后复盘过于浅层

`_compare_plan_to_actual()` (daily_log.py:224) 仅比较：
```python
# 计划意图数 vs 实际订单数
if plan_intents > 0 and summary_orders < plan_intents:
    deviations.append("計劃 N 條訂單意圖，實際僅 M 條訂單")
if plan.status == "blocked":
    deviations.append("今日計劃因執行門禁阻塞")
```

**缺少**:
- 每条计划的逐笔执行状态
- 对应订单和成交详情
- 滑点 / 交易成本分析 (TCA)
- 未执行原因归因
- 审批延迟统计
- 撤单原因记录
- 是否违反盘前计划的方向/仓位
- 盘中洞察是否得到处理
- 明日参数调整建议

### 3.5 🟡 合成数据被当作真实数据使用

**问题**:
- `MarketDataService` 支持 `fallback_to_synthetic=True`
- FX 汇率可能回退到 synthetic series
- 合成行情/汇率在就绪检查中被标记为正常

**后果**: 测试/诊断功能可能混淆真实交易就绪判断。合成数据应明确标注并在实盘 readiness 中降级。

### 3.6 🟡 策略信号默认硬编码

`app.py:374` 硬编码了三个默认策略 ID：
```python
_default_execution_strategy_ids = [
    "strategy_a_etf_rotation",
    "strategy_b_equity_momentum",
    "strategy_c_option_overlay",
]
```

这些策略的实现在 `strategies/simple.py` 和 `strategies/fallbacks.py` 中，但缺少通过配置动态注册的能力。

### 3.7 🟡 DuckDB instrument catalog 字段保真问题

`InstrumentCatalogRepository` 在写入 DuckDB 时可能丢失 `enabled` / `tradable` / `liquidity_bucket` / `tags` 等筛选关键字段，导致 universe screener 和 research 查询结果不准确。

---

## 4. 需要改进之处

### 4.1 📋 标的主数据 (Instrument) 不够完整

当前 `Instrument` 模型缺少以下三市场交易必需字段：

| 缺失字段 | 影响 | 市场 |
|---------|------|------|
| 交易所 (exchange) | 无法区分 SSE/SZSE/SEHK/NYSE/NASDAQ | CN/HK/US |
| 板块/行业 (sector/industry) | 板块背离检测缺少输入 | ALL |
| 港股每手股数 (lot_size) | 港股不能统一按 100 股处理 | HK |
| 行情数据源 (data_source) | 无法追踪行情来源可信度 | ALL |
| 可交易状态 (tradable) | 区分可交易 vs 仅观察标的 | ALL |
| 行情权限状态 (quote_permission) | Futu 用户等级影响行情订阅数 | ALL |
| A股 ST/退市/涨跌停状态 | A股风险阻断 | CN |
| 涨跌停价格约束 | A股订单价格合法性校验 | CN |

### 4.2 📋 市场日历过于简化

当前 `MarketCalendarService` 的问题：

| 缺陷 | 影响 |
|------|------|
| US/HK 仅按工作日处理 | 忽略交易所假日（如 Memorial Day, 佛诞日） |
| HK/CN 午休缺失 | 盘中调度可能在休市期间错误触发 |
| US 半日市未建模 | 半日市（如 Black Friday）错误判断收盘时间 |
| 夏令时细节不足 | 美股盘前/盘后时间随 DST 变化 |
| CN 假日硬编码且仅 2026 | 到 2027 年即失效，标注 approximate |

需要引入可靠的市场日历数据源（如 exchange_calendars Python 库或 TradingHours API）。

### 4.3 📋 汇率数据可信度不足

- FX 有模型 (domain/fx.py) 和持久化 (repositories)，但真实覆盖率弱
- 服务层可能回退到 synthetic FX series
- 需要：
  - 明确标注 FX 来源（realtime / cached / synthetic）
  - Synthetic FX 不通过实盘 readiness 检查
  - 引入至少一个可靠的 FX 数据源（如 yfinance FX pair 或 freeforexapi）

### 4.4 📋 盘中洞察不是真正的实时系统

当前 `intraday_insight_scan` 每 300 秒运行一次，但：

- 没有接入实时/准实时 quote（依赖缓存价格）
- 没有监测持仓实时变化
- 没有关联今日计划状态
- 没有监测盘中市场结构突变（如 VIX 飙升、涨跌停潮、北向资金异动）
- 没有按持仓/订单/计划项关联洞察影响

### 4.5 📋 前端信息架构

当前首页混合了过多信息，缺少"今日决策条"。

Dashboard 首页应展示：
- **当前市场阶段**: 盘前 / 开盘 / 盘中 / 收盘 / 盘后 / 休市
- **今日决策状态**: 可交易 / 阻塞 / 只观察 / 只减仓
- **关键阻塞项** 和 **下一步动作**
- **最大风险** 提示

洞察页应升级为「洞察影响矩阵」：每条洞察 → 影响哪个市场/持仓/计划项/订单。

---

## 5. 需要增加的功能

### 5.1 P0 — 🛡️ 安全与断链修复

| 编号 | 项目 | 说明 |
|------|------|------|
| P0-1 | **A股硬半自动边界** | 在 broker adapter 或 execution policy 层增加不可绕过的 CN live-order guard。即使代码路径绕过了 `RiskEngine.requires_approval=True`，adapter 层也必须拦截 CN 市场的自动下单。 |
| P0-2 | **MarketStateService 全链路接入** | 在 `app.py` 中创建实例 → 在 `routes/` 中增加 API 端点 → 前端 `market_state.js` 连接生效 |
| P0-3 | **修補前後端斷鏈** | 核查 `/journal/daily`、`/journal/markdown/latest` 等前端 JS 引用但后端缺失的 API |
| P0-4 | **核查 self_iteration_weekly** | 确认该定时任务是否应注册或移除 |
| P0-5 | **DuckDB instrument catalog 字段保真** | 修复写入 DuckDB 时丢失 `enabled/tradable/liquidity_bucket/tags` 字段的问题 |

### 5.2 P1 — 🖥️ 统一交易日驾驶舱 (Trading Day Cockpit)

新增 `GET /dashboard/today/data` 和 `/dashboard/today` 页面，聚合：

```
┌─────────────────────────────────────────────────┐
│ 📊 今日交易驾驶舱          2026-05-01 (周四)    │
├─────────────────────────────────────────────────┤
│ 🇨🇳 A股: 休市 │ 🇭🇰 港股: 盘中 │ 🇺🇸 美股: 盘前 │
├─────────────────────────────────────────────────┤
│ 决策状态: ✅ 可交易                              │
│ 阻塞项: 无                                       │
│ 今日最大风险: 美股科技板块集中度偏高              │
├─────────────────────────────────────────────────┤
│ 计划订单: 3 条 │ 待审批: 1 条 │ 活跃洞察: 5 条   │
│ 持仓数: 12     │ 今日已成交: 2 笔                │
├─────────────────────────────────────────────────┤
│ 下一步: 审批 AAPL 加仓 → 关注 NVDA 盘中突破     │
└─────────────────────────────────────────────────┘
```

数据来源聚合：
- `TradingSessionService` → 各市场当前阶段
- `MarketAwarenessService` → 市场状态与参与判断
- `generate_daily_trading_plan()` → 今日计划
- `approvals.list_pending()` → 待审批
- `portfolio.current_snapshot()` → 当前持仓
- `insight_store.list(include_dismissed=False)` → 活跃洞察
- `execution.list_orders()` → 最近订单
- `execution_gate_summary()` → 执行门禁
- `DailyLogService` → 盘后总结

### 5.3 P1 — 🧠 盘前决策包 (Pre-Market Decision Package)

将 `run_briefing()` + `generate_daily_trading_plan()` 统一为一个盘前决策包：

```json
{
  "as_of": "2026-05-01",
  "markets": {
    "CN": {"phase": "closed", "status": "no_trade", "reason": "法定假日"},
    "HK": {"phase": "pre_market", "status": "ready", "trading": true},
    "US": {"phase": "sleep", "status": "pending", "opens_at": "21:30 CST"}
  },
  "decision": {
    "can_trade": true,
    "tradable_markets": ["HK"],
    "overall_regime": "cautious",
    "risk_posture": "hold_pace",
    "participation": {"decision": "selective", "probability": 0.62, "odds": 1.8}
  },
  "plan": {
    "intent_count": 3,
    "signal_count": 5,
    "manual_count": 1,
    "items": [...]
  },
  "risks": {
    "top_risk": "港股地产板块波动加剧",
    "blockers": [],
    "pending_approvals": 1
  },
  "watchlist": [...],
  "conditional_alerts": [...]
}
```

### 5.4 P2 — 📡 盘中洞察矩阵 (Intraday Insight Matrix)

新增 `GET /dashboard/intraday/data`，输出持仓级洞察矩阵：

```
          持仓 AAPL  持仓 NVDA  持仓 TLT  计划 ORDER-1  计划 ORDER-2
洞察 #1     ⚠️ 高     -        -        ⚠️ 中         -
洞察 #2     -         🔴 高    -        -            🔴 高
洞察 #3     -         -        🟡 低    -            -
```

同时：
- `intraday_insight_scan` 同时记录 market-state timeline
- 每次扫描记录风险 tick + 订单变化 + 紧急洞察
- 盘中市场结构突变自动触发告警

### 5.5 P2 — 📋 执行质量复盘 (Execution Quality Review)

扩展盘后复盘内容：

```json
{
  "plan_vs_actual": {
    "intended": 3,
    "executed": 2,
    "not_executed": [{"reason": "审批过期", "intent_id": "..."}],
    "extra_orders": []
  },
  "execution_quality": {
    "slippage_bps": 3.2,
    "tca_summary": "平均滑点 3.2bps，优于 5bps 阈值",
    "fill_rate": 0.95,
    "avg_time_to_fill_seconds": 12
  },
  "deviations": [...],
  "insight_resolution": {
    "total": 5, "resolved": 3, "dismissed": 1, "unresolved": 1
  },
  "parameter_adjustments": [
    {"param": "max_single_stock_weight", "current": 0.08, "suggested": 0.06, "reason": "..."}
  ]
}
```

### 5.6 P3 — 🏗️ 三市场真实交易基础建设

| 编号 | 项目 | 说明 |
|------|------|------|
| P3-1 | **可靠市场日历** | 引入 exchange_calendars 库或维护三市场假日数据库 |
| P3-2 | **分级 FX 数据** | realtime → cached (<5min) → cached (>5min) → synthetic，标注可信度 |
| P3-3 | **Instrument 主数据扩展** | 补充 4.1 节列出的所有缺失字段 |
| P3-4 | **港股订单类型** | 支持增强限价单、竞价市价单等港股特有订单类型 |
| P3-5 | **A股价格约束** | 涨跌停价自动校验，超限拦截 |
| P3-6 | **US 盘前/盘后交易** | 支持 RTH 和 extended hours 区分 |
| P3-7 | **三市场边界测试** | 跨市场交易日历、时区、币种转换的集成测试 |

### 5.7 P3 — 🔄 交易日工作流服务 (TradingDayWorkflowService)

新增核心编排服务，职责：
- 只做 read-model 聚合和流程编排
- **不直接下单**，不修改风险/审批/组合状态
- 为 dashboard / daily-log / scheduler status 提供统一数据源

```python
class TradingDayWorkflowService:
    def today_snapshot(as_of: date) -> TradingDaySnapshot:
        """一次性获取今日全部关键状态"""

    def pre_market_package(as_of: date) -> PreMarketPackage:
        """盘前决策包：市场状态 + 决策 + 计划 + 风险 + 观察清单"""

    def intraday_matrix(as_of: date) -> IntradayMatrix:
        """盘中洞察 x 持仓/订单 影响矩阵"""

    def post_market_report(as_of: date) -> PostMarketReport:
        """盘后复盘：执行对照 + 成交质量 + 偏差 + 参数调整建议"""
```

---

## 6. 目标架构

```
                         ┌─────────────────────────┐
                         │   TradingDayWorkflow    │
                         │       Service           │
                         │  (read-model 聚合编排)   │
                         └───────────┬─────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
   ┌──────▼──────┐           ┌──────▼──────┐           ┌──────▼──────┐
   │  盘前决策包   │           │  盘中洞察矩阵 │           │  盘后复盘报告 │
   │ PreMarket   │           │  Intraday   │           │ PostMarket  │
   │  Package    │           │   Matrix    │           │   Report    │
   └─────────────┘           └─────────────┘           └─────────────┘
          │                          │                          │
          └──────────────────────────┼──────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
              ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
              │ Dashboard │   │ Daily Log │   │ Scheduler │
              │  /today   │   │  Service  │   │  Status   │
              └───────────┘   └───────────┘   └───────────┘
```

现有服务层不变，`TradingDayWorkflowService` 仅在它们之上做聚合。

---

## 7. 实施路线图

### Phase 0: 安全补丁（预计 2-3 天）
- [ ] P0-1: CN 市场硬拦截 guard（adapter 层）
- [ ] P0-2: MarketStateService 全链路接入
- [ ] P0-3: 修复前后端 API 断链
- [ ] P0-4: 核查清理 self_iteration_weekly
- [ ] P0-5: DuckDB instrument catalog 字段保真

### Phase 1: 交易日驾驶舱（预计 3-5 天）
- [ ] 实现 `TradingDayWorkflowService` 基础骨架
- [ ] 实现 `GET /dashboard/today/data` API
- [ ] 实现 `/dashboard/today` 前端页面（含日内市场阶段可视化）
- [ ] 实现 **盘前决策包** 聚合逻辑
- [ ] 端到端连通：market phase → awareness → plan → approvals → positions

### Phase 2: 盘中与复盘升级（预计 4-6 天）
- [ ] 实现 `GET /dashboard/intraday/data`（持仓×洞察矩阵）
- [ ] `intraday_insight_scan` 增加 market-state timeline + risk tick + order change 记录
- [ ] 实现每日执行对照报告（计划→订单→成交→滑点→审批→偏差→结论）
- [ ] AI 保留为解释层，结构化字段由本地服务计算生成

### Phase 3: 三市场真实交易基础（预计 5-8 天）
- [ ] 引入可靠市场日历（exchange_calendars 或自建假日数据库）
- [ ] FX 分级标注（realtime / cached / synthetic）
- [ ] Instrument 主数据扩展（exchange, sector, lot_size, tradable, ST status）
- [ ] 港股订单类型扩展
- [ ] A股价格约束自动校验
- [ ] 三市场边界集成测试

---

## 8. 供 Codex 审核的关键判断

请 Codex 重点审核以下判断是否成立：

1. **当前最大瓶颈** 是否是"交易日闭环分散"，而非策略数量或 AI 能力不足？
2. **A股半自动边界** 是否需在 adapter 层而非仅 RiskEngine 层做硬拦截？
3. **MarketStateService** 是否应作为盘中 cockpit 的核心服务接回？
4. **合成数据（行情/FX）** 是否应从实盘 readiness 检查中严格降级？
5. **Phase 0-3 优先级划分** 是否合理？有没有遗漏的 P0 项？
6. **TradingDayWorkflowService** 的设计是否合理？是否存在过度抽象？
7. 是否需要引入 **WebSocket** 做实时推送，还是继续用轮询足够？
8. 三市场并行调度（不同时区 cron）的可靠性是否充分？

---

## 9. 结论

TradingCat 的底座方向正确：
- ✅ 本地优先、三市场、多策略
- ✅ 风控门禁、人工审批、kill switch
- ✅ AI 只做研究辅助不下单
- ✅ 完整的回测→模拟→实盘上线管线

但要成为真正可日常使用的个人量化交易平台，核心升级路径是：

> **从"模块集合"升级为"交易者工作流产品"**

最重要的下一步不是增加策略数量，而是：
1. 🛡️ 补齐安全红线（P0）
2. 🖥️ 构建统一交易日驾驶舱（P1）
3. 📡 升级盘中洞察和盘后复盘深度（P2）
4. 🏗️ 夯实三市场真实交易基础设施（P3）
