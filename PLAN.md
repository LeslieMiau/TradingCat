# TradingCat V1 自动交易系统实施计划

## Summary
- 目标改写为：建立一个能持续验证正期望、把回撤控制在可承受范围内，并可分阶段上线的个人自动交易系统；不把“必赚”当成系统承诺。
- V1 范围固定为：`Python 优先`、`本地运行`、`富途/Moomoo 为主券商`、`港股/美股自动执行`、`A 股半自动执行`、`仅美股期权做对冲/备兑`、`AI 只做研究辅助不参与下单决策`。
- 资金与风险约束固定为：`10万-100万人民币`、`不上杠杆`、组合目标 `年化 15%-25%`、`最大回撤 < 15%`。
- 上线门槛固定为：任何策略必须先通过回测、再通过模拟交易、最后按 `10% -> 30% -> 100%` 资金分阶段实盘。

## Key Changes
- 建一个统一交易内核，拆成 `Data`、`Research/Backtest`、`Risk`、`Execution`、`Control Panel` 五层。
- 技术栈固定为：`Python 3.12`、`FastAPI` 本地控制台、`PostgreSQL` 存运行状态与审计日志、`Parquet + DuckDB` 存历史行情与回测数据、`APScheduler` 做定时任务、`Futu OpenD` 做实盘/模拟网关。
- 核心接口固定为：
  - `MarketDataAdapter`: `fetch_bars`, `fetch_quotes`, `fetch_option_chain`, `fetch_corporate_actions`
  - `BrokerAdapter`: `place_order`, `cancel_order`, `get_orders`, `get_positions`, `get_cash`, `reconcile_fills`
  - `Strategy`: `generate_signals(date) -> Signal[]`
  - `RiskEngine`: `check(signal_set) -> ApprovedOrderIntent[]`
  - `ApprovalService`: `create_request`, `approve`, `reject`, `expire`
- 核心类型固定为：`Instrument`、`Bar`、`OptionContract`、`Signal`、`TargetPosition`、`OrderIntent`、`ExecutionReport`、`ApprovalRequest`、`PortfolioSnapshot`。
- 控制台接口固定为：
  - `GET /signals/today`
  - `GET /portfolio`
  - `GET /orders`
  - `POST /approvals/{id}/approve`
  - `POST /approvals/{id}/reject`
  - `POST /kill-switch`
  - `POST /reconcile/manual-fill`
- A 股执行方式固定为 `ManualExecutionAdapter`：系统生成建议单，你在本地 Web 控制台确认；成交回报通过手工录入或券商导出文件回填。后续若拿到 `QMT/PTrade` 再替换为自动适配器，不改上层逻辑。
- AI 只接在研究侧：新闻摘要、实验建议、异常复盘、日报周报；AI 不直接输出可下单信号。

## Strategy And Risk
- V1 只做 3 个简单可解释策略：
  - `策略 A`：多市场 ETF 趋势/轮动。标的限定为高流动性宽基 ETF；周频调仓；用 3/6/12 月动量 + 200 日趋势过滤；风险关闭时转现金或防御 ETF。
  - `策略 B`：美股/港股高流动性股票动量。只选高成交额股票；月度选股、周度再平衡；避开财报日前后新开仓；组合中性化只做基础行业分散，不做复杂因子堆叠。
  - `策略 C`：美股期权对冲/备兑。只基于核心持仓和指数 ETF；保护性看跌只在风险-off 状态开启；备兑看涨只覆盖已持有现货，且覆盖比例不超过组合的 `30%`。
- 初始风控参数固定为：
  - 单一股票最大权重 `8%`
  - 单一 ETF 最大权重 `20%`
  - 单日新增期权权利金风险不超过组合净值 `2%`
  - 组合总期权风险预算不超过净值 `5%`
  - 单日亏损达到净值 `2%` 触发当日停机
  - 滚动周亏损达到净值 `4%` 触发降仓
  - 组合回撤达到 `10%` 自动降为半仓
  - 组合回撤达到 `15%` 停止新开仓，只允许减仓和平仓
- 研究验证门槛固定为：
  - 回测必须包含至少 `2018-01-01` 到最近可得数据
  - 使用滚动 walk-forward，不允许只看单段样本
  - 计入市场别交易成本、滑点、汇率与公司行为调整
  - 单策略样本外必须满足：`净年化 > 12%`、`最大回撤 < 12%`、`Sharpe > 1.0`
  - 组合层必须满足：`净年化 > 15%`、`最大回撤 < 15%`、`Calmar > 1.0`

## Delivery Phases
1. `Phase 0: 基线与合规`
   - Status: `Done`
   - 固化市场日历、交易时段、时区、币种、公司行为模型。
   - 确认富途账户、模拟账户、行情权限、美股期权权限。
   - 加一个 A 股合规检查清单；在未与券商确认程序化交易报告要求前，A 股保持半自动。
