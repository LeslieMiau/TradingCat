"""Stage A acceptance: inject 3 failure modes against an in-memory app and assert hardening behaves.

Scenarios:
  1. Duplicate fill replay (same broker deal_id) -> reconciliation must dedup.
  2. Drawdown lockout breach -> intraday risk tick must activate kill switch and record alert.
  3. NAV/snapshot fetch failure -> intraday risk tick must fail closed and record alert.

Run:
    python scripts/stage_a_fault_injection.py
Exits non-zero on any scenario failure.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from tradingcat.config import AppConfig, FutuConfig, RiskConfig
from tradingcat.domain.models import (
    AssetClass,
    ExecutionReport,
    Instrument,
    Market,
    OrderSide,
    OrderStatus,
    PortfolioSnapshot,
)
from tradingcat.main import TradingCatApplication
from tradingcat.services.execution import OrderStateMachine
from tradingcat.services.reconciliation import ReconciliationService


GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def _ok(label: str) -> None:
    print(f"{GREEN}PASS{RESET} {label}")


def _fail(label: str, detail: str) -> None:
    print(f"{RED}FAIL{RESET} {label}: {detail}")


def _build_app() -> TradingCatApplication:
    tmp = Path(tempfile.mkdtemp(prefix="stage-a-fault-"))
    return TradingCatApplication(
        config=AppConfig(
            data_dir=tmp,
            futu=FutuConfig(enabled=False),
            risk=RiskConfig(daily_stop_loss=0.02, weekly_drawdown_limit=0.04, no_new_risk_drawdown=0.15),
        )
    )


def _instrument() -> Instrument:
    return Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")


def scenario_duplicate_fill_dedup() -> bool:
    label = "duplicate fill replay is deduplicated by deal_id"
    reconciliation = ReconciliationService(OrderStateMachine())
    fill_a = ExecutionReport(
        order_id="order-1",
        instrument=_instrument(),
        side=OrderSide.BUY,
        quantity=10.0,
        average_price=400.0,
        status=OrderStatus.FILLED,
        broker_order_id="BROKER-1",
        fill_id="DEAL-XYZ",
    )
    fill_b = ExecutionReport(
        order_id="order-1",
        instrument=_instrument(),
        side=OrderSide.BUY,
        quantity=10.0,
        average_price=400.0,
        status=OrderStatus.FILLED,
        broker_order_id="BROKER-1",
        fill_id="DEAL-XYZ",
    )

    print_a = reconciliation.fill_fingerprint(fill_a)
    print_b = reconciliation.fill_fingerprint(fill_b)
    same = print_a == print_b
    has_deal_id = print_a.startswith("fill:DEAL-XYZ")

    if same and has_deal_id:
        _ok(label)
        return True
    _fail(label, f"fingerprint_a={print_a}, fingerprint_b={print_b}, has_deal_id={has_deal_id}")
    return False


def scenario_drawdown_breach_activates_kill_switch() -> bool:
    label = "drawdown breach activates kill switch and records alert"
    app = _build_app()

    breach = PortfolioSnapshot(nav=1_000_000.0, cash=900_000.0, drawdown=0.20, daily_pnl=0.0, weekly_pnl=0.0)
    app.portfolio.current_snapshot = lambda: breach  # type: ignore[method-assign]

    result = app.run_intraday_risk_tick()
    kill_active = app.risk.kill_switch_status()["enabled"]
    breach_alert = any(alert.category == "intraday_risk_breach" for alert in app.alerts.list_alerts())

    if result["kill_switch_activated"] and kill_active and breach_alert:
        _ok(label)
        return True
    _fail(label, f"result={result}, kill_active={kill_active}, breach_alert={breach_alert}")
    return False


def scenario_nav_unavailable_fails_closed() -> bool:
    label = "NAV snapshot failure fails closed and records alert"
    app = _build_app()

    def _broken() -> PortfolioSnapshot:
        raise RuntimeError("OpenD unreachable")

    app.portfolio.current_snapshot = _broken  # type: ignore[method-assign]

    result = app.run_intraday_risk_tick()
    kill_active = app.risk.kill_switch_status()["enabled"]
    alert_recorded = any(alert.category == "intraday_risk_nav_unavailable" for alert in app.alerts.list_alerts())

    if (not result["nav_available"]) and result["kill_switch_activated"] and kill_active and alert_recorded:
        _ok(label)
        return True
    _fail(label, f"result={result}, kill_active={kill_active}, alert_recorded={alert_recorded}")
    return False


def main() -> int:
    print("Stage A fault injection")
    print("=" * 50)
    results = [
        scenario_duplicate_fill_dedup(),
        scenario_drawdown_breach_activates_kill_switch(),
        scenario_nav_unavailable_fails_closed(),
    ]
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"{passed}/{total} scenarios passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
