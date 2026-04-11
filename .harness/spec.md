# Market-Awareness Participation Engine Spec

## Goal

Refactor TradingCat market awareness into a participation-engine architecture that observes key news, the A-share three-index tape, fear-greed conditions, and volume-price structure, then converts those observations into advisory-only participation guidance using probability and odds.

## Product Contract

- The top-level market-awareness entrypoint remains `/research/market-awareness` and continues to expose:
  - `overall_regime`
  - `confidence`
  - `risk_posture`
  - `actions`
  - `strategy_guidance`
  - `data_quality`
- The payload must now also expose typed sections for:
  - `news_observation`
  - `a_share_indices`
  - `fear_greed`
  - `volume_price`
  - `participation`
- Participation output is advisory-only:
  - it informs the research page
  - it informs `/dashboard/summary`
  - it informs `/journal/plans/generate`
  - it does not alter execution gating or place orders

## Architecture Contract

- `MarketAwarenessService` becomes an orchestrator over dedicated leaf services:
  - `NewsObservationService`
  - `AshareIndexObservationService`
  - `FearGreedToolService`
  - `VolumePriceToolService`
  - `ParticipationDecisionService`
- Routes remain thin.
- Query/facade layers consume typed payloads and do not rebuild business logic.
- A-share observation symbols are internal-only and must not leak into the tradable universe.

## Data Contract

- Public RSS/web feeds are used without API keys and must degrade cleanly on timeout or parsing failure.
- The A-share tape is defined by:
  - 上证指数
  - 深证成指
  - 创业板指
- Internal symbol mapping must route those indices to provider-specific identifiers without adding a new tradable asset class.

## UI Contract

- `/dashboard/research` must hydrate from `/dashboard/summary` first.
- Slow research scorecard endpoints must not block first paint.
- The research page must show dedicated sections for news, A-share indices, fear-greed, volume-price, and participation.
- Degraded data must show explicit operator-facing notes instead of blank panels.

## Baseline Repair Included

- `/research/backtests` currently fails because non-finite numeric values leak into API serialization.
- This regression must be repaired before the task is considered healthy.

## Validation Contract

- Focused pytest must cover:
  - backtests API regression
  - market-awareness services/models
  - dashboard summary/trading-plan contracts
  - research page/static asset coverage
- Local smoke must verify:
  - `/research/market-awareness`
  - `/dashboard/summary`
  - `/journal/plans/generate`
  - `/dashboard/research`
