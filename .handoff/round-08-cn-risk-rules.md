# Round 08 — P3 China Market Hard Risk Rules

**Status**: ✅ Done · 2026-04-25

## Goal

把中国市场专属的确定性硬规则接入 `RiskEngine`：涨跌停、T+1、ST/退市风险标记。
本轮是 risk.py 的计划内修改，不引入 LLM，不改策略。

## Done

- [`tradingcat/config.py`](../tradingcat/config.py)
  - `RiskConfig` 新增 CN 规则开关与涨跌停参数。
  - 默认启用确定性 CN market rules。
- [`tradingcat/services/risk.py`](../tradingcat/services/risk.py)
  - CN ST / *ST / 退市标记拦截。
  - 普通 A 股 ±10%，ST ±5%，创业/科创 `300/301/688` ±20%。
  - 买入触涨停拦截，卖出触跌停拦截。
  - 支持 `metadata.limit_status` 直接标注 `limit_up/limit_down`。
  - 支持 `metadata.last_buy_date/acquired_at/bought_at` 的 T+1 卖出锁。
- [`tests/test_risk.py`](../tests/test_risk.py)
  - 覆盖 ST/退市、涨跌停、20% 板别、T+1 卖出锁。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_risk.py
# 16 passed
```

## Known gotchas

1. **只对 CN 生效**：US/HK 风控路径不变。
2. **T+1 依赖 metadata**：本轮不改 ledger/position 模型，先提供 risk 校验入口。
3. **涨跌停需要 previous_close/current price**：缺数据时不做推断，避免误杀。
4. **确定性硬规则**：无 LLM、无新闻、无 analyst 参与。

## Next step → Round 09 (Technical indicator feature engineering)

Round 09 进入 P4：技术指标特征工程进 research candidates。

建议任务：
1. 在 `tradingcat/strategies/research_candidates.py` 或新 helper 中加入 MA/MACD/RSI/BOLL/量价特征计算。
2. 输出 research-only metadata（support/resistance/stop_loss 等），不改变生产策略。
3. 写小样本单测，覆盖趋势共振、超买超卖、BOLL 突破。

## Commit

```
956b472 absorb-tradingagents-cn: round 08 — China market risk rules
```
