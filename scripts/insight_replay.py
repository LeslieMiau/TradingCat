#!/usr/bin/env python3
"""Replay InsightEngine over a historical date range and dump candidates as JSONL.

Used by Round 3 of the InsightEngine harness to evaluate detector precision
on real bar history. Each line of the output file is one candidate insight
with an empty ``manual_judgement`` field — the user fills it in (``true`` /
``false`` / ``edge``) and a follow-up summarizer reads the file back to
compute precision and false-positive density per spec §5.1 thresholds.

Usage::

    python scripts/insight_replay.py --start 2025-10-01 --end 2025-12-31 \
        --output data/reports/insight_replay/2025q4.jsonl

Notes:
- Engine runs in ``dry_run=True`` mode so the live insight store is never
  touched. Existing dashboard insights, ack/dismiss state, and feedback
  history are unaffected.
- Watchlist + benchmark resolution use the *current* config snapshot. If
  the historical instruments catalog matters, snapshot it first; we do not
  rewind ``data/instruments.json``.
- Flow series provider is omitted by default (no per-day flow snapshot in
  history yet); ``FlowAnomalyDetector`` therefore produces nothing in
  Round 3 replays. Round 4 will bridge ``MarketSentimentHistoryRepository``
  into a date-aware provider for backtest mode.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tradingcat.app import TradingCatApplication  # noqa: E402


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _is_weekday(day: date) -> bool:
    return day.weekday() < 5  # Mon=0..Sun=6


def _iter_trading_days(start: date, end: date):
    cur = start
    while cur <= end:
        if _is_weekday(cur):
            yield cur
        cur += timedelta(days=1)


@dataclass
class _ReplaySummary:
    days_evaluated: int = 0
    candidates_total: int = 0
    by_kind: Counter = None  # type: ignore[assignment]
    by_severity: Counter = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_kind is None:
            self.by_kind = Counter()
        if self.by_severity is None:
            self.by_severity = Counter()

    def report(self) -> str:
        if self.days_evaluated == 0:
            return "no trading days in range"
        density = self.candidates_total / self.days_evaluated
        return (
            f"days={self.days_evaluated} candidates={self.candidates_total} "
            f"density={density:.2f}/day "
            f"by_kind={dict(self.by_kind)} "
            f"by_severity={dict(self.by_severity)}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="output JSONL path (parent dirs auto-created)",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=400,
        help="safety cap on trading days walked (default 400)",
    )
    args = parser.parse_args(argv)
    if args.start > args.end:
        parser.error("--start must be <= --end")

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    app = TradingCatApplication()
    app.startup()
    try:
        engine = app.insight_engine
        summary = _ReplaySummary()
        with output_path.open("w", encoding="utf-8") as fp:
            for evaluation_date in _iter_trading_days(args.start, args.end):
                if summary.days_evaluated >= args.max_days:
                    print(
                        f"[insight_replay] hit --max-days={args.max_days}, stopping",
                        file=sys.stderr,
                    )
                    break
                summary.days_evaluated += 1
                try:
                    result = engine.run(as_of=evaluation_date, dry_run=True)
                except Exception as exc:  # noqa: BLE001 — replay must keep going
                    print(
                        f"[insight_replay] {evaluation_date}: engine error {exc}",
                        file=sys.stderr,
                    )
                    continue
                for insight in result.candidates or []:
                    summary.candidates_total += 1
                    summary.by_kind[insight.kind.value] += 1
                    summary.by_severity[insight.severity.value] += 1
                    record = {
                        "evaluation_date": evaluation_date.isoformat(),
                        "insight": insight.model_dump(mode="json"),
                        "manual_judgement": "",
                        "manual_note": "",
                    }
                    fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[insight_replay] {summary.report()}")
        print(f"[insight_replay] wrote {output_path}")
        return 0
    finally:
        app.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
