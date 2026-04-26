"""Unit tests for the daily advisory-research runner."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tradingcat.config import AdvisoryReportConfig
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market
from tradingcat.domain.news import NewsEventClass, NewsItem, NewsUrgency
from tradingcat.services.advisory_research_runner import AdvisoryResearchRunner


def _instrument(symbol: str, market: Market = Market.CN, currency: str = "CNY") -> Instrument:
    return Instrument(symbol=symbol, market=market, currency=currency)


def _bars(instrument: Instrument, start: date, end: date) -> list[Bar]:
    days = (end - start).days
    bars: list[Bar] = []
    price = 10.0
    for offset in range(days + 1):
        when = start + timedelta(days=offset)
        price *= 1.001
        bars.append(
            Bar(
                instrument=instrument,
                timestamp=datetime(when.year, when.month, when.day, tzinfo=UTC),
                open=price * 0.99,
                high=price * 1.01,
                low=price * 0.98,
                close=price,
                volume=1_000_000,
            )
        )
    return bars


def test_runner_writes_dated_report_with_no_news_or_analyst(tmp_path):
    runner = AdvisoryResearchRunner(
        output_dir=tmp_path / "advisory",
        instrument_provider=lambda: [_instrument("600000"), _instrument("510300", currency="CNY")],
        bars_provider=_bars,
    )
    target = date(2026, 4, 26)

    result = runner.run_for(target)

    expected_path = tmp_path / "advisory" / "2026-04-26.md"
    assert result.output_path == expected_path
    assert expected_path.exists()
    content = expected_path.read_text(encoding="utf-8")
    assert "# 每日研究 2026-04-26" in content
    assert "_暂无分析师输出。_" in content
    assert "## 候选标的排行" in content
    assert "## 资讯引用" in content
    assert "_暂无资讯。_" in content
    assert result.candidate_count == 2
    assert result.news_count == 0
    assert result.analyst_called is False


def test_runner_includes_news_items_and_calls_analyst_when_provided(tmp_path):
    captured_payloads: list[dict] = []

    class _StubAnalyst:
        def analyze(self, analyst_id, payload, *, source_refs=None):
            captured_payloads.append(payload)
            from tradingcat.services.research_analysts import AnalystOutput

            return AnalystOutput(
                analyst_id=analyst_id,
                summary="今日研究摘要：成长板块技术面修复。",
                bullets=["沪深 300 ETF 受政策面利好"],
                confidence=0.7,
                risks=["关注外部宏观波动"],
                source_refs=source_refs or [],
            )

    news_item = NewsItem(
        source="eastmoney",
        title="政策窗口关注信号",
        url="https://example.com/policy",
        published_at=datetime(2026, 4, 25, 23, 0, tzinfo=UTC),
        symbols=["510300"],
        urgency=NewsUrgency.MEDIUM,
        event_class=NewsEventClass.POLICY,
        relevance=0.8,
    )

    runner = AdvisoryResearchRunner(
        output_dir=tmp_path / "advisory",
        instrument_provider=lambda: [_instrument("510300", currency="CNY")],
        bars_provider=_bars,
        news_provider=lambda: [news_item],
        analyst=_StubAnalyst(),
    )

    result = runner.run_for(date(2026, 4, 26))

    assert result.analyst_called is True
    assert result.candidate_count == 1
    assert result.news_count == 1
    content = result.output_path.read_text(encoding="utf-8")
    assert "今日研究摘要" in content
    assert "[eastmoney] 政策窗口关注信号" in content
    assert captured_payloads[0]["candidate_count"] == 1
    assert captured_payloads[0]["sources"] == [
        "universe_screener",
        "news_filter",
        "technical_features",
    ]


def test_runner_prunes_reports_older_than_retention(tmp_path):
    output_dir = tmp_path / "advisory"
    output_dir.mkdir(parents=True)
    target = date(2026, 4, 26)
    # Within retention window (10d back) — should survive.
    survivor = output_dir / "2026-04-16.md"
    survivor.write_text("survivor", encoding="utf-8")
    # 31 days old — should be pruned.
    old = output_dir / "2026-03-26.md"
    old.write_text("expired", encoding="utf-8")
    # Filename does not parse as a date — must be left alone.
    other = output_dir / "manual-note.md"
    other.write_text("manual", encoding="utf-8")

    runner = AdvisoryResearchRunner(
        output_dir=output_dir,
        instrument_provider=lambda: [],
        bars_provider=_bars,
        retention_days=30,
    )

    result = runner.run_for(target)

    assert old not in [path for path in output_dir.iterdir()]
    assert survivor.exists()
    assert other.exists()
    assert result.output_path.exists()
    assert old in result.pruned_paths


def test_runner_returns_zero_candidates_when_no_instruments(tmp_path):
    runner = AdvisoryResearchRunner(
        output_dir=tmp_path / "advisory",
        instrument_provider=lambda: [],
        bars_provider=_bars,
    )

    result = runner.run_for(date(2026, 4, 26))

    assert result.candidate_count == 0
    assert result.instrument_count == 0
    assert result.output_path.exists()


def test_advisory_report_config_defaults_disabled():
    cfg = AdvisoryReportConfig()
    assert cfg.enabled is False
    assert cfg.cron_hour == 7
    assert cfg.cron_minute == 45
    assert cfg.cron_timezone == "Asia/Shanghai"
    assert cfg.retention_days == 30
    assert cfg.candidate_limit == 10
    assert cfg.output_dir == Path("data") / "reports" / "advisory"


def test_advisory_report_config_from_env_parses_overrides():
    cfg = AdvisoryReportConfig.from_env(
        {
            "TRADINGCAT_ADVISORY_REPORT_ENABLED": "true",
            "TRADINGCAT_ADVISORY_REPORT_CRON_HOUR": "9",
            "TRADINGCAT_ADVISORY_REPORT_CRON_MINUTE": "15",
            "TRADINGCAT_ADVISORY_REPORT_CRON_TIMEZONE": "America/New_York",
            "TRADINGCAT_ADVISORY_REPORT_RETENTION_DAYS": "60",
            "TRADINGCAT_ADVISORY_REPORT_CANDIDATE_LIMIT": "5",
            "TRADINGCAT_ADVISORY_REPORT_OUTPUT_DIR": "/tmp/advisory",
        }
    )
    assert cfg.enabled is True
    assert cfg.cron_hour == 9
    assert cfg.cron_minute == 15
    assert cfg.cron_timezone == "America/New_York"
    assert cfg.retention_days == 60
    assert cfg.candidate_limit == 5
    assert cfg.output_dir == Path("/tmp/advisory")
