# Round 06 — P2.2 CLS / Finnhub / Alpha Vantage News Sources

**Status**: ✅ Done · 2026-04-25

## Goal

补齐 P2 资讯源底盘的第二批 source：财联社、Finnhub、Alpha Vantage。
本轮仍保持 advisory-only，只交付 adapter + config + tests，不接 LLM、不进入交易决策路径。

## Done

### 新增文件
- [`tradingcat/adapters/news/cls.py`](../tradingcat/adapters/news/cls.py)
  - `CLSNewsClient` 拉取财联社公开 web API。
  - 解析 `data.roll_data` / `data.list` 等常见 shape。
  - 输出 `fetch_items(limit=...) -> list[dict]`，兼容 `NewsObservationService` provider shape。
- [`tradingcat/adapters/news/finnhub.py`](../tradingcat/adapters/news/finnhub.py)
  - `FinnhubNewsClient` 封装 `company-news`。
  - token/symbols 缺失时返回 `[]`。
- [`tradingcat/adapters/news/alpha_vantage.py`](../tradingcat/adapters/news/alpha_vantage.py)
  - `AlphaVantageNewsClient` 封装 `NEWS_SENTIMENT`。
  - api key/tickers 缺失时返回 `[]`。
- [`tests/test_news_sources_round06.py`](../tests/test_news_sources_round06.py)
  - fake HTTP 覆盖 CLS / Finnhub / Alpha Vantage 成功、缺 token、异常降级和 config parsing。

### 修改文件
- [`tradingcat/adapters/news/__init__.py`](../tradingcat/adapters/news/__init__.py)
  - 导出 Round 06 news clients。
- [`tradingcat/config.py`](../tradingcat/config.py)
  - 新增 `CLSNewsConfig` / `FinnhubNewsConfig` / `AlphaVantageNewsConfig`，均默认 disabled。
  - 挂到 `AppConfig`。
- [`tests/test_config.py`](../tests/test_config.py)
  - 覆盖三类 news source config 的 env 装载。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_news_sources_round06.py tests/test_eastmoney_news_adapter.py tests/test_config.py
# 15 passed
```

## Known gotchas

1. **token/API key 不入仓库**：Finnhub 和 Alpha Vantage key 只从 env 读取。
2. **本轮不接 runtime**：新增 clients 不改变现有 `NewsObservationService` 默认 provider。
3. **shape 宽松解析**：外部 API shape 变化时返回 `[]`，后续由统一过滤层标记 degraded。
4. **advisory only**：新闻源只做研究输入，不生成交易信号。

## Next step → Round 07 (Unified NewsItem + filter pipeline)

Round 07 进入 P2.3：统一新闻模型和多层去重过滤管线，无 LLM。

建议任务：
1. 新增统一 `NewsItem` domain/research model，包含 `source/title/url/published_at/summary/symbols/urgency/event_class/relevance/quality_score`。
2. 新增 `tradingcat/services/news_filter.py`：
   - URL 规范化去重。
   - 标题归一化/短标题过滤。
   - source allow/deny。
   - 时间衰减。
   - urgency/event_class 关键词分类。
   - relevance/quality score 计算。
3. 扩展或新增测试，不接 LLM。
4. 暂不改 broker / risk.py / strategies。

## Commit

```
906efb8 absorb-tradingagents-cn: round 06 — additional news sources
```
