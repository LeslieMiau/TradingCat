# Round 01 — P1.1 AKShare A-share MarketDataAdapter

**Status**: ✅ Done · 2026-04-25

## Goal

吸收 TradingAgents-CN 的 AKShare 经验，给 TradingCat 加一条**确定性 A 股数据通路**——
覆盖率比现有 yfinance 兜底更完整。**不替代** Futu/yfinance，仅作 CN 板块的可选首选。
本轮只交付 adapter 类 + 配置 + 测试，**不改 AdapterFactory**——零风险扰动既有验收门。

## Done

### 新增文件
- [`tradingcat/adapters/cn/__init__.py`](../tradingcat/adapters/cn/__init__.py) — 子包入口
- [`tradingcat/adapters/cn/akshare.py`](../tradingcat/adapters/cn/akshare.py) — `AkshareMarketDataAdapter` 实现
  - `fetch_bars`：A 股普通股走 `stock_zh_a_hist`，ETF 走 `fund_etf_hist_em`，按 `Instrument.asset_class` 分发
  - `fetch_quotes`：缓存 `stock_zh_a_spot_em` 全市场快照（默认 30s TTL），从中查价
  - `fetch_option_chain` / `fetch_corporate_actions` / `fetch_fx_rates`：暂返回 `[]`，留给后续 round
  - 入参严格校验：拒绝非 CN 市场、拒绝 `SH`/`SZ` 指数标签、拒绝非 6 位数字代码 → 抛 `AkshareUnavailable`
  - 异常吞掉返回空：网络失败/解析失败不传播
- [`tests/test_akshare_adapter.py`](../tests/test_akshare_adapter.py) — 14 个用例，注入 fake `akshare` 模块跑

### 修改文件
- [`tradingcat/config.py`](../tradingcat/config.py)
  - 新增 `AkshareConfig`（`enabled` / `adjust` / `spot_cache_ttl_seconds`），从 env 解析
  - 挂到 `AppConfig.akshare`，`from_env` 装载

### 配置开关（新增 env 变量，默认全部 off / 安全值）
| 变量 | 默认 | 含义 |
|---|---|---|
| `TRADINGCAT_AKSHARE_ENABLED` | `false` | 启用 AKShare 适配器（factory 接线在 Round 02） |
| `TRADINGCAT_AKSHARE_ADJUST` | `qfq` | 复权方式：`""` / `qfq` / `hfq` |
| `TRADINGCAT_AKSHARE_SPOT_CACHE_TTL_SECONDS` | `30.0` | 现货快照缓存秒数 |

## Verification

```bash
pytest tests/test_akshare_adapter.py tests/test_config.py -v
# 17 passed
```

完整回归：
```bash
# 排除环境缺依赖（duckdb/yfinance 在本机 Homebrew Python 没装）的 collection 错误
pytest --ignore=tests/test_acceptance_gates.py \
       --ignore=tests/test_adapter_factory.py \
       --ignore=tests/test_api.py \
       --ignore=tests/test_dashboard_facade.py \
       --ignore=tests/test_history_audit.py \
       --ignore=tests/test_intraday_risk_tick.py \
       --ignore=tests/test_notifier.py \
       --ignore=tests/test_persistence.py \
       --ignore=tests/test_research_reporting.py \
       --ignore=tests/test_runtime_recovery.py \
       --ignore=tests/test_scheduler_history.py \
       --ignore=tests/test_scheduler_runtime.py \
       --ignore=tests/test_selection_service.py \
       --ignore=tests/test_trade_ledger.py \
       --ignore=tests/test_trade_ledger_reconciliation.py
# 258 passed (9 failed + 13 errors 全部环境性，与本 round 无关)
```

## Known gotchas

1. **AKShare 是 optional dep**——必须先 `pip install 'tradingcat[sentiment_akshare]'` 才能在生产用。
   测试用注入的 fake module，不需要装。
2. **A 股 ETF 与 stock 走不同 endpoint**——必须正确填 `Instrument.asset_class`。
   ETF 用 `fund_etf_hist_em`，stock 用 `stock_zh_a_hist`。
