# Round 07 — P2.3 Unified NewsItem + Filter Pipeline

**Status**: ✅ Done · 2026-04-25

## Goal

新增统一新闻模型和无 LLM 的多层过滤/去重/打分管线，为后续资讯源聚合和研究分析师提供稳定输入。

## Done

### 新增文件
- [`tradingcat/domain/news.py`](../tradingcat/domain/news.py)
  - `NewsItem` Pydantic model。
  - `NewsUrgency`：high / medium / low。
  - `NewsEventClass`：earnings / guidance / m_and_a / policy / regulatory / crisis / industry / management / macro / other。
- [`tradingcat/services/news_filter.py`](../tradingcat/services/news_filter.py)
  - URL 规范化去重，去掉 `utm_*` / `fbclid` / `gclid` 等 tracking 参数。
  - 标题归一化与短标题过滤。
  - source allow/deny。
  - urgency/event_class 关键词分类。
  - target symbol relevance 评分。
  - source quality + freshness + relevance + urgency 的 deterministic quality score。
- [`tests/test_news_filter.py`](../tests/test_news_filter.py)
  - 覆盖 URL 去重、tracking 清理、排序、source 过滤、短标题过滤、model 输入和 limit。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_news_filter.py tests/test_news_sources_round06.py tests/test_eastmoney_news_adapter.py tests/test_news_observation_service.py
# 17 passed
```

## Known gotchas

1. **无 LLM**：本轮完全确定性，不做摘要重排。
2. **暂不改默认 NewsObservationService**：先提供独立 service，后续 round 可显式接入。
3. **分类是关键词启发式**：适合过滤/排序，不是交易信号。
4. **NewsItem 与 Round 05 adapter-local NewsItem 同名**：Round 07 起推荐使用 `tradingcat.domain.news.NewsItem`；adapter-local 模型留作兼容。

## Next step → Round 08 (China market hard risk rules)

Round 08 进入 P3：中国市场专属确定性硬规则。

建议任务：
1. 在 domain/config/risk 增加 A 股规则所需字段，但保持默认不破坏既有行为。
2. 支持涨跌停判断：普通 A 股 ±10%，ST ±5%，科创/创业 ±20%。
3. 支持 T+1 卖出锁的纯函数/校验入口。
4. 支持 ST / *ST / 退市预警标记的确定性拦截。
5. 写 risk 单测；不要引入 LLM，不碰策略。

## Commit

```
f2d9aba absorb-tradingagents-cn: round 07 — news filter pipeline
```
