from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

logger = logging.getLogger(__name__)


def format_date(dt: date) -> str:
    return dt.strftime("%Y%m%d")


def parse_date(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, date):
        return datetime.combine(raw, datetime.min.time(), tzinfo=UTC)
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    # Pandas Timestamp objects have to_pydatetime; some APIs emit them.
    to_py = getattr(raw, "to_pydatetime", None)
    if to_py is not None:
        try:
            converted = to_py()
            if isinstance(converted, datetime):
                return converted if converted.tzinfo else converted.replace(tzinfo=UTC)
        except Exception:
            pass
    logger.debug("Could not parse date: %r", raw)
    return None
