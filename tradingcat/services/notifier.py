from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from tradingcat.domain.models import AlertEvent


logger = logging.getLogger(__name__)

_SEVERITY_ORDER: dict[str, int] = {"info": 0, "warning": 1, "error": 2, "critical": 3}


def _severity_rank(severity: str) -> int:
    return _SEVERITY_ORDER.get(severity.lower(), 0)


def _format_alert_text(alert: AlertEvent) -> str:
    lines = [
        f"[{alert.severity.upper()}] {alert.category}",
        alert.message,
    ]
    if alert.recovery_action:
        lines.append(f"Action: {alert.recovery_action}")
    if alert.details:
        lines.append("Details: " + json.dumps(alert.details, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


class NotifierChannel(Protocol):
    name: str

    def send(self, alert: AlertEvent) -> bool: ...


@dataclass
class TelegramNotifier:
    bot_token: str
    chat_id: str
    timeout: float = 5.0
    name: str = "telegram"

    def send(self, alert: AlertEvent) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({"chat_id": self.chat_id, "text": _format_alert_text(alert)}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            logger.warning("Telegram notifier delivery failed: %s", exc)
            return False


@dataclass
class EmailNotifier:
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_addr: str
    to_addrs: list[str]
    use_tls: bool = True
    timeout: float = 5.0
    name: str = "email"

    def send(self, alert: AlertEvent) -> bool:
        if not self.to_addrs:
            return False
        message = EmailMessage()
        message["From"] = self.from_addr
        message["To"] = ", ".join(self.to_addrs)
        message["Subject"] = f"[{alert.severity.upper()}] TradingCat: {alert.category}"
        message.set_content(_format_alert_text(alert))
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout) as client:
                if self.use_tls:
                    client.starttls()
                if self.username:
                    client.login(self.username, self.password)
                client.send_message(message)
            return True
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("Email notifier delivery failed: %s", exc)
            return False


@dataclass
class _ThrottleEntry:
    last_dispatched_at: datetime
    last_severity_rank: int


@dataclass
class AlertDispatcher:
    """Dispatches alerts to configured channels with per-category cooldown.

    A repeat alert in the same category within `cooldown_seconds` is suppressed,
    *unless* its severity is strictly higher than the last-dispatched severity for
    that category — escalations always punch through so operators never miss a
    warning-to-error upgrade.
    """

    channels: list[NotifierChannel] = field(default_factory=list)
    min_severity: str = "error"
    cooldown_seconds: int = 900
    _last_dispatch: dict[str, _ThrottleEntry] = field(default_factory=dict, repr=False)
    _suppressed_counts: dict[str, int] = field(default_factory=dict, repr=False)

    def dispatch(self, alert: AlertEvent, *, now: datetime | None = None) -> dict[str, bool | str]:
        if _severity_rank(alert.severity) < _severity_rank(self.min_severity):
            return {}
        moment = now or datetime.now(UTC)
        severity_rank = _severity_rank(alert.severity)
        entry = self._last_dispatch.get(alert.category)
        if entry is not None and self.cooldown_seconds > 0:
            cooled = moment - entry.last_dispatched_at < timedelta(seconds=self.cooldown_seconds)
            escalation = severity_rank > entry.last_severity_rank
            if cooled and not escalation:
                self._suppressed_counts[alert.category] = self._suppressed_counts.get(alert.category, 0) + 1
                return {"throttled": True}
        results: dict[str, bool | str] = {}
        for channel in self.channels:
            try:
                results[channel.name] = bool(channel.send(alert))
            except Exception as exc:
                logger.exception("Notifier channel %s raised: %s", channel.name, exc)
                results[channel.name] = False
        self._last_dispatch[alert.category] = _ThrottleEntry(
            last_dispatched_at=moment,
            last_severity_rank=severity_rank,
        )
        suppressed = self._suppressed_counts.pop(alert.category, 0)
        if suppressed:
            results["suppressed_since_last"] = str(suppressed)
        return results

    def suppressed_counts(self) -> dict[str, int]:
        return dict(self._suppressed_counts)


def build_default_dispatcher(
    *,
    telegram_bot_token: str = "",
    telegram_chat_id: str = "",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_username: str = "",
    smtp_password: str = "",
    email_from: str = "",
    email_to: list[str] | None = None,
    min_severity: str = "error",
    cooldown_seconds: int = 900,
) -> AlertDispatcher | None:
    channels: list[NotifierChannel] = []
    if telegram_bot_token and telegram_chat_id:
        channels.append(TelegramNotifier(bot_token=telegram_bot_token, chat_id=telegram_chat_id))
    if smtp_host and email_from and email_to:
        channels.append(
            EmailNotifier(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                username=smtp_username,
                password=smtp_password,
                from_addr=email_from,
                to_addrs=list(email_to),
            )
        )
    if not channels:
        return None
    return AlertDispatcher(channels=channels, min_severity=min_severity, cooldown_seconds=cooldown_seconds)
