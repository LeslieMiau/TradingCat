from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.domain.models import Instrument, Market
from tradingcat.domain.news import NewsEventClass, NewsItem, NewsUrgency
from tradingcat.services.report_export import ReportExportService
from tradingcat.services.research_analysts import AnalystOutput
from tradingcat.services.universe_screener import UniverseCandidate


def test_report_export_renders_markdown_sections():
    service = ReportExportService()
    analyst = AnalystOutput(
        analyst_id="news",
        summary="Constructive tone.",
        bullets=["Policy support"],
        risks=["Risk: headline reversal"],
        source_refs=["https://example.com/news"],
        generated_at=datetime(2026, 4, 26, tzinfo=UTC),
    )
    candidate = UniverseCandidate(
        instrument=Instrument(symbol="600000", market=Market.CN, currency="CNY"),
        score=0.8,
        technical_score=0.7,
        fundamental_score=0.8,
        news_score=0.9,
        reasons=["bullish MA alignment", "reasonable PE"],
    )
    news = NewsItem(
        source="cls",
        title="重大政策支持",
        url="https://example.com/1",
        published_at=datetime(2026, 4, 26, 1, 0, tzinfo=UTC),
        urgency=NewsUrgency.HIGH,
        event_class=NewsEventClass.POLICY,
    )

    markdown = service.render_markdown(
        title="Daily Research",
        analysts=[analyst],
        candidates=[candidate],
        news_items=[news],
        generated_at=datetime(2026, 4, 26, 2, 0, tzinfo=UTC),
    )

    assert "# Daily Research" in markdown
    assert "仅作研究参考" in markdown
    assert "## 分析师研究" in markdown
    assert "## 候选标的排行" in markdown
    assert "## 资讯引用" in markdown
    assert "置信度：" in markdown
    assert "要点：" in markdown
    assert "- Policy support" in markdown
    assert "| 600000 | 0.8000 | 0.7000 | 0.8000 | 0.9000 |" in markdown
    assert "[cls] 重大政策支持" in markdown


def test_report_export_writes_to_requested_path(tmp_path):
    output = tmp_path / "reports" / "research.md"

    returned = ReportExportService().export_markdown(output, title="Empty Report")

    assert returned == output
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "_暂无分析师输出。_" in content
    assert "_暂无候选标的。_" in content
    assert "_暂无资讯。_" in content
