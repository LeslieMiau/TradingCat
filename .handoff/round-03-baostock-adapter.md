# Round 03 — P1.2 BaoStock A-share MarketDataAdapter

**Status**: ✅ Done · 2026-04-25

## Goal

新增 BaoStock 免费 A 股日线数据适配器，作为后续中国市场数据 fallback 的候选能力。
本轮只交付 adapter + 配置 + 测试，不接入 `AdapterFactory`，确保默认运行路径和 Round 02 行为不变。

## Done

### 新增文件
- [`tradingcat/adapters/cn/baostock.py`](../tradingcat/adapters/cn/baostock.py) — `BaostockMarketDataAdapter`
  - optional import `baostock`，缺依赖时由 `BAOSTOCK_AVAILABLE=False` 和 `BaostockUnavailable` 显式表达。
  - `fetch_bars`：调用 BaoStock `login()` → `query_history_k_data_plus(..., frequency="d")` → `logout()`。
  - 支持 CN 6 位股票/ETF symbol 到 BaoStock `sh.xxxxxx` / `sz.xxxxxx` 的映射。
  - 解析字段：`date,code,open,high,low,close,volume,amount,tradestatus`。
  - 跳过停牌行（`tradestatus != 1`）和 malformed rows。
  - login/query/网络异常返回 `[]`，不向调用方传播。
  - `fetch_quotes` / `fetch_option_chain` / `fetch_corporate_actions` / `fetch_fx_rates`：暂返回空。
- [`tests/test_baostock_adapter.py`](../tests/test_baostock_adapter.py) — 9 个 fake BaoStock 用例
  - 不安装 BaoStock、不访问网络。
  - 覆盖 login/logout 生命周期、查询参数、SH/SZ 映射、错误降级、入参拒绝、stub endpoints、配置解析。

### 修改文件
- [`tradingcat/adapters/cn/__init__.py`](../tradingcat/adapters/cn/__init__.py)
  - 导出 `BAOSTOCK_AVAILABLE` / `BaostockMarketDataAdapter` / `BaostockUnavailable`。
- [`tradingcat/config.py`](../tradingcat/config.py)
  - 新增 `BaostockConfig(enabled, adjustflag)`，挂到 `AppConfig.baostock`。
  - 支持 env：`TRADINGCAT_BAOSTOCK_ENABLED` / `TRADINGCAT_BAOSTOCK_ADJUSTFLAG`。
- [`pyproject.toml`](../pyproject.toml)
  - 新增 optional extra `sentiment_baostock = ["baostock>=0.8,<1.0"]`。
- [`tests/test_config.py`](../tests/test_config.py)
  - 覆盖 `AppConfig.from_env()` 装载 BaoStock 配置。

### 配置开关（新增 env 变量，默认 off / 安全值）
| 变量 | 默认 | 含义 |
|---|---|---|
| `TRADINGCAT_BAOSTOCK_ENABLED` | `false` | 启用 BaoStock 适配器（本轮不接 factory） |
| `TRADINGCAT_BAOSTOCK_ADJUSTFLAG` | `2` | BaoStock 复权标志：`1` 后复权 / `2` 前复权 / `3` 不复权 |

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_baostock_adapter.py tests/test_config.py tests/test_akshare_adapter.py
# 26 passed
```

Round 01-03 组合验证：
```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_adapter_factory.py tests/test_akshare_adapter.py tests/test_baostock_adapter.py tests/test_config.py
# 37 passed, 1 warning
```

## Known gotchas

1. **BaoStock 是 optional dep**：生产使用前安装 `pip install 'tradingcat[sentiment_baostock]'`。
2. **本轮不接 factory**：`BaostockConfig.enabled` 目前只是配置入口，不改变实际 market data 路由。
3. **BaoStock 有全局 session 生命周期**：adapter 用 lock 包住每次 `login/query/logout`，避免并发请求互相登出。
4. **Round 03 不处理指数**：`SH000001` / `SZ399001` 仍被拒绝，后续若要指数数据应单独建 index path。
5. **停牌行会被跳过**：`tradestatus != 1` 不产出 `Bar`，避免生成不可交易日价格。
6. **字段全是字符串**：解析失败会跳过该 row，不中断整次拉取。

## Next step → Round 04 (Tushare adapter)

Round 04 进入 P1.3：新增 Tushare adapter。Tushare 需要 token，必须默认 disabled，测试必须注入 fake module/client。

建议任务：
1. 新增 `tradingcat/adapters/cn/tushare.py`。
2. 新增 `TushareConfig(enabled, token, adj, timeout...)`，token 只从 env 读取，不写入仓库。
3. 支持日线 bars；如实现 `daily_basic` 截面或 `fina_indicator` 时序，保持 research-only，不进入交易决策路径。
4. 测试覆盖 token missing、fake query success、empty/error fallback。
5. 暂不改 broker / risk.py / strategies；factory 接入 BaoStock/Tushare 可单独开后续 round。

入口文件：
- [`tradingcat/adapters/cn/akshare.py`](../tradingcat/adapters/cn/akshare.py) — optional SDK + DataFrame 解析参考
- [`tradingcat/adapters/cn/baostock.py`](../tradingcat/adapters/cn/baostock.py) — optional SDK + session lifecycle 参考
- [`tests/test_baostock_adapter.py`](../tests/test_baostock_adapter.py) — fake SDK 测试参考
- [`tradingcat/config.py`](../tradingcat/config.py) — `BaostockConfig` 挂载方式参考

## Commit

```
f4e2ff6 absorb-tradingagents-cn: round 03 — BaoStock A-share market data adapter
```

---

## Roadmap 提醒（来自 plan §10.4）

```
✅ Round 01  P1.1 AKShare adapter
✅ Round 02  P1.1 AdapterFactory composite + 集成
✅ Round 03  P1.2 BaoStock adapter（本轮）
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