2. `Phase 1: 数据与回测底座`
   - Status: `In Progress`
   - Remaining: 历史行情采集还偏 `smoke-test / on-demand`，同步编排、覆盖范围、长期完整性校验还需要继续补。
   - 打通 Futu 行情采集、历史数据落地、统一标的主数据。
   - 完成股票/ETF/期权的事件驱动回测器、交易成本模型、组合记账。
3. `Phase 2: 策略研发与筛选`
   - Status: `In Progress`
   - Remaining: 策略实现与研究报告基线已在，但更完整的真实历史覆盖、容量分析和稳定筛选结果还需要沉淀。
   - 按上面的 3 个策略做参数最少化实现。
   - 输出策略研究报告：收益、回撤、换手、容量、市场分布、相关性。
   - 只保留通过门槛且互相关性低于 `0.7` 的策略进入下一阶段。
4. `Phase 3: 模拟交易与人工确认链路`
   - Status: `Code Complete · Awaiting Wall-Clock Evidence`
   - Stage A 上线硬化（去重、盘中风控 tick、NAV fail-closed、EOD 历史同步、告警通道）已合并 `ccb060a` `94dddda`。
   - Stage B 流水/税务 schema 与 OpenD 15-min runbook 已合并 `ff8a8ab`。
   - Stage C 验收门 + wall-clock 证据管道已合并 `0d951ae` `c92ebac`。
   - Stage D 自动门禁（pass-streak 不到不让升档）+ dashboard streak 暴露已合并 `1f8aa29` `9398609`。
   - Remaining: 港美连续 6 周纸面 + A 股 4 周建议单的实际运行证据。
5. `Phase 4: 小资金实盘`
   - Status: `Blocked By Time · Auto-Gated`
   - Remaining: `10% -> 30% -> 100%` 的资金分阶段上线和 `4 周 / 8 周` 稳定性验收，必须依赖真实时间推进。
   - 先用 `10%` 资金跑 4 周；若成交偏差、异常率、风控命中都在预期内，升到 `30%`。
   - 连续 8 周稳定后，再决定是否开到全部资金。
   - `acceptance_gate_readiness` 在每档要求 30/50/70 个连续 pass 日，未达 streak 不允许升档。
6. `Phase 5: 二期扩展`
   - Status: `Deferred`
   - Remaining: 这部分按计划本来就要求 V1 稳定盈利后再开始，不属于当前一次性交付能完成的范围。
   - 仅在 V1 稳定盈利后再考虑：A 股自动适配器、更多券商、更多策略、云端执行迁移。

## Test Plan
- Progress Snapshot
  - Unit tests: `Done`
  - Integration tests: `Done`
  - Backtest reproducibility: `Done`
  - Paper-trading acceptance: `Auto-captured daily, waiting for wall-clock evidence`
  - Live-trading acceptance: `Auto-gated by pass-streak, waiting for wall-clock evidence`
- 单元测试：市场日历、公司行为、仓位计算、期权到期处理、风控阈值、订单状态机。
- 集成测试：Futu 模拟下单、撤单、断线重连、重复成交回报去重、资金与持仓对账。
- 回测一致性测试：相同输入必须可复现；参数变更必须写入实验记录。
- 纸面交易验收：
  - 港美模拟连续运行不少于 `6 周`
  - A 股建议单流程连续运行不少于 `4 周`
  - 模拟成交滑点与模型偏差：股票不超过 `20 bps`，期权不超过权利金的 `10%`
- 实盘验收：
  - 不出现未授权下单
  - 不出现持仓失真
  - 任何 kill switch 都能在 1 个调度周期内生效

## Assumptions And Defaults
- 默认你是个人自有资金交易，不涉及代客理财、多账户托管或对外资管。
- 默认本地机器可在交易时段稳定运行；若本地可用性不足，执行层可迁到云端，但研究与控制台架构不变。
- 默认 V1 不做高频、不做杠杆、不做卖裸期权、不做复杂波动率套利。
- 默认 A 股先以宽基/行业 ETF 为主，减少半自动执行负担；A 股个股自动化留到拿到正式 API 之后。
- 外部约束依据官方资料：
  - [Futu OpenAPI 总览](https://openapi.futunn.com/futu-api-doc/en/)
  - [Futu 下单接口与模拟/实盘说明](https://openapi.futunn.com/futu-api-doc/en/trade/place-order.html)
  - [证监会《证券市场程序化交易管理规定（试行）》自 2024-10-08 施行](https://www.csrc.gov.cn/csrc/c101954/c7480579/content.shtml)
  - [上交所程序化交易实施细则于 2025-07-07 起实施](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20250403_10776805.shtml)
  - 备选券商能力参考 [Tiger Open Platform](https://quant.itigerup.com/openapi/en/cpp/overview/introduction.html)
