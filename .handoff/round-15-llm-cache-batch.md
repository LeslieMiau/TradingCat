# Round 15 — P6.5 LLM Cache + Batch Research

**Status**: ✅ Done · 2026-04-26

## Goal

新增 advisory-only 的 LLM response cache 与批量研究辅助服务，把 universe screener、research analyst、report export 串成轻量离线编排，但不接入交易决策或 runtime 自动执行路径。

## Done

- [`tradingcat/services/llm_cache.py`](../tradingcat/services/llm_cache.py)
  - 新增 `InMemoryLLMResponseCache`，按 provider / model / purpose / messages 生成稳定 SHA256 cache key。
  - 新增 `CachedLLMProvider` read-through wrapper，cache hit 时不再调用 inner provider，也不新增 budget usage。
  - 保留底层 provider/model 透传，便于后续替换 provider 时复用。
- [`tradingcat/services/batch_research.py`](../tradingcat/services/batch_research.py)
  - 新增 `BatchResearchService`，组合 `UniverseScreener`、`ResearchAnalystService`、`ReportExportService`。
  - 新增 `BatchResearchResult`，返回 ranked candidates、analyst outputs，以及 markdown 字符串或写入路径。
  - 支持 `NewsItem` 或 dict news 输入，无法校验的新闻项在报告层忽略。
- [`tests/test_llm_cache_batch_research.py`](../tests/test_llm_cache_batch_research.py)
  - 覆盖 LLM cache hit 不重复记账。
  - 覆盖 batch research 排序、analyst advisory metadata、Markdown 生成。
  - 覆盖指定路径写出 batch report。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_llm_cache_batch_research.py tests/test_report_export.py tests/test_research_analysts.py tests/test_llm_provider.py tests/test_llm_budget.py tests/test_universe_screener.py
# 19 passed
```

## Known gotchas

1. **In-memory only**：本轮只提供进程内 cache，不做持久化、TTL、跨进程共享。
2. **不接 runtime**：`BatchResearchService` 是可测试的离线服务，未接 FastAPI route、scheduler 或交易路径。
3. **advisory-only**：输出仍是研究报告/候选解释，不生成 `Signal` / `OrderIntent`。
4. **Fake provider tests**：测试不访问外部 LLM 或行情网络。

## Next step → Round 16 (optional hardening)

当前 plan 中 P1-P6 主线已经完成到可组合的研究能力层。后续如继续推进，建议选择小步 hardening：

1. 为 LLM cache 增加可选持久化后端和 TTL。
2. 把 batch research 作为显式 operator-only 工具接入，而不是自动交易路径。
3. 扩展 report export 到 DOCX/PDF，保持 Markdown 为默认无依赖格式。

## Commit

```
514a08b absorb-tradingagents-cn: round 15 — LLM cache and batch research
```
