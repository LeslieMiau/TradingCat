# Round 12 — P6.2 LLM Provider Abstraction

**Status**: ✅ Done · 2026-04-25

## Goal

新增 LLM provider 抽象层，并强制所有 provider 调用先经过 Round 11 的 budget gate。

## Done

- [`tradingcat/adapters/llm/base.py`](../tradingcat/adapters/llm/base.py)
  - `LLMMessage` / `LLMResponse` / `LLMProvider` / `LLMProviderError`。
- [`tradingcat/adapters/llm/fake.py`](../tradingcat/adapters/llm/fake.py)
  - deterministic fake provider，测试和后续 analyst 可用。
- [`tradingcat/adapters/llm/openai_compatible.py`](../tradingcat/adapters/llm/openai_compatible.py)
  - OpenAI-compatible chat-completions HTTP provider。
  - budget denied 时不发 HTTP。
  - 成功后记录实际 usage。
- [`tests/test_llm_provider.py`](../tests/test_llm_provider.py)
  - 覆盖 fake success、budget denied、HTTP-compatible success、denied 不发请求。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_llm_provider.py tests/test_llm_budget.py
# 9 passed
```

## Known gotchas

1. **没有真实联网测试**：HTTP provider 通过 fake client 验证 contract。
2. **仍 advisory-only**：没有接入 strategy/risk/order。
3. **同步 API**：先匹配当前服务风格；异步可后续加。

## Next step → Round 13 (Advisory research analysts)

Round 13：新增 advisory-only research analysts。

建议任务：
1. 新增 `tradingcat/services/research_analysts/`。
2. 定义 `AnalystOutput(summary, bullets, confidence, risks, source_refs)`。
3. 用 `LLMProvider` 消费 news/technical/screener payload，输出研究档案对象。
4. 测试断言不生成 `Signal` / `OrderIntent`。

## Commit

```
TBD
```
