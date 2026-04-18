from dataclasses import dataclass, field

from tradingcat.config import AppConfig, FutuConfig, NotifierConfig
from tradingcat.domain.models import AlertEvent
from tradingcat.main import TradingCatApplication
from tradingcat.services.alerts import AlertService
from tradingcat.services.notifier import AlertDispatcher


@dataclass
class _RecordingChannel:
    name: str = "recording"
    delivered: list[AlertEvent] = field(default_factory=list)
    succeed: bool = True

    def send(self, alert: AlertEvent) -> bool:
        self.delivered.append(alert)
        return self.succeed


def _alert(severity: str = "error", category: str = "test") -> AlertEvent:
    return AlertEvent(severity=severity, category=category, message="hi")


def test_dispatcher_skips_below_min_severity():
    channel = _RecordingChannel()
    dispatcher = AlertDispatcher(channels=[channel], min_severity="error")

    dispatcher.dispatch(_alert(severity="info"))
    dispatcher.dispatch(_alert(severity="warning"))

    assert channel.delivered == []


def test_dispatcher_delivers_at_or_above_threshold():
    channel = _RecordingChannel()
    dispatcher = AlertDispatcher(channels=[channel], min_severity="warning")

    dispatcher.dispatch(_alert(severity="warning", category="a"))
    dispatcher.dispatch(_alert(severity="error", category="b"))
    dispatcher.dispatch(_alert(severity="critical", category="c"))

    assert [alert.category for alert in channel.delivered] == ["a", "b", "c"]


def test_dispatcher_continues_when_channel_raises():
    failing = _RecordingChannel(name="failing")
    good = _RecordingChannel(name="good")

    def boom(_: AlertEvent) -> bool:
        raise RuntimeError("network down")

    failing.send = boom  # type: ignore[method-assign]
    dispatcher = AlertDispatcher(channels=[failing, good], min_severity="info")

    results = dispatcher.dispatch(_alert(severity="error"))

    assert results == {"failing": False, "good": True}
    assert len(good.delivered) == 1


def test_alert_service_invokes_dispatcher_on_record(tmp_path):
    from tradingcat.repositories.state import AlertRepository

    channel = _RecordingChannel()
    dispatcher = AlertDispatcher(channels=[channel], min_severity="info")
    repository = AlertRepository(AppConfig(data_dir=tmp_path))
    service = AlertService(repository, dispatcher=dispatcher)

    service.record(severity="error", category="scheduler_job_failed", message="sync crashed")

    assert len(channel.delivered) == 1
    assert channel.delivered[0].category == "scheduler_job_failed"


def test_application_builds_no_dispatcher_when_notifier_config_empty(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )

    assert app.alerts._dispatcher is None  # type: ignore[attr-defined]


def test_application_builds_telegram_dispatcher_when_configured(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
            notifier=NotifierConfig(telegram_bot_token="t", telegram_chat_id="c"),
        )
    )

    assert app.alerts._dispatcher is not None  # type: ignore[attr-defined]
    assert any(ch.name == "telegram" for ch in app.alerts._dispatcher.channels)  # type: ignore[attr-defined]
