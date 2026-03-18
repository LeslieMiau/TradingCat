from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
from __future__ import annotations

from datetime import date

from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
from tradingcat.repositories.state import DailyTradingPlanRepository, DailyTradingSummaryRepository


class TradingJournalService:
    def __init__(
        self,
        plan_repository: DailyTradingPlanRepository,
        summary_repository: DailyTradingSummaryRepository,
    ) -> None:
        self._plans = plan_repository.load()
        self._summaries = summary_repository.load()
        self._plan_repository = plan_repository
        self._summary_repository = summary_repository

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        self._plans[note.id] = note
        self._plan_repository.save(self._plans)
        return note

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        self._summaries[note.id] = note
        self._summary_repository.save(self._summaries)
        return note

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        plans = sorted(self._plans.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            plans = [item for item in plans if item.account == account]
        return plans

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        summaries = sorted(self._summaries.values(), key=lambda item: (item.as_of, item.generated_at), reverse=True)
        if account:
            summaries = [item for item in summaries if item.account == account]
        return summaries

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        for note in self.list_plans(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        for note in self.list_summaries(account):
            if as_of is None or note.as_of == as_of:
                return note
        return None

    def clear(self) -> None:
        self._plans = {}
        self._summaries = {}
        self._plan_repository.save(self._plans)
        self._summary_repository.save(self._summaries)
