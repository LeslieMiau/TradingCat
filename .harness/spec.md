# Research Page Loading Repair Spec

## Goal

Repair the TradingCat research page so `http://127.0.0.1:8000/dashboard/research` renders useful operator data immediately instead of appearing blank when optional live research endpoints are slow.

## Product Contract

- The research page must use `/dashboard/summary` as the first-paint data source for:
  - market-awareness
  - active strategy rows
  - candidate counts and top picks
- The page must remain useful when one or more live enhancement endpoints are slow or unavailable:
  - `POST /research/scorecard/run`
  - `POST /research/candidates/scorecard`
  - `POST /research/correlation`
- Partial failure must produce explicit degraded notes, not a blank page.
- Existing market-awareness panels must remain visible.
- The fix must not turn live scorecards off; they remain optional enhancement layers after first paint.

## Baseline Repair Included

- `GET /research/backtests` currently fails JSON serialization because at least one experiment field emits `nan`.
- This regression must be repaired as part of the baseline before the task is considered complete.

## Validation Contract

- Targeted pytest must pass for:
  - research backtests API
  - dashboard summary contract
  - research page/static asset coverage
  - any touched facade/helper tests
- Local curl/html smoke must show:
  - `/dashboard/summary` contains enough data for first paint
  - `/dashboard/research` still exposes the expected market-awareness sections
  - the page no longer depends on both live scorecard endpoints completing before showing data

## Scope Limits

- No large redesign of the research page
- No removal of market-awareness UI
- No broad refactor of unrelated research APIs
