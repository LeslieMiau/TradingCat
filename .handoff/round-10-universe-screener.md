# Round 10 — P5 Universe Screener

**Status**: ✅ Done · 2026-04-25

## Goal

新增 research-only 多维度 universe screener，把技术面、基本面、新闻面输入合成为候选排序。

## Done

- [`tradingcat/services/universe_screener.py`](../tradingcat/services/universe_screener.py)
  - `UniverseScreener.screen(...)`。
  - `UniverseCandidate` 输出 instrument、score、分项 score、reasons、metadata。
  - 支持 technical / fundamentals / news 三维加权。
  - 缺数据时降级到中性偏低分，不阻塞筛选。
- [`tests/test_universe_screener.py`](../tests/test_universe_screener.py)
  - 覆盖多维排序、缺数据降级、limit、序列化。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_universe_screener.py tests/test_research_candidate_technical_features.py tests/test_research_reporting.py
# 34 passed, 1 warning
```

## Known gotchas

1. **research-only**：不生成 `Signal` / `OrderIntent`。
2. **输入由调用方提供**：本轮不接 scheduler/runtime 自动拉取。
3. **权重可调但无配置挂载**：先保持服务构造参数，避免扩大配置面。

## Next step → Round 11 (LLM budget gate)

Round 11 进入 P6 的第一步：LLM budget gate。先建栅栏，再接 provider/analyst。

建议任务：
1. 新增 `tradingcat/services/llm_budget.py`。
2. 支持 daily token / monthly cost / provider rate 的 deterministic gate。
3. 支持 JSON ledger repository 或内存 ledger，默认 disabled。
4. 触顶返回 skip/degrade，不抛到交易路径。
5. 写测试覆盖 allow、daily exceeded、monthly exceeded、record usage。

## Commit

```
TBD
```
