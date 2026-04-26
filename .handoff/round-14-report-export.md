# Round 14 — P6.4 Report Export

**Status**: ✅ Done · 2026-04-26

## Goal

新增研究报告导出服务，先支持 Markdown，把 analyst outputs / universe candidates / news items 组合为可归档报告。

## Done

- [`tradingcat/services/report_export.py`](../tradingcat/services/report_export.py)
  - `ReportExportService.render_markdown(...)`。
  - `ReportExportService.export_markdown(path, ...)`。
  - 报告明确标注 advisory-only，不生成交易指令。
- [`tests/test_report_export.py`](../tests/test_report_export.py)
  - 覆盖 Markdown section 内容和指定路径写入。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_report_export.py tests/test_research_analysts.py tests/test_universe_screener.py
# 7 passed
```

## Known gotchas

1. **Markdown first**：DOCX/PDF 后续可接，不在本轮扩大依赖。
2. **调用方指定路径**：服务不会默认写生产报告目录。
3. **advisory-only**：报告不产生 signals/orders。

## Next step → Round 15 (LLM cache + batch research)

Round 15：新增 LLM response cache 和批量研究辅助。

建议任务：
1. 新增 `tradingcat/services/llm_cache.py`。
2. 新增 `BatchResearchService`，组合 screener + analyst + report export 的轻量编排。
3. 测试 cache hit/miss 和 batch 输出；不接 runtime。

## Commit

```
TBD
```
