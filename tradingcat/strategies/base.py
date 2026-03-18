from __future__ import annotations

from datetime import date
from typing import Protocol

from tradingcat.domain.models import Signal


class Strategy(Protocol):
    strategy_id: str

    def generate_signals(self, as_of: date) -> list[Signal]: ...

