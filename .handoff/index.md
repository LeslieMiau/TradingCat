# TradingAgents-CN 能力吸收 — 执行 Handoff Index

## 背景与计划文件

完整方案见 [`/Users/miau/.claude/plans/https-github-com-hsliuping-tradingagent-peppy-pinwheel.md`](file:///Users/miau/.claude/plans/https-github-com-hsliuping-tradingagent-peppy-pinwheel.md)。

核心原则（不可违背）：
- **AI 仅作研究/咨询，绝不进入交易决策路径**。任何吸收能力都不能直接生成 `OrderIntent` / `Signal`。
- 风控硬规则（见 [`tradingcat/services/risk.py`](../tradingcat/services/risk.py)）保持确定性，绝不让 LLM 替代。
- 不引入 MongoDB / Vue3 重写 / AiHubMix。
- 详见 [`PLAN.md`](../PLAN.md) §五边界与 plan 文件 §五。

## 落地顺序（来自 plan 文件 §10.4）

```
P1 数据源底盘（A 股）         ── adapters/cn/{akshare,baostock,tushare}.py
P2 资讯源底盘                ── adapters/news/{eastmoney,cls,finnhub,alpha_vantage}.py
P3 中国市场专属规则进 risk    ── 涨跌停 / T+1 / ST / 板别
P4 技术指标特征工程          ── strategies/research_candidates.py 多指标共振
P5 universe_screener.py     ── 多维度筛选喂 research_ideas
P6 LLM 层（advisory only）   ── budget gate → provider abstraction → analysts
```

每个 Round 是独立可回退的 git checkpoint。

## Round 状态

| # | 标题 | 状态 | 文档 | Commit |
|---|---|---|---|---|
| 01 | P1.1 AKShare A 股 MarketDataAdapter | ✅ done | [round-01-akshare-adapter.md](round-01-akshare-adapter.md) | (见下方 git log) |
| 02 | P1.1 AdapterFactory composite 接线 | ✅ done | [round-02-factory-composite.md](round-02-factory-composite.md) | `1ac8f78` |
| 03 | P1.2 BaoStock adapter | ✅ done | [round-03-baostock-adapter.md](round-03-baostock-adapter.md) | `f4e2ff6` |
| 04 | P1.3 Tushare adapter | ✅ done | [round-04-tushare-adapter.md](round-04-tushare-adapter.md) | `8d5cde6` |
| 05 | P2.1 East Money 资讯源 | ✅ done | [round-05-eastmoney-news.md](round-05-eastmoney-news.md) | `e9f2284` |
| 06+ | P2 其他资讯源 / P3 风控规则 / P4 指标 / P5 筛选 / P6 LLM | ⬜ pending | — | — |

## 下一步给 Codex 的指引

1. 读 [round-05-eastmoney-news.md](round-05-eastmoney-news.md) §"Next step → Round 06"。
2. 创建 `.handoff/round-06-news-sources.md`，按相同结构（Goal / Done / Verification / Known gotchas / Next step）填写。
3. 跑新增 news source 测试，并回归 `tests/test_eastmoney_news_adapter.py tests/test_config.py`。
4. commit + 更新本 index 表的 Round 06 行。

## 给 Codex 接力者的常用指令

```bash
# 拉取最新进度
git log --oneline -10

# 查看本批 handoff 文档
ls .handoff

# 阅读最新 round 文档
cat .handoff/round-NN-*.md

# 跑测试
pytest -x

# 跑特定 round 涉及的测试
pytest tests/test_<area>.py -v
```

每个 round 文档结构：
1. Goal — 这一步要解决什么
2. Done — 实际改了什么（文件 + 行号）
3. Verification — 怎么验证已通过
4. Known gotchas — 踩过的坑、依赖、配置开关
5. Next step — 下一 round 应该做什么、入口在哪

接力者读 Next step 即可继续。
