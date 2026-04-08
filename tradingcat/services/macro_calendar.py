from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from tradingcat.config import AppConfig


class MacroEvent(BaseModel):
    id: str
    time: str
    country: str
    event: str
    impact: str  # HIGH, MEDIUM, LOW
    forecast: str
    previous: str


class MacroCalendarService:
    def __init__(self, _config: AppConfig | None = None) -> None:
        self._config = _config

    def fetch_upcoming_events(self, days: int = 7) -> list[MacroEvent]:
        # TODO: Connect this fixture set to a real macro calendar data source.
        now = datetime.now(timezone.utc)
        
        events = [
            MacroEvent(
                id="evt1",
                time=(now - timedelta(days=2)).strftime("%Y-%m-%dT10:00:00Z"),
                country="US",
                event="Non Farm Payrolls",
                impact="High",
                forecast="180K",
                previous="210K"
            ),
            MacroEvent(
                id="evt2",
                time=(now - timedelta(days=5)).strftime("%Y-%m-%dT08:30:00Z"),
                country="US",
                event="CPI y/y",
                impact="High",
                forecast="3.1%",
                previous="3.2%"
            ),
            MacroEvent(
                id="evt3",
                time=(now + timedelta(days=1)).strftime("%Y-%m-%dT14:00:00Z"),
                country="US",
                event="Initial Jobless Claims",
                impact="Medium",
                forecast="215K",
                previous="212K"
            ),
            MacroEvent(
                id="evt4",
                time=(now + timedelta(hours=2)).strftime("%Y-%m-%dT09:00:00Z"),
                country="CN",
                event="Caixin Manufacturing PMI",
                impact="High",
                forecast="50.2",
                previous="50.4"
            )
        ]
        return sorted(events, key=lambda x: x.time)
