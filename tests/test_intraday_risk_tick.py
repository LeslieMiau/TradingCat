from tradingcat.config import AppConfig, FutuConfig, RiskConfig
from tradingcat.domain.models import PortfolioSnapshot
from tradingcat.main import TradingCatApplication


def _make_app(tmp_path, **config_overrides) -> TradingCatApplication:
    return TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
            risk=RiskConfig(daily_stop_loss=0.02, weekly_drawdown_limit=0.04, no_new_risk_drawdown=0.15),
            **config_overrides,
        )
    )


def test_run_intraday_risk_tick_healthy_portfolio_is_noop(tmp_path):
    app = _make_app(tmp_path)

    result = app.run_intraday_risk_tick()

    assert result["kill_switch_activated"] is False
    assert result["severity"] == "info"
    assert result["breached"] == []
    assert app.risk.kill_switch_status()["enabled"] is False


def test_run_intraday_risk_tick_breach_activates_kill_switch_and_records_alert(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    breaching = PortfolioSnapshot(
        nav=1_000_000.0,
        cash=900_000.0,
        drawdown=0.05,
        daily_pnl=-25_000.0,
        weekly_pnl=0.0,
    )
    monkeypatch.setattr(app.portfolio, "current_snapshot", lambda: breaching)

    result = app.run_intraday_risk_tick()

    assert result["kill_switch_activated"] is True
    assert any(item["rule"] == "daily_stop_loss" for item in result["breached"])
    assert app.risk.kill_switch_status()["enabled"] is True
    alerts = app.alerts.list_alerts()
    assert any(alert.category == "intraday_risk_breach" for alert in alerts)


def test_run_intraday_risk_tick_nav_unavailable_fails_closed(tmp_path, monkeypatch):
    app = _make_app(tmp_path)

    def _broken_snapshot():
        raise RuntimeError("broker degraded")

    monkeypatch.setattr(app.portfolio, "current_snapshot", _broken_snapshot)

    result = app.run_intraday_risk_tick()

    assert result["nav_available"] is False
    assert result["kill_switch_activated"] is True
    assert app.risk.kill_switch_status()["enabled"] is True
    alerts = app.alerts.list_alerts()
    assert any(alert.category == "intraday_risk_nav_unavailable" for alert in alerts)


def test_run_intraday_risk_tick_idempotent_when_kill_switch_already_active(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    app.risk.set_kill_switch(True, reason="prior incident")
    breaching = PortfolioSnapshot(
        nav=1_000_000.0,
        cash=900_000.0,
        drawdown=0.0,
        daily_pnl=-30_000.0,
        weekly_pnl=0.0,
    )
    monkeypatch.setattr(app.portfolio, "current_snapshot", lambda: breaching)

    result = app.run_intraday_risk_tick()

    assert result["kill_switch_activated"] is False
    assert result["kill_switch_already_active"] is True
    alerts_before = len(app.alerts.list_alerts())

    app.run_intraday_risk_tick()
    assert len(app.alerts.list_alerts()) == alerts_before
