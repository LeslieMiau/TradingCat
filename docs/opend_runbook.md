# OpenD 宿主恢复手册

**目标**：当 OpenD 连接异常时，在 15 分钟内恢复到可下单的稳定状态，且不丢失执行/审计状态。

**适用范围**：单机部署（富途 OpenD + TradingCat）；香港/美股/A 股的仿真或实盘账户。

---

## 0. 触发条件（任一即进入本 runbook）

- `/health/opend` 或 `scripts/opend_check.sh` 返回非零退出码
- `/alerts` 出现 `category="broker"` 或 `category="opend"` 的 `error` 级事件
- Dashboard `/diagnostics` 显示 `opend_online=false` 超过 2 个检查周期
- 盘中风控 tick 触发 `fail-closed`，原因含 `NAV unavailable`
- Kill switch 自动启用，最新事件 `reason` 以 `"Intraday tick"` 开头

---

## 1. 现场评估（2 分钟）

1. `bash scripts/opend_check.sh`  → 看 `sdk_import` / `tcp_connect` / `mode` 哪个失败。
2. `GET /alerts?limit=20` → 截取最近告警时间戳与类别。
3. `GET /portfolio/risk-state` → 确认 kill switch 状态（若未启用，按需手动启用避免盲下单）。
4. 记录 TCP 失败/SDK 失败/登录失败三类中具体哪一类。

**如果 kill switch 未启用且下单通道不确定**：先 `POST /kill-switch/enable` 再继续诊断，宁可多停一会儿。

---

## 2. 恢复步骤（按故障类型）

### 2.1 TCP 不通 (`tcp_connect.ok=false`)

1. 确认 OpenD 进程：`ps aux | grep -i opend`
2. 若无：启动富途 OpenD 客户端，等待登录指示灯变绿（约 30-60 秒）
3. 若有但仍不通：kill OpenD 进程后重启（OpenD 偶发 socket stuck）
4. 重试 `bash scripts/opend_check.sh`，期望三项全绿
5. 继续第 3 节

### 2.2 SDK 失败 (`sdk_import.ok=false`)

1. `source .venv/bin/activate && pip install futu-api`
2. 重启 TradingCat：`pkill -f uvicorn` → `bash init.sh`
3. 继续第 3 节

### 2.3 登录/账户异常（连得上但下单失败）

1. 打开富途客户端，重新输入交易密码解锁
2. 若提示设备未授权：在客户端解绑旧设备，重新绑定
3. 若实盘环境：检查账户状态是否被券商风控限制
4. 调用 `POST /broker/validate` → 期望返回 `status="ok"`
5. 继续第 3 节

---

## 3. 运行时恢复调用顺序（4 分钟）

严格按顺序执行，**每步必须看到 HTTP 200 + 预期字段**才能进入下一步：

| 步骤 | 端点 | 预期 |
|---|---|---|
| 1 | `GET /health/opend` | `status=="ok"` |
| 2 | `GET /portfolio/snapshot` | `nav>0`、`cash_by_market` 非空 |
| 3 | `POST /execution/reconcile` | `duplicate_fills=0`、`unmatched_broker_orders=[]` |
| 4 | `POST /portfolio/reconcile` | `cash_difference` 在容忍带 (±1%) 之内 |
| 5 | `GET /portfolio/risk-state` | `fail_closed=false`，若仍 fail-closed 回到第 2 节 |
| 6 | `POST /kill-switch/disable`（需人工确认） | `enabled=false` |
| 7 | `POST /ops/evaluate-triggers` | 新一轮信号产出，观察日志无 RiskViolation |

**不要跳过第 3、4 步**——断线期间的缺失成交必须在恢复后的第一次对账里被补回；漏掉一次会把 reconciliation 差异带到下一个交易日。

---

## 4. 验证（3 分钟）

- `GET /ops/acceptance/gates`
  - `gates.reconciliation.status == "pass"`
  - `gates.kill_switch_latency.status != "fail"`
- `GET /ops/readiness` → `ready=true`
- `GET /audit/summary?limit=10` → 最近 10 条无 `status="error"`
- 在 `/alerts` 确认恢复事件已写入，便于事后复盘

---

## 5. 事后动作（6 分钟，可异步）

1. **运营日志**：`POST /ops/journal/record`，附 `notes={"incident": "opend_recovery", "downtime_minutes": N}`
2. **Post-mortem**：`GET /ops/postmortem?window_days=1` 导出最近 24 小时事件链
3. 若停机时间 > 15 分钟：暂停本日新开仓，等待第二交易日再恢复，或留 ops owner 手工复核
4. 在 `docs/` 追加一行事故时间线，供季度复盘

---

## 6. 放弃阈值（何时不再尝试修复）

出现任一情况，**立即** `POST /kill-switch/enable` 并通知 ops owner：

- 累计停机时间 > 30 分钟
- `POST /execution/reconcile` 返回 `duplicate_fills>0` 或 `unmatched_broker_orders` 非空且无法解释
- 券商账户被标记为风控限制或冻结
- 当日是 FOMC / CPI / 港美股季报日，且信心度低于 60%

放弃后走人工下单 + 事后补录流程（`POST /reconcile/manual-fill`），而不是继续让自动化裸奔。

---

## 附录 A · 关键命令速查

```bash
# 诊断
bash scripts/opend_check.sh
bash scripts/doctor.sh

# 强停 / 重启
pkill -f uvicorn
bash init.sh

# 一次性健康链（按顺序）
curl -sf localhost:8000/health/opend
curl -sf -X POST localhost:8000/execution/reconcile
curl -sf -X POST localhost:8000/portfolio/reconcile
curl -sf localhost:8000/ops/acceptance/gates | python -m json.tool
```

## 附录 B · 相关代码/配置

- 健康检查：[tradingcat/routes/market_data.py](tradingcat/routes/market_data.py)、[scripts/opend_check.sh](scripts/opend_check.sh)
- Fail-closed 实现：[tradingcat/services/risk.py](tradingcat/services/risk.py:148)
- 成交对账：[tradingcat/services/reconciliation.py](tradingcat/services/reconciliation.py)、[tradingcat/services/execution.py](tradingcat/services/execution.py:136)
- 告警分派：[tradingcat/services/alerts.py](tradingcat/services/alerts.py)、[tradingcat/services/notifier.py](tradingcat/services/notifier.py)
- 验收门槛：[tradingcat/services/acceptance_gates.py](tradingcat/services/acceptance_gates.py)
