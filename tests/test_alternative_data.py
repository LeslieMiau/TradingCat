"""Unit tests for the AlternativeDataService snapshot reporting.

These guard against regressing to the prior behaviour where unconfigured
data sources were reported ``healthy`` while actually returning fake data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingcat.adapters.alternative import (
    AlternativeDataService,
    CapitalFlowFetcher,
    MacroEventFetcher,
    SocialMediaFetcher,
)


def test_capital_flow_fetcher_returns_empty_when_unconfigured() -> None:
    fetcher = CapitalFlowFetcher()

    assert fetcher.fetch_northbound() == []
    assert fetcher.fetch_southbound() == []
    assert fetcher.fetch_all() == []


def test_macro_event_fetcher_returns_empty_when_unconfigured() -> None:
    fetcher = MacroEventFetcher()

    assert fetcher.fetch_upcoming() == []
    assert fetcher.fetch_recent() == []


def test_social_fetcher_returns_empty_without_mock_path() -> None:
    fetcher = SocialMediaFetcher(symbols=["AAPL"])

    assert fetcher.fetch() == {}


def test_social_fetcher_loads_mock_when_path_provided(tmp_path: Path) -> None:
    mock_file = tmp_path / "social.json"
    mock_file.write_text(
        json.dumps(
            {
                "AAPL": {
                    "source": "test",
                    "mention_count": 12,
                    "positive_ratio": 0.5,
                    "negative_ratio": 0.2,
                    "neutral_ratio": 0.3,
                    "total_volume": 4200,
                }
            }
        )
    )
    fetcher = SocialMediaFetcher(symbols=["AAPL", "MSFT"], mock_data_path=mock_file)

    mentions = fetcher.fetch()

    # AAPL is in the file → returned. MSFT is absent → omitted.
    assert set(mentions) == {"AAPL"}
    assert mentions["AAPL"].mention_count == 12


def test_snapshot_reports_all_unconfigured_sources_as_degraded() -> None:
    service = AlternativeDataService(symbols=["AAPL"])

    snap = service.snapshot()

    assert snap.sources_healthy == []
    assert set(snap.sources_degraded) == {"social_media", "capital_flows", "macro_events"}
    assert snap.social_media == {}
    assert snap.capital_flows == []
    assert snap.macro_events == []


def test_snapshot_marks_social_healthy_when_mock_provides_data(tmp_path: Path) -> None:
    mock_file = tmp_path / "social.json"
    mock_file.write_text(
        json.dumps(
            {
                "AAPL": {
                    "source": "test",
                    "mention_count": 5,
                    "positive_ratio": 0.4,
                    "negative_ratio": 0.3,
                    "neutral_ratio": 0.3,
                    "total_volume": 1000,
                }
            }
        )
    )
    service = AlternativeDataService(symbols=["AAPL"], mock_data_path=mock_file)

    snap = service.snapshot()

    assert "social_media" in snap.sources_healthy
    assert "capital_flows" in snap.sources_degraded
    assert "macro_events" in snap.sources_degraded
