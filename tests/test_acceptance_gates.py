from datetime import datetime, timedelta

from tradingcat.config import AppConfig, FutuConfig, RiskConfig
from tradingcat.domain.models import KillSwitchEvent, PortfolioSnapshot
from tradingcat.main import TradingCatApplication
from tradingcat.services.acceptance_gates import (
    EXCEPTION_RATE_THRESHOLD,
    KILL_SWITCH_LATENCY_SECONDS,
    SLIPPAGE_BPS_THRESHOLD,
    compute_acceptance_gates,
)


def test_compute_gates_all_green_when_inputs_clean():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 100, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        kill_switch_events=[
            KillSwitchEvent(
                enabled=True,
                detected_at=datetime(2026, 4, 18, 10, 0, 0),
                changed_at=datetime(2026, 4, 18, 10, 0, 30),
            )
        ],
    )
    assert result["status"] == "pass"
    assert result["gates"]["slippage"]["status"] == "pass"
    assert result["gates"]["exception_rate"]["status"] == "pass"
    assert result["gates"]["reconciliation"]["status"] == "pass"
    assert result["gates"]["kill_switch_latency"]["status"] == "pass"
    assert result["thresholds"]["slippage_bps"] == SLIPPAGE_BPS_THRESHOLD
    assert result["thresholds"]["exception_rate"] == EXCEPTION_RATE_THRESHOLD
    assert result["thresholds"]["kill_switch_latency_seconds"] == KILL_SWITCH_LATENCY_SECONDS


def test_compute_gates_flag_slippage_breach():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 2},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["slippage"]["status"] == "fail"


def test_compute_gates_flag_exception_rate_breach():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 100, "exception_count": 5},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["exception_rate"]["status"] == "fail"
    assert result["gates"]["exception_rate"]["metric"]["observed_ratio"] == 0.05


def test_compute_gates_flag_reconciliation_diff():
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 1, "unmatched_broker_orders": ["BR-1"]},
        kill_switch_events=[],
    )
    assert result["status"] == "fail"
    assert result["gates"]["reconciliation"]["status"] == "fail"
    assert result["gates"]["reconciliation"]["metric"]["unmatched_broker_orders"] == 1


def test_compute_gates_flag_kill_latency_breach():
    slow = KillSwitchEvent(
        enabled=True,
        detected_at=datetime(2026, 4, 18, 10, 0, 0),
        changed_at=datetime(2026, 4, 18, 10, 5, 0),
    )
    result = compute_acceptance_gates(
        execution_quality={"equity_samples": 5, "equity_breaches": 0},
        audit_metrics={"cycle_count": 10, "exception_count": 0},
        reconciliation={"duplicate_fills": 0, "unmatched_broker_orders": []},
        kill_switch_events=[slow],
    )
    assert result["status"] == "fail"
    assert result["gates"]["kill_switch_latency"]["status"] == "fail"
    assert result["gates"]["kill_switch_latency"]["metric"]["max_seconds"] == 300.0


def test_compute_gates_pending_when_no_samples():
    result = compute_acceptance_gates()
    # Reconciliation with no data = no diffs; the other three are pending.
    assert result["gates"]["slippage"]["status"] == "pending"
    assert result["gates"]["exception_rate"]["status"] == "pending"
    assert result["gates"]["kill_switch_latency"]["status"] == "pending"
    assert result["gates"]["reconciliation"]["status"] == "pass"
    assert result["status"] == "pending"


def test_app_acceptance_gates_records_latency_on_intraday_tick(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
            risk=RiskConfig(no_new_risk_drawdown=0.15),
        )
    )
    breach = PortfolioSnapshot(nav=1_000_000.0, cash=900_000.0, drawdown=0.20, daily_pnl=0.0, weekly_pnl=0.0)
    app.portfolio.current_snapshot = lambda: breach  # type: ignore[method-assign]

    app.run_intraday_risk_tick()
    gates = app.acceptance_gates()

    latency_gate = gates["gates"]["kill_switch_latency"]
    assert latency_gate["metric"]["sampled_events"] >= 1
    assert latency_gate["status"] in {"pass", "fail"}
    # Either way, a latency number should be present.
    assert "max_seconds" in latency_gate["metric"]
