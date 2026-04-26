from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from tradingcat.domain.news import NewsItem
from tradingcat.services.research_analysts import AnalystOutput
from tradingcat.services.universe_screener import UniverseCandidate


class ReportExportService:
    """Export advisory research artifacts to Markdown."""

    def export_markdown(
        self,
        output_path: Path,
        *,
        title: str,
        analysts: Iterable[AnalystOutput] = (),
        candidates: Iterable[UniverseCandidate] = (),
        news_items: Iterable[NewsItem] = (),
        generated_at: datetime | None = None,
    ) -> Path:
        generated_at = generated_at or datetime.now(UTC)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            self.render_markdown(
                title=title,
                analysts=analysts,
                candidates=candidates,
                news_items=news_items,
                generated_at=generated_at,
            ),
            encoding="utf-8",
        )
        return output_path

    def render_markdown(
        self,
        *,
        title: str,
        analysts: Iterable[AnalystOutput] = (),
        candidates: Iterable[UniverseCandidate] = (),
        news_items: Iterable[NewsItem] = (),
        generated_at: datetime | None = None,
    ) -> str:
        generated_at = generated_at or datetime.now(UTC)
        lines = [
            f"# {_clean(title)}",
            "",
            f"Generated at: {generated_at.astimezone(UTC).isoformat()}",
            "",
            "> Advisory research only. This report does not create signals, orders, approvals, or execution instructions.",
            "",
        ]
        lines.extend(_analyst_section(list(analysts)))
        lines.extend(_candidate_section(list(candidates)))
        lines.extend(_news_section(list(news_items)))
        return "\n".join(lines).rstrip() + "\n"


def _analyst_section(outputs: list[AnalystOutput]) -> list[str]:
    lines = ["## Analyst Outputs", ""]
    if not outputs:
        return [*lines, "_No analyst outputs._", ""]
    for output in outputs:
        lines.extend(
            [
                f"### {_clean(output.analyst_id)}",
                "",
                _clean(output.summary),
                "",
                f"Confidence: {output.confidence:.2f}",
                "",
            ]
        )
        if output.bullets:
            lines.append("Key points:")
            lines.extend(f"- {_clean(item)}" for item in output.bullets)
            lines.append("")
        if output.risks:
            lines.append("Risks:")
            lines.extend(f"- {_clean(item)}" for item in output.risks)
            lines.append("")
        if output.source_refs:
            lines.append("Sources:")
            lines.extend(f"- {_clean(item)}" for item in output.source_refs)
            lines.append("")
    return lines


def _candidate_section(candidates: list[UniverseCandidate]) -> list[str]:
    lines = ["## Universe Candidates", ""]
    if not candidates:
        return [*lines, "_No candidates._", ""]
    lines.append("| Symbol | Score | Technical | Fundamental | News | Reasons |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for item in candidates:
        reasons = "; ".join(_clean(reason) for reason in item.reasons[:4])
        lines.append(
            f"| {_clean(item.instrument.symbol)} | {item.score:.4f} | {item.technical_score:.4f} | "
            f"{item.fundamental_score:.4f} | {item.news_score:.4f} | {reasons} |"
        )
    lines.append("")
    return lines


def _news_section(news_items: list[NewsItem]) -> list[str]:
    lines = ["## News Items", ""]
    if not news_items:
        return [*lines, "_No news items._", ""]
    for item in news_items:
        when = item.published_at.astimezone(UTC).isoformat() if item.published_at else "unknown time"
        url = f" ({item.url})" if item.url else ""
        lines.append(f"- [{_clean(item.source)}] {_clean(item.title)}{url} - {when}")
    lines.append("")
    return lines


def _clean(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|").strip()
