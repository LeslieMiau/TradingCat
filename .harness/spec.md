# TradingCat Market Awareness And Trend-Aware Guidance

## 愿景
给 TradingCat 增加一个独立的市场感知层：先用市场走势与结构证据判断当前市场处于什么状态，再把这个状态翻译成操作建议，最后把建议接入研究页、dashboard 摘要和日内计划上下文。结果必须对操作者有用，但保持 advisory-only，不得偷偷替代审批、风控或下单链路。

## 功能列表
1. **市场状态快照** — 输出整体市场 posture，以及 US / HK / CN 的分市场视角。
   - 验收：`/research/market-awareness` 返回整体状态、分市场状态、置信度和数据质量字段。
2. **走势证据解释** — 用趋势、动量、回撤、波动、breadth、跨资产确认等证据解释判断。
   - 验收：响应中包含结构化 evidence 列表，而不是只有一句结论。
3. **操作建议生成** — 把市场状态翻译成“加风险 / 控节奏 / 降风险 / 等待确认”等动作建议。
   - 验收：响应中包含按优先级排序的 action 列表，并明确理由。
4. **策略级 guidance** — 对 Strategy A / B / C 分别给出姿态建议。
   - 验收：响应中包含每个策略的 guidance，不需要用户自行从总述里推断。
5. **Dashboard 可见性** — 在研究页和 dashboard summary 中展示 market-awareness 结果。
   - 验收：研究页能直接看到 posture 卡片、证据列表和 action 面板。
6. **降级与安全回退** — 数据缺失、Futu 限频、行情权限不足时仍返回保守建议与 blocker 说明。
   - 验收：接口返回 degraded payload，不抛 500，不因为 live adapter 问题把整个研究页拖死。

## 技术栈
- 后端：现有 `FastAPI` + `Pydantic` + `tradingcat/services/*`
- 数据：现有 market-history、本地 instruments、macro-calendar、alpha-radar
- 前端：现有 dashboard/research 页面 JS 和 summary payload
- 运行约束：本地优先、safe mode 优先、禁止新增实盘副作用

## 架构
- 新增一个独立的 `MarketAwarenessService`，负责：
  - 读取 benchmark 历史、breadth universe、市场日历、宏观事件、可选 alpha-radar overlay
  - 生成 per-market posture、overall posture、evidence、actions、strategy guidance、data-quality
- 通过 query/facade 层暴露能力：
  - `ResearchQueryService.market_awareness(as_of)`
  - `GET /research/market-awareness`
  - `POST /research/market-awareness/run`
- dashboard 集成原则：
  - `DashboardQueryService.summary_context()` 中嵌入一个 market-awareness snapshot
  - 研究页直接消费嵌入数据或同路径 API，不在 route 层拼业务
- Daily plan 集成原则：
  - 将 overall posture 和 top actions 注入计划上下文，但不直接修改 intent / weight / approval

## 公共接口约定
- 新接口：
  - `GET /research/market-awareness`
  - `POST /research/market-awareness/run`
- 顶层响应字段固定为：
  - `as_of`
  - `overall_regime`
  - `confidence`
  - `risk_posture`
  - `overall_score`
  - `market_views`
  - `evidence`
  - `actions`
  - `strategy_guidance`
  - `data_quality`
- dashboard summary 新增：
  - `details.market_awareness`

## 固定 benchmark basket
- US posture basket：
  - 主基准：`SPY`
  - 趋势/领导确认：`QQQ`、`VTI`
- HK posture basket：
  - 主基准：`0700`
  - 领导确认：`9988`
- CN posture basket：
  - 主基准：`510300`
  - 趋势/成长确认：`159915`
- Cross-asset defensive references：
  - `TLT`、`IEF`、`GLD`、`GSG`
- Breadth universe source order：
  - 先读持久化 instrument catalog 中 `enabled + tradable` 的标的
  - 再按市场过滤到 US / HK / CN 各自的 breadth universe
  - 只有当持久化 universe 为空时才退回 `sample_instruments()`
- 这套 basket 在本轮 harness 中视为固定契约；后续实现只能消费它，不能在 service/UI 层隐式换篮子

## 固定 regime taxonomy
- `bullish`
  - 中长期趋势向上、动量支持、breadth 过线、无明显波动/回撤压力
- `neutral`
  - 证据偏混合，方向存在但确认不足，适合维持节奏而非扩大风险
- `caution`
  - 趋势或 breadth 开始恶化，或波动/回撤压力抬头，需要控制节奏并提高确认门槛
- `risk_off`
  - 长趋势破坏、breadth 明显转弱，且伴随回撤/波动压力，需要以防守和暂停新增风险为先
- 置信度标签固定为：
  - `high`：3 个以上独立证据方向一致，且数据完整
  - `medium`：主方向明确，但仍有 1-2 个冲突证据
  - `low`：证据显著冲突，或数据降级/回退路径影响判断

## 固定 action tier 与优先级
- 顶层 `risk_posture` 固定映射为：
  - `build_risk`
  - `hold_pace`
  - `reduce_risk`
  - `pause_new_adds`
- 冲突折叠规则固定为：
  - 先看 overall regime，再看单市场里最差的 regime，再看波动/回撤硬压力
  - 多个建议冲突时，总是保留更防守的 tier 作为顶层 posture
  - 其余建议以下钻 `actions[]` 形式保留，但顺序必须按严重度从高到低
- deterministic mapping：
  - `bullish + medium/high confidence` -> `build_risk`
  - `neutral` -> `hold_pace`
  - `caution` -> 至少 `hold_pace`，若伴随 drawdown/volatility 压力则升级为 `reduce_risk`
  - `risk_off` 或 `low-confidence caution + degraded data` -> `pause_new_adds`

## 评估标准
- **功能性**：是否真的能把市场走势转换成可执行的操作建议，而不是只返回指标快照。
- **解释性**：每个 posture/action 是否都有清晰证据支撑。
- **稳健性**：缺数据、限频、权限不足时是否还能稳定返回保守结论。
- **集成质量**：API、dashboard、计划上下文是否一致，不出现一处 bullish 一处 risk-off 的分裂状态。

## 约束
- 不新增任何自动下单、自动审批、副作用执行。
- 优先使用本地历史和持久化 universe；live 数据只能是补充，不是硬依赖。
- route 保持薄，业务拼装放在 service/query/facade 层。
- 必须先恢复当前基线失败，再推进新功能交付。
