# Round 02 — P1.1 AdapterFactory Composite MarketDataAdapter

**Status**: ✅ Done · 2026-04-25

## Goal

把 Round 01 新增的 `AkshareMarketDataAdapter` 接进实际 market data 创建路径。
本轮只改 market data adapter wiring：当 `TRADINGCAT_AKSHARE_ENABLED=false` 时，factory 行为保持原样；
当显式启用且 AKShare SDK 可用时，CN instrument 优先走 AKShare，US/HK 和 fallback 仍走既有 Futu/YFinance/Static 链。

## Done

### 新增文件
- [`tradingcat/adapters/composite.py`](../tradingcat/adapters/composite.py) — `CompositeMarketDataAdapter`
  - `fetch_bars`：`Instrument.market == CN` 时先走 AKShare；非 CN 直接走 inner adapter。
  - fallback：AKShare 抛 `AkshareUnavailable`、其他异常、或返回空 bars 时，回退到 inner adapter。
  - `fetch_quotes`：按 CN / 非 CN 分组；CN 走 AKShare，非 CN 走 inner，再合并结果。
  - CN quotes 空结果或缺失 symbol 时，用 inner adapter 补齐。
  - `fetch_option_chain` / `fetch_corporate_actions` / `fetch_fx_rates`：直接转发给 inner adapter。

### 修改文件
- [`tradingcat/adapters/factory.py`](../tradingcat/adapters/factory.py)
  - `create_market_data_adapter` 先按原顺序选择 Futu → YFinance → Static。
  - 仅当 `config.akshare.enabled and AKSHARE_AVAILABLE` 时，才用 `CompositeMarketDataAdapter` 包住当前 adapter。
  - AKShare SDK 不可用或初始化失败时，保持当前 adapter，不影响启动。
  - broker 创建路径未改。
- [`tests/test_adapter_factory.py`](../tests/test_adapter_factory.py)
  - 覆盖 Akshare disabled 时不初始化且返回原 Static adapter。
  - 覆盖 Akshare enabled + available 时返回 composite，CN bars/quotes 走 AKShare，US quotes 走 inner。
  - 覆盖 AKShare 返回空和抛 `AkshareUnavailable` 时 fallback 到 inner。

## Verification

```bash
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/test_adapter_factory.py tests/test_akshare_adapter.py
# 25 passed, 1 warning
```

备注：直接用系统 Python 跑同一命令会因未安装既有 optional dependency `yfinance` 在 collection 阶段失败；
README 建议使用 repo `.venv/bin/pytest`，上面的验证使用了该虚拟环境。

## Known gotchas

1. **默认仍关闭**：`AkshareConfig.enabled` 默认 `False`，disabled 时 factory 不会 import-time 初始化 AKShare adapter。
2. **Composite 只接 market data**：broker / risk / strategies 未改，AI/研究能力仍不进入交易决策路径。
3. **AKShare 空数据不是成功**：CN bars 返回 `[]` 时会 fallback 到 inner，避免 history sync 被空结果截断。
4. **CN index labels 仍由 inner 兜底**：`AkshareMarketDataAdapter` 会拒绝 `SH000001` 这类标签，Composite 会 fallback。
5. **quotes 是部分 fallback**：AKShare 若只返回部分 CN symbols，缺失或非正价格会由 inner adapter 补齐。

## Next step → Round 03 (BaoStock adapter)

Round 03 进入 P1.2：新增 BaoStock adapter，作为中国市场免费数据 fallback。

建议任务：
1. 新增 `tradingcat/adapters/cn/baostock.py`，保持 optional dependency 和 fake-module 测试方式。
2. 支持 A 股日线 bars，注意 BaoStock 需要 login/logout 生命周期，测试里必须避免真实网络。
3. 新增 `BaostockConfig`，默认 disabled。
4. 暂不改 broker / risk.py / strategies。
5. 如要接入 factory，应在 Round 04 或后续单独做，不要和 adapter 实现混在一起。

入口文件：
- [`tradingcat/adapters/cn/akshare.py`](../tradingcat/adapters/cn/akshare.py) — Round 01 optional adapter 模式参考
- [`tests/test_akshare_adapter.py`](../tests/test_akshare_adapter.py) — fake SDK 测试模式参考
- [`tradingcat/config.py`](../tradingcat/config.py) — `AkshareConfig` 挂载方式参考

## Commit

```
TBD
```

---

## Roadmap 提醒（来自 plan §10.4）

```
✅ Round 01  P1.1 AKShare adapter
✅ Round 02  P1.1 AdapterFactory composite + 集成（本轮）
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
