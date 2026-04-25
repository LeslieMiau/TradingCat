# Round 11 — P6.1 LLM Budget Gate

**Status**: ✅ Done · 2026-04-25

## Goal

在接任何 LLM provider/analyst 前先建立预算栅栏。默认 disabled，触顶降级，不影响交易路径。

## Done

- [`tradingcat/config.py`](../tradingcat/config.py)
  - 新增 `LLMConfig(enabled, provider, model, daily_token_budget, monthly_cost_budget)`。
- [`tradingcat/services/llm_budget.py`](../tradingcat/services/llm_budget.py)
  - `LLMBudgetGate.check(...)`。
  - `LLMBudgetGate.check_and_record(...)`。
  - `LLMUsage` / `LLMBudgetDecision` / `InMemoryLLMUsageLedger`。
- [`tests/test_llm_budget.py`](../tests/test_llm_budget.py)
  - 覆盖 disabled、allow+record、daily token exceeded、monthly cost exceeded、env parsing。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_llm_budget.py tests/test_config.py
# 8 passed
```

## Known gotchas

1. **默认 disabled**：不接 provider，不调用外部模型。
2. **ledger 先用内存**：后续可换 JSON/PG repo，不影响 gate API。
3. **advisory only**：budget gate 只服务未来研究/报告调用。

## Next step → Round 12 (LLM provider abstraction)

Round 12：新增 LLM provider Protocol 和 fake/OpenAI-compatible adapter 壳，不真实调用网络。

建议任务：
1. 新增 `tradingcat/adapters/llm/`。
2. 定义 `LLMProvider` / `LLMResponse`。
3. 提供 deterministic fake provider 和 OpenAI-compatible HTTP provider。
4. provider 调用必须先过 `LLMBudgetGate`。
5. 写测试覆盖 budget denied、fake success、usage recording。

## Commit

```
92f85c7 absorb-tradingagents-cn: round 11 — LLM budget gate
```
