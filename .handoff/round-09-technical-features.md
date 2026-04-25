# Round 09 — P4 Technical Indicator Feature Engineering

**Status**: ✅ Done · 2026-04-25

## Goal

把 TradingAgents-CN prompt 中的技术分析框架转成 TradingCat 的确定性 research-only 特征工程。

## Done

- [`tradingcat/strategies/research_candidates.py`](../tradingcat/strategies/research_candidates.py)
  - 新增 `TechnicalFeatureSnapshot`。
  - 新增 `compute_technical_features(bars)`。
  - 覆盖 MA5/10/20/60、MACD、RSI14、BOLL、20 日量比、support/resistance。
  - 输出 `trend_alignment` / `momentum_state`，可作为研究候选 metadata。
- [`tests/test_research_candidate_technical_features.py`](../tests/test_research_candidate_technical_features.py)
  - 覆盖 bullish/bearish alignment、overbought/oversold、短序列、量比和 metadata 输出。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_research_candidate_technical_features.py tests/test_research_reporting.py tests/test_backtest.py
# 38 passed, 1 warning
```

## Known gotchas

1. **research-only**：没有改生产策略生成逻辑。
2. **无外部依赖**：未引入 TA-Lib/stockstats，避免环境负担。
3. **指标用于排序/报告，不是自动交易决策**。

## Next step → Round 10 (Universe screener)

Round 10 进入 P5：新增 universe screener，把基础面/技术面/新闻面信号组合成研究候选排序。

建议任务：
1. 新增 `tradingcat/services/universe_screener.py`。
2. 输入 instruments、technical snapshots、fundamental rows、news items，输出 research-only ranked candidates。
3. 写单测覆盖维度加权、缺数据降级、排序。
4. 不接 OrderIntent / risk / approval。

## Commit

```
TBD
```
