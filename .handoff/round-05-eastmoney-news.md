# Round 05 — P2.1 East Money News Source

**Status**: ✅ Done · 2026-04-25

## Goal

新增 East Money 资讯源 adapter，作为中国市场新闻/公告/快讯底盘之一。
本轮只交付 news adapter + 配置 + 测试，不接入 LLM，不让资讯进入交易决策路径。

## Done

### 新增文件
- [`tradingcat/adapters/news/__init__.py`](../tradingcat/adapters/news/__init__.py) — news adapter 子包入口。
- [`tradingcat/adapters/news/eastmoney.py`](../tradingcat/adapters/news/eastmoney.py) — `EastMoneyNewsClient`
  - 默认使用 `SentimentHttpClient`，也支持注入 fake/http client 测试。
  - 默认 endpoint：`https://np-listapi.eastmoney.com/comm/web/getNewsByColumns`。
  - adapter-local `NewsItem` dataclass：`source/title/url/published_at/summary/symbols/raw`。
  - `fetch_news(limit=...)` 返回 `NewsItem`。
  - `fetch_items(limit=...)` 返回 plain dict，兼容现有 `NewsObservationService` provider shape。
  - 支持常见 East Money JSON shapes：`data.list`、`data` list、`result.data.items` 等。
  - HTTP `None`、client 抛异常、空数据、缺标题、JSON shape 变化时返回 `[]`。
  - 中文本地时间按 `Asia/Shanghai` 解析后转 UTC。
- [`tests/test_eastmoney_news_adapter.py`](../tests/test_eastmoney_news_adapter.py) — 7 个 fake HTTP 用例
  - 不访问真实网络。
  - 覆盖参数、headers、TTL、常见字段映射、fallback URL、symbols 提取、observation dict shape、异常降级、config parsing。

### 修改文件
- [`tradingcat/config.py`](../tradingcat/config.py)
  - 新增 `EastMoneyNewsConfig(enabled, column, page_size, cache_ttl_seconds, timeout_seconds, user_agent)`。
  - 挂到 `AppConfig.eastmoney_news`。
  - 支持 env：`TRADINGCAT_EASTMONEY_NEWS_*`。
- [`pyproject.toml`](../pyproject.toml)
  - 新增 optional extra `sentiment_eastmoney = ["curl_cffi>=0.7,<1.0"]`。
  - 当前 adapter 默认用 `httpx`/`SentimentHttpClient`；`curl_cffi` 留给后续需要强反爬时接入。
- [`tests/test_config.py`](../tests/test_config.py)
  - 覆盖 `AppConfig.from_env()` 装载 East Money news 配置。

### 配置开关（新增 env 变量，默认 off / 安全值）
| 变量 | 默认 | 含义 |
|---|---|---|
| `TRADINGCAT_EASTMONEY_NEWS_ENABLED` | `false` | 启用 East Money news source（本轮不接 runtime） |
| `TRADINGCAT_EASTMONEY_NEWS_COLUMN` | `351` | East Money news column id |
| `TRADINGCAT_EASTMONEY_NEWS_PAGE_SIZE` | `20` | 每页拉取条数 |
| `TRADINGCAT_EASTMONEY_NEWS_CACHE_TTL_SECONDS` | `600` | HTTP cache TTL |
| `TRADINGCAT_EASTMONEY_NEWS_TIMEOUT_SECONDS` | `5.0` | 预留给 runtime 创建 HTTP client |
| `TRADINGCAT_EASTMONEY_NEWS_USER_AGENT` | `Mozilla/5.0 TradingCat research bot` | 请求 UA |

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_eastmoney_news_adapter.py tests/test_tushare_adapter.py tests/test_config.py
# 20 passed
```

Round 01-05 组合验证：
```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest \
  tests/test_adapter_factory.py \
  tests/test_akshare_adapter.py \
  tests/test_baostock_adapter.py \
  tests/test_tushare_adapter.py \
  tests/test_eastmoney_news_adapter.py \
  tests/test_config.py \
  tests/test_news_observation_service.py
# 56 passed, 1 warning
```

## Known gotchas

1. **本轮不接 runtime**：`EastMoneyNewsConfig.enabled` 目前只是配置入口，不改变现有 `NewsObservationService` 默认 provider。
2. **East Money web API 非正式合约**：adapter 对 shape 做宽松解析，任何异常返回 `[]`，由上层标记 degraded。
3. **curl_cffi 只是 optional extra**：当前默认仍走 `SentimentHttpClient`/`httpx`。若 East Money 后续 TLS 指纹拦截，再单独接 curl transport。
4. **NewsItem 暂为 adapter-local**：Round 07 会做统一 `NewsItem` 模型和多层去重过滤管线。
5. **advisory only**：资讯源不接 LLM、不生成 `Signal` / `OrderIntent`。

## Next step → Round 06 (CLS / Finnhub / Alpha Vantage news sources)

Round 06 进入 P2.2：新增财联社 RSS / Finnhub / Alpha Vantage 资讯源，仍保持 advisory-only。

建议任务：
1. 新增 `tradingcat/adapters/news/cls.py`，优先 RSS/公开 feed，fake HTTP/RSS 测试。
2. 新增 `tradingcat/adapters/news/finnhub.py` 与 `alpha_vantage.py`，token 从 env 读取，默认 disabled。
3. 统一 provider 输出 shape 到 `fetch_items(limit=...) -> list[dict]`，先不要做全局去重；Round 07 再统一。
4. 所有 HTTP/token/shape 失败返回 `[]`。
5. 不接 broker / risk.py / strategies；不让新闻直接驱动交易决策。

入口文件：
- [`tradingcat/adapters/news/eastmoney.py`](../tradingcat/adapters/news/eastmoney.py) — news adapter 形态参考
- [`tests/test_eastmoney_news_adapter.py`](../tests/test_eastmoney_news_adapter.py) — fake HTTP 测试参考
- [`tradingcat/config.py`](../tradingcat/config.py) — news config 挂载方式参考

## Commit

```
e9f2284 absorb-tradingagents-cn: round 05 — East Money news source
```

---

## Roadmap 提醒（来自 plan §10.4）

```
✅ Round 01  P1.1 AKShare adapter
✅ Round 02  P1.1 AdapterFactory composite + 集成
✅ Round 03  P1.2 BaoStock adapter
✅ Round 04  P1.3 Tushare adapter
✅ Round 05  P2.1 East Money 资讯源（本轮）
⬜ Round 06  P2.2 财联社 RSS / FinnHub / Alpha Vantage 资讯源
⬜ Round 07  P2.3 NewsItem 模型 + 多层去重过滤管线（无 LLM）
⬜ Round 08  P3 中国市场专属硬规则（涨跌停 / T+1 / ST / 板别）→ risk.py
⬜ Round 09  P4 技术指标特征工程（MA/MACD/RSI/BOLL）→ research_candidates
⬜ Round 10  P5 universe_screener.py（多维度筛选）
⬜ Round 11+ P6 LLM 层（budget gate → provider abstraction → analysts）
```

每轮独立可回退，每轮跟 git commit。
