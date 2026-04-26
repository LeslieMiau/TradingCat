from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventType(Enum):
    QUOTE = auto()
    ORDER_UPDATE = auto()
    POSITION_UPDATE = auto()
    RISK_ALERT = auto()
    TRADE = auto()
    CONNECTION_STATUS = auto()


@dataclass
class Event:
    type: EventType
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "realtime"


class EventBus:
    """In-process pub/sub for intraday events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def publish(self, event: Event) -> None:
        with self._lock:
            cbs = list(self._subscribers.get(event.type, []))
        for cb in cbs:
            try:
                cb(event)
            except Exception:
                logger.exception("EventBus callback failed for %s", event.type)

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()


class IntradayRiskConfig:
    def __init__(self) -> None:
        self.max_price_deviation_pct = 0.05
        self.max_volume_surge_ratio = 5.0
        self.cooldown_seconds = 300


class IntradayRiskMonitor:
    """Monitor real-time prices and trigger risk alerts."""

    def __init__(self, event_bus: EventBus, config: IntradayRiskConfig | None = None) -> None:
        self._bus = event_bus
        self._config = config or IntradayRiskConfig()
        self._ref_prices: dict[str, float] = {}
        self._avg_volumes: dict[str, float] = {}
        self._last_alert: dict[str, datetime] = {}
        self._bus.subscribe(EventType.QUOTE, self._on_quote)

    def set_reference_price(self, symbol: str, price: float) -> None:
        self._ref_prices[symbol] = price

    def _on_quote(self, event: Event) -> None:
        symbol = event.data.get("symbol", "")
        price = event.data.get("price")
        vol = event.data.get("volume", 0)
        if price is None:
            return
        msgs = []
        ref = self._ref_prices.get(symbol)
        if ref and ref > 0:
            dev = abs(price - ref) / ref
            if dev > self._config.max_price_deviation_pct and self._can_alert(symbol):
                msgs.append(f"{symbol} price {price:.2f} dev {dev*100:.1f}% from ref {ref:.2f}")
        avg = self._avg_volumes.get(symbol)
        if avg and avg > 0 and vol > avg * self._config.max_volume_surge_ratio and self._can_alert(f"{symbol}_v"):
            msgs.append(f"{symbol} vol {vol} is {vol/avg:.1f}x avg {avg:.0f}")
        for m in msgs:
            self._bus.publish(Event(EventType.RISK_ALERT, {"symbol": symbol, "message": m, "price": price}))
            logger.warning("RISK: %s", m)

    def _can_alert(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        last = self._last_alert.get(key)
        if last and (now - last).total_seconds() < self._config.cooldown_seconds:
            return False
        self._last_alert[key] = now
        return True

    def close(self) -> None:
        self._bus.unsubscribe(EventType.QUOTE, self._on_quote)
