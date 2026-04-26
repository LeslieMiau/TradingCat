# Round 13 — P6.3 Advisory Research Analysts

**Status**: ✅ Done · 2026-04-26

## Goal

新增 advisory-only research analyst wrapper，消费 Round 12 LLM provider 输出结构化研究对象。

## Done

- [`tradingcat/services/research_analysts/service.py`](../tradingcat/services/research_analysts/service.py)
  - `AnalystOutput(summary, bullets, confidence, risks, source_refs, metadata)`。
  - `ResearchAnalystService.analyze(...)`。
  - system prompt 明确禁止交易/订单/审批建议。
  - metadata 标记 `advisory_only=True`。
- [`tests/test_research_analysts.py`](../tests/test_research_analysts.py)
  - 覆盖结构化输出、usage recording。
  - 断言输出不是 `Signal` / `OrderIntent`。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_research_analysts.py tests/test_llm_provider.py tests/test_llm_budget.py
# 11 passed
```

## Known gotchas

1. **不做交易建议执行**：仅输出研究对象。
2. **解析轻量**：先从文本抽 summary/bullets/risks；后续可改 JSON schema。
3. **依赖 budget-gated provider**：所有调用仍过 Round 11/12。

## Next step → Round 14 (Report export)

Round 14：新增研究报告导出（Markdown first）。

建议任务：
1. 新增 `tradingcat/services/report_export.py`。
2. 支持把 screener candidates / analyst outputs / news items 导出为 Markdown。
3. 输出到调用方指定路径，不默认写生产目录。
4. 测试文件内容即可；DOCX/PDF 可后续 round 接。

## Commit

```
da87d27 absorb-tradingagents-cn: round 13 — advisory research analysts
```
