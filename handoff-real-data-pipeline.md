# TradingCat Real Data Pipeline Handoff

## Background

TradingCat 的工程基础设施已完成（blocker 对齐、控制面语义、API 合约），但 research readiness 仍为 `false`。原因是 execution strategies (A/B/C) 被真实数据 blocker 阻断。

**当前状态**:
- Futu OpenD 已在本地运行 (`127.0.0.1:11111`, SIMULATE 模式)
- `FutuMarketDataAdapter` 和 `FutuBrokerAdapter` 已完整实现且可连接
- 数据同步管道 (`sync_history`, `repair_history_gaps`) 已实现但从未跑过真实数据
- FX 汇率使用合成正弦波生成器，不是真实市场数据
- Futu OpenD **不支持** forex 代码格式（已验证 `Forex.USDCNH` / `US.USDCNH` 均失败）

**目标**: 让 `GET /ops/readiness` 返回 `research_readiness.ready = true`

---

## Architecture Context

### Adapter Fallback Chain
```
AdapterFactory.create_market_data_adapter()
  → FutuMarketDataAdapter (if enabled + OpenD reachable)
  → YFinanceMarketDataAdapter (fallback)
  → StaticMarketDataAdapter (synthetic, always available)
```

Current config (.env): `TRADINGCAT_FUTU_ENABLED=true`, `SIMULATE`, `127.0.0.1:11111`

### Readiness Flow
```
GET /ops/readiness
  → ReadinessQueryService.operations_readiness()
    ├─ data_quality_summary()        → history coverage ≥ 95%
    ├─ research_readiness_summary()  → all strategies data_ready + not promotion_blocked
    ├─ compliance_summary()          → no blocked items
    └─ execution_readiness()         → state + authorization + alerts
```

### Key Blockers (from PROGRESS.md)
1. Strategy A/B/C 缺公司行为 (corporate actions) 完整性
2. FX 覆盖率不足（合成数据不算真实）
3. 历史 bar 数据未从 OpenD 拉取
4. `data_quality.ready = true` 但 `research_readiness.ready = false`

---

## Task 1: Run Real History Sync via OpenD (Priority: Highest)

### What To Do
调用 `POST /data/history/sync` 触发通过 Futu OpenD 拉取真实 bars + corporate actions。

### Steps
1. 启动服务：`uvicorn tradingcat.main:app --port 8053`
2. 确认适配器是 Futu（不是 Static fallback）：
   ```bash
   curl http://127.0.0.1:8053/broker/status | python -m json.tool
   # 应该看到 backend: "futu"
   ```
3. 运行全量同步：
   ```bash
   curl -X POST http://127.0.0.1:8053/data/history/sync | python -m json.tool
   ```
   - 默认同步最近 30 天所有 catalog 中的 instrument
   - 返回 `reports` (成功) 和 `failures` (失败)
4. 检查覆盖率：
   ```bash
   curl http://127.0.0.1:8053/data/history/coverage | python -m json.tool
   ```
   - 需要 `coverage_ratio ≥ 0.95` 且 `ready = true`
5. 如果覆盖率不足，运行修复：
   ```bash
   curl -X POST http://127.0.0.1:8053/data/history/repair | python -m json.tool
   ```

### Expected Issues
- **行情权限**：SIMULATE 模式下某些标的可能无权限。如果 `failures` 中出现权限错误，需要在 Futu 客户端确认模拟交易行情权限。
- **A 股限制**：CN 市场的 `510300`, `159915`, `300308`, `603986` 在模拟环境可能不可用。
- **数据量**：13 个 instrument × 30 天，预计几分钟完成。

### Key Files
- `tradingcat/services/market_data.py:184-229` — `sync_history()` 实现
- `tradingcat/services/market_data.py:231-318` — `summarize_history_coverage()` (95% 阈值)
- `tradingcat/adapters/futu.py:130-152` — `FutuMarketDataAdapter.fetch_bars()`
- `tradingcat/adapters/futu.py:197-209` — `fetch_corporate_actions()` via `get_rehab()`
- `tradingcat/routes/market_data.py:71` — `POST /data/history/sync` 路由

---

## Task 2: Implement Real FX Rates (Priority: High)

### Problem
`sync_fx_rates()` 使用 `_generate_fx_series()` 生成合成汇率（正弦波 + 锚定基准）。Futu OpenD 不支持 forex 代码，已验证：
- `Forex.USDCNH` → "format of code is wrong"
- `US.USDCNH` → "Unknown stock"
- `HK.USDCNH` → "Unknown stock"

### Recommended Approach: 中国人民银行 / exchangerate.host

**Option A: exchangerate.host (简单, 免费)**
```python
# 在 tradingcat/adapters/ 新增 fx_adapter.py
import urllib.request
import json
from datetime import date
from tradingcat.domain.models import FxRate

class ExchangeRateAdapter:
    _BASE_URL = "https://api.exchangerate.host"

    def fetch_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        url = f"{self._BASE_URL}/timeseries?start_date={start}&end_date={end}&base={quote_currency}&symbols={base_currency}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        rates = []
        for date_str, values in sorted(data.get("rates", {}).items()):
            rate_value = values.get(base_currency)
            if rate_value:
                rates.append(FxRate(
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    date=date.fromisoformat(date_str),
                    rate=round(float(rate_value), 6),
                ))
        return rates
```

**Option B: 央行数据 (最权威, 免费)**
- URL: `https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcsrHisByDate`
- 返回 CNY 对主要货币的中间价
- 适合 CNY 为 base_currency 的场景

### Integration Point
`tradingcat/services/market_data.py:489-517` — `sync_fx_rates()` 方法已改造为优先调用 `self._adapter.fetch_fx_rates()`，找不到时 fallback 到合成生成器。

