# Round 04 — P1.3 Tushare A-share MarketDataAdapter

**Status**: ✅ Done · 2026-04-25

## Goal

新增 Tushare Pro A 股数据适配器，覆盖 token-gated 日线行情和研究型财务/估值数据入口。
本轮只交付 adapter + 配置 + 测试，不接入 `AdapterFactory`，不改变交易或风控路径。

## Done

### 新增文件
- [`tradingcat/adapters/cn/tushare.py`](../tradingcat/adapters/cn/tushare.py) — `TushareMarketDataAdapter`
  - optional import `tushare`，缺依赖时由 `TUSHARE_AVAILABLE=False` 和 `TushareUnavailable` 显式表达。
  - `fetch_bars`：调用 `ts.pro_bar(ts_code, start_date, end_date, freq="D", asset="E", adj=...)`。
  - 支持 CN 6 位股票/ETF symbol 到 Tushare `xxxxxx.SH` / `xxxxxx.SZ` 的映射。
  - 解析字段：`trade_date/open/high/low/close/vol`，按日期升序返回 `Bar`。
  - `fetch_daily_basic`：research-only，返回 plain dict rows。
  - `fetch_fina_indicator`：research-only，返回 plain dict rows。
  - `fetch_quotes` / `fetch_option_chain` / `fetch_corporate_actions` / `fetch_fx_rates`：暂返回空。
- [`tests/test_tushare_adapter.py`](../tests/test_tushare_adapter.py) — 10 个 fake Tushare 用例
  - 不安装 Tushare、不需要 token、不访问网络。
  - 覆盖 token missing、`pro_bar` 成功/空/异常/坏行、SH/SZ 映射、raw adj、research helper、入参拒绝、stub endpoints、配置解析。

### 修改文件
- [`tradingcat/adapters/cn/__init__.py`](../tradingcat/adapters/cn/__init__.py)
  - 导出 `TUSHARE_AVAILABLE` / `TushareMarketDataAdapter` / `TushareUnavailable`。
- [`tradingcat/config.py`](../tradingcat/config.py)
  - 新增 `TushareConfig(enabled, token, adj)`，挂到 `AppConfig.tushare`。
  - 支持 env：`TRADINGCAT_TUSHARE_ENABLED` / `TRADINGCAT_TUSHARE_TOKEN` / `TRADINGCAT_TUSHARE_ADJ`。
- [`pyproject.toml`](../pyproject.toml)
  - 新增 optional extra `sentiment_tushare = ["tushare>=1.4,<2.0"]`。
- [`tests/test_config.py`](../tests/test_config.py)
  - 覆盖 `AppConfig.from_env()` 装载 Tushare 配置。

### 配置开关（新增 env 变量，默认 off / 安全值）
| 变量 | 默认 | 含义 |
|---|---|---|
| `TRADINGCAT_TUSHARE_ENABLED` | `false` | 启用 Tushare 适配器（本轮不接 factory） |
| `TRADINGCAT_TUSHARE_TOKEN` | unset | Tushare Pro token，只从 env 读取 |
| `TRADINGCAT_TUSHARE_ADJ` | `qfq` | 复权：`""` / `qfq` / `hfq` |

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_tushare_adapter.py tests/test_akshare_adapter.py tests/test_baostock_adapter.py tests/test_config.py
# 36 passed
```

## Known gotchas

1. **Tushare 是 optional dep**：生产使用前安装 `pip install 'tradingcat[sentiment_tushare]'`。
2. **token 不入仓库**：`TRADINGCAT_TUSHARE_TOKEN` 只从环境读取，测试全部用 fake client。
3. **本轮不接 factory**：`TushareConfig.enabled` 目前只是配置入口，不改变实际 market data 路由。
4. **research-only helpers**：`daily_basic` / `fina_indicator` 只返回 plain dict，不生成 `Signal` / `OrderIntent`。
5. **Round 04 不处理指数**：`SH000001` / `SZ399001` 仍被拒绝，后续若要指数数据应单独建 path。

## Next step → Round 05 (East Money news source)

Round 05 进入 P2.1：新增 East Money 资讯源 adapter，作为中国市场新闻/公告/快讯底盘之一。

建议任务：
1. 新增 `tradingcat/adapters/news/eastmoney.py` 或等价 news 子包。
2. 新增轻量 `NewsItem` 模型或 adapter-local dataclass；若后续 Round 07 要做统一模型，可以先保持 adapter-local 并在 handoff 标清。
3. 使用 HTTP client 注入方式测试，避免真实网络；可选支持 `curl_cffi`，但默认用 `httpx`。
4. 支持超时、空数据、非 200、JSON shape 变化时返回 `[]`。
5. 新增 `EastMoneyNewsConfig`，默认 disabled；不要接入 LLM，也不要让资讯进入交易决策路径。
6. 暂不改 broker / risk.py / strategies。

入口文件：
- [`tradingcat/adapters/sentiment_sources/cn_market_flows.py`](../tradingcat/adapters/sentiment_sources/cn_market_flows.py) — 现有 HTTP sentiment source 风格参考
- [`tradingcat/config.py`](../tradingcat/config.py) — config 挂载方式参考
- [`tests/test_news_observation_service.py`](../tests/test_news_observation_service.py) — news observation 现有测试参考

## Commit

```
TBD
```

---

## Roadmap 提醒（来自 plan §10.4）

```
✅ Round 01  P1.1 AKShare adapter
✅ Round 02  P1.1 AdapterFactory composite + 集成
✅ Round 03  P1.2 BaoStock adapter
✅ Round 04  P1.3 Tushare adapter（本轮）
⬜ Round 05  P2.1 East Money 资讯源（含 curl_cffi 反爬）
⬜ Round 06  P2.2 财联社 RSS / FinnHub / Alpha Vantage 资讯源
⬜ Round 07  P2.3 NewsItem 模型 + 多层去重过滤管线（无 LLM）
⬜ Round 08  P3 中国市场专属硬规则（涨跌停 / T+1 / ST / 板别）→ risk.py
⬜ Round 09  P4 技术指标特征工程（MA/MACD/RSI/BOLL）→ research_candidates
⬜ Round 10  P5 universe_screener.py（多维度筛选）
⬜ Round 11+ P6 LLM 层（budget gate → provider abstraction → analysts）
```

每轮独立可回退，每轮跟 git commit。
