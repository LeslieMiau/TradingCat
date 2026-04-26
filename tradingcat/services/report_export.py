from __future__ import annotations

import html
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
            f"生成时间：{generated_at.astimezone(UTC).isoformat()}",
            "",
            "> 仅作研究参考。本报告不生成交易信号、订单、审批或执行指令。",
            "",
        ]
        lines.extend(_analyst_section(list(analysts)))
        lines.extend(_candidate_section(list(candidates)))
        lines.extend(_news_section(list(news_items)))
        return "\n".join(lines).rstrip() + "\n"


def _analyst_section(outputs: list[AnalystOutput]) -> list[str]:
    lines = ["## 分析师研究", ""]
    if not outputs:
        return [*lines, "_暂无分析师输出。_", ""]
    for output in outputs:
        lines.extend(
            [
                f"### {_clean(output.analyst_id)}",
                "",
                _clean(output.summary),
                "",
                f"置信度：{output.confidence:.2f}",
                "",
            ]
        )
        if output.bullets:
            lines.append("要点：")
            lines.extend(f"- {_clean(item)}" for item in output.bullets)
            lines.append("")
        if output.risks:
            lines.append("风险：")
            lines.extend(f"- {_clean(item)}" for item in output.risks)
            lines.append("")
        if output.source_refs:
            lines.append("来源：")
            lines.extend(f"- {_clean(item)}" for item in output.source_refs)
            lines.append("")
    return lines


def _candidate_section(candidates: list[UniverseCandidate]) -> list[str]:
    lines = ["## 候选标的排行", ""]
    if not candidates:
        return [*lines, "_暂无候选标的。_", ""]
    lines.append("| 标的 | 综合分 | 技术面 | 基本面 | 新闻面 | 原因 |")
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
    lines = ["## 资讯引用", ""]
    if not news_items:
        return [*lines, "_暂无资讯。_", ""]
    for item in news_items:
        when = item.published_at.astimezone(UTC).isoformat() if item.published_at else "时间未知"
        url = f" ({item.url})" if item.url else ""
        lines.append(f"- [{_clean(item.source)}] {_clean(item.title)}{url} - {when}")
    lines.append("")
    return lines


def _clean(value: object) -> str:
    return html.escape(str(value).replace("\n", " ").replace("|", "\\|").strip())
