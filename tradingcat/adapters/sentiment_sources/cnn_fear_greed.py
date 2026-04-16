"""CNN Fear & Greed Index fetcher.

Endpoint is undocumented but widely used:
    https://production.dataviz.cnn.io/index/fearandgreed/graphdata

Response shape (abridged):
    {
      "fear_and_greed": {
        "score": 57.0,
        "rating": "greed",
        "timestamp": "2026-04-15T00:00:00+00:00",
        "previous_close": ...
      },
      "fear_and_greed_historical": { ... }
    }

Failure mode contract: `fetch()` returns `None` on any error (HTTP, parse,
shape, type). Upstream callers must treat `None` as "source unavailable".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


# A reasonable browser UA — CNN's endpoint 403s on a default httpx UA.
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class CNNFearGreedReading:
    """A single Fear & Greed observation."""

    value: float  # 0..100
    rating: str  # one of: extreme_fear, fear, neutral, greed, extreme_greed
    fetched_at: datetime


class CNNFearGreedClient:
    """Thin wrapper around the CNN Fear & Greed JSON endpoint."""

    def __init__(
        self,
        http: SentimentHttpClient,
        *,
        url: str = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        ttl_seconds: int = 600,
        user_agent: str = _DEFAULT_UA,
    ) -> None:
        self._http = http
        self._url = url
        self._ttl_seconds = int(ttl_seconds)
        self._user_agent = user_agent

    def fetch(self) -> CNNFearGreedReading | None:
        payload = self._http.get_json(
            self._url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
            ttl_seconds=self._ttl_seconds,
        )
        if payload is None:
            return None
        try:
            section = payload.get("fear_and_greed") or payload.get("data", {}).get("fear_and_greed")
            if not isinstance(section, dict):
                logger.info("CNN F&G payload missing 'fear_and_greed' section")
                return None
            raw_value = section.get("score")
            raw_rating = section.get("rating")
            if raw_value is None or raw_rating is None:
                logger.info("CNN F&G payload missing score/rating")
                return None
            value = float(raw_value)
            rating = str(raw_rating).strip().lower().replace(" ", "_")
            return CNNFearGreedReading(
                value=value,
                rating=rating,
                fetched_at=datetime.now(UTC),
            )
        except (TypeError, ValueError, AttributeError) as exc:
            logger.warning("CNN F&G payload parse failure: %s", exc)
            return None