3. **指数（SH000001 等）不归这个 adapter**——会被显式拒绝，留给 yfinance 或后续 index adapter。
4. **AKShare 列名是中文**：`日期/开盘/收盘/最高/最低/成交量`。已封装，调用方无感。
5. **快照端点 `stock_zh_a_spot_em` 一次返回 5000+ 行**——务必走缓存，不要在 hot loop 里每 symbol 一调。
6. **反爬虫**：当前未启用 `curl_cffi`，因为我们走 AKShare SDK 不直接发请求。**后续接东财直链**（Round 04 资讯源）时必装。参考 TradingAgents-CN 用 `curl_cffi.impersonate("chrome120")` 绕过 TLS 指纹拦截。
7. **复权选 `qfq`** 是 backtest 一致性默认；要原始价位用 `""`。

## Next step → Round 02 (factory wiring + composite adapter)

Round 01 的 adapter 现在是**孤立的、不会被任何代码路径调到**——
必须在 [`AdapterFactory`](../tradingcat/adapters/factory.py) 里接进去才能产生效果。

### 任务

1. **新建 `CompositeMarketDataAdapter`**（建议放 [`tradingcat/adapters/composite.py`](../tradingcat/adapters/composite.py) 或 `factory.py` 内私有类）：
   - 按 `Instrument.market` 分发：CN → akshare（如启用），其他 → 当前已有适配器
   - 失败 fallback：akshare 抛 `AkshareUnavailable` 或 `fetch_bars` 返回空时，回退到 yfinance/static
   - `fetch_quotes` 多 instrument 时按 market 分组分别下发再合并
   - 其他方法（`fetch_option_chain` / `fetch_corporate_actions` / `fetch_fx_rates`）暂直接转发给 inner adapter（akshare 这些都返回空）

2. **修改 [`AdapterFactory.create_market_data_adapter`](../tradingcat/adapters/factory.py:90)**：
   - 在现有 Futu→YFinance→Static 链的最后一步**之后**，如果 `config.akshare.enabled and AKSHARE_AVAILABLE`，把当前选中的 adapter 包成 `CompositeMarketDataAdapter(akshare_inner=AkshareMarketDataAdapter(...), us_hk_inner=current_choice)`
   - 启动日志区分清楚"CN→akshare, US/HK→futu"

3. **测试**（[`tests/test_adapter_factory.py`](../tests/test_adapter_factory.py)）：
   - akshare 关闭时，factory 行为与 Round 01 之前完全一致（向后兼容断言）
   - akshare 开启 + AKSHARE_AVAILABLE=True → CN instrument 路由到 akshare
   - akshare 开启但 AKShare 抛错 → fallback 到 inner（yfinance/static）

4. **集成测试**：检查 [`tradingcat/services/market_data.py`](../tradingcat/services/market_data.py) 的 history sync 路径，确认开启 akshare 后 CN symbol 的 sync 走新通路。可加一条 e2e 测试用 fake akshare 模块。

### 入口文件
- [`tradingcat/adapters/factory.py:90-103`](../tradingcat/adapters/factory.py) — `create_market_data_adapter` 当前实现
- [`tests/test_adapter_factory.py`](../tests/test_adapter_factory.py) — 既有 factory 测试样式参考

### 边界提醒
- **不要**让 akshare 路径介入 broker 创建——只是 market data 适配器
- **不要**默认开启——保持 `enabled=false`，让用户显式启用
- **不要**改 `[`risk.py`](../tradingcat/services/risk.py)`——P3 才动它

## Commit

```
c5eb8e4 absorb-tradingagents-cn: round 01 — AKShare A-share market data adapter
```

---

## Roadmap 提醒（来自 plan §10.4）

```
✅ Round 01  P1.1 AKShare adapter（本轮）
⬜ Round 02  P1.1 AdapterFactory composite + 集成
⬜ Round 03  P1.2 BaoStock adapter（free fallback）
⬜ Round 04  P1.3 Tushare adapter（daily_basic 截面 + fina_indicator 时序）
⬜ Round 05  P2.1 East Money 资讯源（含 curl_cffi 反爬）
⬜ Round 06  P2.2 财联社 RSS / FinnHub / Alpha Vantage 资讯源
⬜ Round 07  P2.3 NewsItem 模型 + 多层去重过滤管线（无 LLM）
⬜ Round 08  P3 中国市场专属硬规则（涨跌停 / T+1 / ST / 板别）→ risk.py
⬜ Round 09  P4 技术指标特征工程（MA/MACD/RSI/BOLL）→ research_candidates
⬜ Round 10  P5 universe_screener.py（多维度筛选）
⬜ Round 11+ P6 LLM 层（budget gate → provider abstraction → analysts）
```

每轮独立可回退，每轮跟 git commit。