**已完成的准备工作**:
- `MarketDataAdapter` protocol 已添加 `fetch_fx_rates()` 方法 (`adapters/base.py:26`)
- `sync_fx_rates()` 已改为 adapter-first + synthetic-fallback (`services/market_data.py:489-517`)
- `StaticMarketDataAdapter`, `YFinanceMarketDataAdapter`, `FutuMarketDataAdapter` 都已添加空 `fetch_fx_rates()` 实现
- 返回结果新增 `source` 字段标识数据来源 ("adapter" vs "synthetic")

### What's Left To Implement
1. 创建 `tradingcat/adapters/fx_adapter.py` — 实现 `ExchangeRateAdapter`（或央行适配器）
2. 在 `tradingcat/adapters/factory.py` 或 `tradingcat/runtime.py` 中注入 FX 适配器
3. 修改 `MarketDataService.__init__()` 接受可选的 FX 适配器，在 `sync_fx_rates()` 中优先使用

**或者更简单的方案**:
直接在 `FutuMarketDataAdapter.fetch_fx_rates()` 中调用外部 API（不需要新适配器）。由于 `sync_fx_rates()` 已经会调用 `self._adapter.fetch_fx_rates()`，只需让 Futu 适配器内部 HTTP 调用 exchangerate.host 即可。

### Key Files
- `tradingcat/adapters/base.py:26` — `fetch_fx_rates()` 协议方法（**已添加**）
- `tradingcat/adapters/futu.py:210-212` — Futu 的空 `fetch_fx_rates()`（待实现真实调用）
- `tradingcat/services/market_data.py:489-517` — `sync_fx_rates()`（**已改造**）
- `tradingcat/services/market_data.py:701-737` — `_generate_fx_series()` 合成生成器（fallback）

---

## Task 3: Validate & Fix Research Readiness (Priority: High)

### Steps
在 Task 1 和 Task 2 完成后：

1. 检查研究就绪状态：
   ```bash
   curl http://127.0.0.1:8053/ops/readiness | python -m json.tool
   ```
2. 对照 `research_readiness.strategies` 数组，逐个检查每个策略的 `blocking_reasons`
3. 如果仍有 blocker：
   - 历史覆盖不足 → 再跑 `POST /data/history/sync` 扩大日期范围
   - 公司行为缺失 → 确认 `include_corporate_actions=true`（默认已开启）
   - FX 缺失 → 确认 `POST /data/fx/sync` 已跑且 `source = "adapter"`

### Research Readiness Logic
**File**: `tradingcat/services/query_services.py:169-211`

```python
blocked_strategy_ids = [
    strategy for strategy in strategies
    if bool(strategy.get("promotion_blocked"))
]
ready = not bool(blocked_strategy_ids)
```

每个策略的 `promotion_blocked` 由 `strategy_experiments.inspect_strategy_readiness()` 计算，检查：
- 策略依赖的所有 symbol 是否有足够历史覆盖
- 公司行为是否完整
- FX 汇率是否可用

---

## Task 4: Handle Permission / Availability Failures (Priority: Medium)

### 可能的问题

**如果部分标的在 SIMULATE 模式下无权限**：
1. 在 catalog 中将无权限标的标记为 `enabled=false`：
   ```bash
   curl -X POST http://127.0.0.1:8053/instruments/upsert \
     -H "Content-Type: application/json" \
     -d '[{"symbol": "300308", "market": "CN", "enabled": false}]'
   ```
2. 或者从策略依赖中排除这些标的（需要修改策略配置）

**如果 A 股完全不可用**：
- CN 市场在 Futu 模拟环境中权限受限
- 可能需要暂时只关注 US + HK 市场
- 检查 `tradingcat/strategies/simple.py` 中策略 A/B/C 的标的依赖

---

## Verification Checklist

完成所有任务后，按顺序验证：

1. `GET /broker/status` → `backend: "futu"`, `healthy: true`
2. `GET /data/history/coverage` → `ready: true`, `coverage_ratio ≥ 0.95`
3. `GET /data/history/corporate-actions` → `missing_symbols: []`
4. `GET /data/fx/coverage` → `ready: true`, `missing_quote_currencies: []`
5. `GET /ops/readiness` → `research_readiness.ready: true`
6. `GET /preflight/startup` → `healthy: true`

### Regression Tests
```bash
.venv/bin/pytest tests/test_api.py tests/test_service_health.py tests/test_runtime_recovery.py -q
```
已确认 223 passed（3 个 pre-existing failure 不相关: test_persistence, test_risk × 2）

---

## Files Modified (Already Committed / Ready to Commit)

| File | Change | Status |
|------|--------|--------|
| `tradingcat/adapters/base.py` | Added `fetch_fx_rates()` to `MarketDataAdapter` protocol | Done |
| `tradingcat/adapters/futu.py` | Added stub `fetch_fx_rates()`, imported `FxRate` | Done |
| `tradingcat/adapters/market.py` | Added stub `fetch_fx_rates()` to `StaticMarketDataAdapter` | Done |
| `tradingcat/adapters/yfinance_adapter.py` | Added stub `fetch_fx_rates()` | Done |
| `tradingcat/services/market_data.py` | `sync_fx_rates()` now tries adapter first, falls back to synthetic | Done |
| `tradingcat/adapters/fx_adapter.py` | **NEW** — Real FX data adapter | **TODO** |
| `tradingcat/runtime.py` | Wire FX adapter into service | **TODO** |

## Out of Scope

- 回测引擎验证（后续任务）
- Paper-trading 实盘运行（需要 wall-clock time）
- 策略参数调优
- 切换 SIMULATE → REAL 模式
- DuckDB / PostgreSQL 后端迁移
