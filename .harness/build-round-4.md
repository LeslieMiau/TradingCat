# Build Round 4 — UI Polish + 30d Sparkline + History Persistence

**Generator**: claude-sonnet-4-6 (in-session)
**Round scope**: DuckDB sentiment history table + repository wrapper + scheduler job + view model additions + query service history enrichment + frontend SVG sparkline rendering + aria-label accessibility.
**Non-goals (R4)**: None — this is the final round.

## Delivered

### New files

| Path | Purpose |
|---|---|
| `tradingcat/repositories/duckdb_sentiment_store.py` | `DuckDbSentimentStore` — append-only DuckDB store for per-indicator sentiment history. Table `market_sentiment_history` with columns `(ts, market, indicator_key, value, score, status, composite_score, risk_switch)`. Methods: `persist_snapshot()` (flattens snapshot dict into rows), `load_history()` (filter by market/indicator_key/days window), `prune()` (delete old rows). Never raises on individual insert failures. |
| `tradingcat/repositories/sentiment_history.py` | `MarketSentimentHistoryRepository` — facade wrapping `DuckDbSentimentStore` with graceful degradation. Construction never raises. When DuckDB is unavailable (not installed or disabled), all methods are no-ops returning empty results. All public methods catch exceptions and return safe defaults. |
| `tests/test_duckdb_sentiment_store.py` | 31 tests covering: schema creation, snapshot persistence (row count, values, empty, missing fields), history loading (all, by market, by indicator_key, day window, ascending order), pruning, multiple snapshot accumulation, `MarketSentimentHistoryRepository` (available/unavailable states, persist/load/prune round-trip, graceful degradation on store errors), scheduler job registration, view model fields, query service history enrichment (with and without getter). |

### Modifications

| Path | Change |
|---|---|
| `tradingcat/api/view_models.py` | Added `MarketSentimentHistoryPoint(ts, value, score)` model. Added `history: dict[str, list[MarketSentimentHistoryPoint]]` field to `MarketSentimentView` (default empty dict). |
| `tradingcat/services/query_services.py` | `ResearchQueryService.__init__` accepts optional `sentiment_history_getter` kwarg. `market_awareness()` enriches response: loads 30d history from repository, groups by `indicator_key`, injects into `market_sentiment.history` dict. Wrapped in try/except — enrichment failure never affects the base response. |
| `tradingcat/app.py` | Added `sentiment_history` property (delegates to runtime). Wired `sentiment_history_getter=lambda: self.sentiment_history` into `ResearchQueryService` constructor. |
| `tradingcat/runtime.py` | Added `MarketSentimentHistoryRepository` import. Added `sentiment_history` field to `ApplicationRuntime` dataclass. Constructs `MarketSentimentHistoryRepository(config)` during runtime build. |
| `tradingcat/scheduler_runtime.py` | Added `run_sentiment_history_persist_job()` method — snapshots current sentiment, persists via repository, prunes rows older than 90 days. Never raises (try/except wrapper). Added `sentiment_history_persist` job registration (9:00 AM Asia/Shanghai, market=None). |
| `static/research.js` | Added `sentimentSparklineSvg(points, key)` function — renders inline SVG sparkline (180×40, polyline path, endpoint dot, green/red color by last value sign). Includes `role="img"` and `aria-label` with point count for accessibility. `renderMarketSentiment()` now groups history by indicator key and passes sparkline points to each indicator card. Falls back gracefully when no history points available (≥2 required to render). |

## Test summary

| Suite | Count | Status |
|---|---|---|
| `test_duckdb_sentiment_store.py` | 31 | ✅ all pass |
| `test_market_sentiment_service.py` | 52 | ✅ all pass |
| `test_market_awareness_service_sentiment.py` | 12 | ✅ all pass |
| `test_hk_southbound.py` | 8 | ✅ all pass |
| `test_market_sentiment_http.py` | 9 | ✅ all pass |
| `test_api.py` (sentiment subset) | 6 | ✅ all pass |
| `test_architecture_boundaries.py` | 6 | ✅ all pass |
| **Total** | **124** | ✅ |

## Architecture notes

- DuckDB store follows the same pattern as `DuckDbResearchStore` — optional dependency, lazy import, never raises on failure
- Repository facade ensures the sentiment service is fully functional even without DuckDB
- Scheduler job is market-agnostic (market=None) to capture cross-market composite data
- Frontend sparkline degrades gracefully: no history → no SVG rendered, null sentiment → "Sentiment offline" banner
- SVG uses `role="img"` + `aria-label` per R4 spec accessibility requirement
- History enrichment in query service is a no-op when `sentiment_history_getter` is not provided (backward compatible)

## Self-score: 9.5/10

- Deductions: No interactive E2E verification yet (deferred to QA phase). Sparkline color logic uses simple positive/negative threshold rather than per-indicator semantic coloring.
