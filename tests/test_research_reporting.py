from datetime import date, datetime, timezone

from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market
from tradingcat.app import TradingCatApplication
from tradingcat.config import AppConfig
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.research import ResearchService
from tradingcat.strategies.simple import DefensiveTrendStrategy, EquityMomentumStrategy, EtfRotationStrategy, MeanReversionStrategy, OptionHedgeStrategy


def test_research_report_applies_walk_forward_thresholds(tmp_path):
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategies = [
        EtfRotationStrategy(),
        EquityMomentumStrategy(),
        OptionHedgeStrategy(),
    ]

    report = service.summarize_strategy_report(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )

    assert report["minimum_history_start"] == date(2018, 1, 1)
    assert len(report["strategy_reports"]) == 3
    assert "strategy_count" in report["portfolio_metrics"]

    etf_report = next(item for item in report["strategy_reports"] if item["strategy_id"] == "strategy_a_etf_rotation")
    assert etf_report["window_count"] >= 1
    assert etf_report["metrics"]["sample_months"] >= 12
    assert "annualized_return" in etf_report["metrics"]
    assert "max_selected_correlation" in etf_report
    assert etf_report["data_source"] == "historical"
    assert etf_report["data_ready"] is True
    assert etf_report["promotion_blocked"] is False
    option_report = next(item for item in report["strategy_reports"] if item["strategy_id"] == "strategy_c_option_overlay")
    assert option_report["capacity_tier"] == "limited"


def test_research_report_blocks_synthetic_promotion_without_local_history(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    report = service.summarize_strategy_report(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of)},
    )

    etf_report = report["strategy_reports"][0]
    assert report["accepted_strategy_ids"] == []
    assert etf_report["passed_validation"] is False
    assert etf_report["validation_status"] == "blocked"
    assert etf_report["promotion_blocked"] is True
    assert etf_report["data_source"] == "synthetic"
    assert etf_report["minimum_coverage_ratio"] == 0.0
    assert report["hard_blocked"] is True
    assert report["report_status"] == "blocked"
    assert report["minimum_history_coverage_ratio"] == 0.0
    assert report["blocking_reasons"]
    assert any("synthetic fallback data" in reason.lower() for reason in etf_report["blocking_reasons"])


def test_option_strategy_generates_research_only_option_signal():
    strategy = OptionHedgeStrategy()

    signals = strategy.generate_signals(date(2026, 3, 8))

    assert len(signals) == 1
    assert signals[0].instrument.asset_class.value == "option"
    assert signals[0].metadata["execution_mode"] == "research_only"


def test_market_driven_strategies_emit_indicator_snapshots_from_persistent_universe(tmp_path):
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    market_data.upsert_instruments(
        [
            Instrument(
                symbol="SPY",
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="SPDR S&P 500 ETF",
                enabled=False,
                tradable=False,
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=38000,
            ),
            Instrument(
                symbol="QQQ",
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="Invesco QQQ Trust",
                enabled=False,
                tradable=False,
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=21000,
            ),
            Instrument(
                symbol="IVV",
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="iShares Core S&P 500 ETF",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=6200,
            ),
            Instrument(
                symbol="AAPL",
                market=Market.US,
                asset_class=AssetClass.STOCK,
                currency="USD",
                name="Apple",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=8400,
            ),
        ]
    )
    as_of = date(2026, 3, 8)

    etf_signals = EtfRotationStrategy(market_data).generate_signals(as_of)
    stock_signals = EquityMomentumStrategy(market_data).generate_signals(as_of)
    option_signals = OptionHedgeStrategy(market_data).generate_signals(as_of)

    assert etf_signals
    assert all(signal.instrument.symbol not in {"SPY", "QQQ"} for signal in etf_signals)
    assert etf_signals[0].metadata["signal_source"] == "historical_momentum_rotation"
    assert "momentum_252d" in etf_signals[0].metadata["indicator_snapshot"]
    assert stock_signals[0].instrument.symbol == "AAPL"
    assert stock_signals[0].metadata["signal_source"] == "historical_equity_momentum"
    assert "avg_dollar_volume_20d" in stock_signals[0].metadata["indicator_snapshot"]
    assert option_signals[0].metadata["underlying_symbol"] == "IVV"
    assert option_signals[0].metadata["signal_source"] == "historical_option_overlay"


def test_research_experiment_prefers_historical_market_data(tmp_path):
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    strategy = EtfRotationStrategy()
    as_of = date(2026, 3, 8)

    experiment = service.run_experiment(strategy.strategy_id, as_of, strategy.generate_signals(as_of))

    assert experiment.assumptions["data_source"] == "historical"
    assert experiment.assumptions["history_symbols"] >= 1
    assert experiment.assumptions["ledger_entries"] >= 1


def test_research_report_does_not_pollute_short_window_stock_signals(tmp_path):
    app = TradingCatApplication(AppConfig(data_dir=tmp_path))
    app.market_history.upsert_instruments(
        [
            Instrument(
                symbol="IVV",
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="iShares Core S&P 500 ETF",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=6200,
            ),
            Instrument(
                symbol="VOO",
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="Vanguard S&P 500 ETF",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=5400,
            ),
            Instrument(
                symbol="AAPL",
                market=Market.US,
                asset_class=AssetClass.STOCK,
                currency="USD",
                name="Apple",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=8400,
            ),
        ]
    )
    as_of = date(2026, 3, 8)

    initial_signals = app.strategy_by_id("strategy_b_equity_momentum").generate_signals(as_of)
    _ = app.research_facade.strategy_detail("strategy_a_etf_rotation", as_of)
    _ = app.research_facade.report(as_of)
    refreshed_signals = app.strategy_by_id("strategy_b_equity_momentum").generate_signals(as_of)

    assert initial_signals[0].instrument.symbol == "AAPL"
    assert initial_signals[0].metadata["signal_source"] == "historical_equity_momentum"
    assert refreshed_signals[0].instrument.symbol == "AAPL"
    assert refreshed_signals[0].metadata["signal_source"] == "historical_equity_momentum"


def test_research_experiment_records_replay_fingerprint_and_compare(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    strategy = EtfRotationStrategy()

    first = service.run_experiment(strategy.strategy_id, date(2026, 3, 8), strategy.generate_signals(date(2026, 3, 8)))
    second = service.run_experiment(strategy.strategy_id, date(2026, 3, 8), strategy.generate_signals(date(2026, 3, 8)))
    third = service.run_experiment(strategy.strategy_id, date(2026, 3, 9), strategy.generate_signals(date(2026, 3, 9)))

    assert first.assumptions["replay_fingerprint"] == second.assumptions["replay_fingerprint"]
    comparison_same = service.compare_experiments(first.id, second.id)
    comparison_changed = service.compare_experiments(first.id, third.id)

    assert comparison_same["same_inputs"] is True
    assert comparison_same["input_diff"] == {}
    assert comparison_changed["same_inputs"] is False
    assert "as_of" in comparison_changed["input_diff"]


def test_research_recommendations_return_actions(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategies = [
        EtfRotationStrategy(),
        EquityMomentumStrategy(),
        OptionHedgeStrategy(),
    ]

    report = service.recommend_strategy_actions(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )

    assert "recommendations" in report
    assert "next_actions" in report
    assert len(report["recommendations"]) == 3
    option_recommendation = next(item for item in report["recommendations"] if item["strategy_id"] == "strategy_c_option_overlay")
    assert option_recommendation["action"] in {"paper_only", "drop"}
    assert "stability_bucket" in option_recommendation
    assert "validation_pass_rate" in option_recommendation


def test_research_recommendations_downgrade_partial_history_to_paper_only(tmp_path):
    class PartialFailureAdapter(StaticMarketDataAdapter):
        def fetch_bars(self, instrument, start, end):
            if instrument.symbol in {"QQQ", "510300"}:
                raise RuntimeError("history unavailable")
            return super().fetch_bars(instrument, start, end)

    market_data = MarketDataService(
        adapter=PartialFailureAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    report = service.recommend_strategy_actions(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of)},
    )

    recommendation = report["recommendations"][0]
    assert recommendation["action"] == "paper_only"
    assert recommendation["promotion_blocked"] is True
    assert recommendation["data_ready"] is False
    assert any("history coverage is incomplete" in reason.lower() for reason in recommendation["reasons"])


def test_research_report_marks_partial_history_as_hard_blocked(tmp_path):
    class PartialFailureAdapter(StaticMarketDataAdapter):
        def fetch_bars(self, instrument, start, end):
            if instrument.symbol in {"QQQ", "510300"}:
                raise RuntimeError("history unavailable")
            return super().fetch_bars(instrument, start, end)

    market_data = MarketDataService(
        adapter=PartialFailureAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    report = service.summarize_strategy_report(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of)},
    )

    strategy_report = report["strategy_reports"][0]
    assert strategy_report["validation_status"] == "blocked"
    assert strategy_report["passed_validation"] is False
    assert strategy_report["promotion_blocked"] is True
    assert strategy_report["minimum_coverage_ratio"] < 0.95
    assert report["hard_blocked"] is True
    assert report["report_status"] == "blocked"
    assert report["portfolio_passed"] is False
    assert report["minimum_history_coverage_ratio"] < 0.95
    assert any("history coverage is incomplete" in reason.lower() for reason in report["blocking_reasons"])


def test_research_report_blocks_missing_corporate_actions(tmp_path):
    class MissingCorporateActionsAdapter(StaticMarketDataAdapter):
        def fetch_corporate_actions(self, instrument, start, end):
            if instrument.symbol in {"SPY", "QQQ", "510300"}:
                raise RuntimeError("corporate actions unavailable")
            return super().fetch_corporate_actions(instrument, start, end)

    market_data = MarketDataService(
        adapter=MissingCorporateActionsAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    report = service.summarize_strategy_report(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of)},
    )

    strategy_report = report["strategy_reports"][0]
    assert strategy_report["data_source"] == "historical"
    assert strategy_report["data_ready"] is False
    assert strategy_report["corporate_actions_ready"] is False
    assert strategy_report["missing_corporate_action_symbols"] == ["QQQ", "SPY"]
    assert strategy_report["corporate_action_blockers"]
    assert report["hard_blocked"] is True
    assert any("corporate action coverage is incomplete" in reason.lower() for reason in report["blocking_reasons"])


def test_research_stability_report_returns_summary(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategies = [
        EtfRotationStrategy(),
        EquityMomentumStrategy(),
        OptionHedgeStrategy(),
    ]

    report = service.summarize_strategy_stability(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )

    assert "strategy_stability" in report
    assert len(report["strategy_stability"]) == 3
    assert "average_validation_pass_rate" in report
    assert "next_actions" in report


def test_research_profit_scorecard_returns_verdicts(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategies = [
        EtfRotationStrategy(),
        EquityMomentumStrategy(),
        OptionHedgeStrategy(),
    ]

    report = service.build_profit_scorecard(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )

    assert "rows" in report
    assert len(report["rows"]) == 3
    assert "profitability_score" in report["rows"][0]
    assert report["rows"][0]["verdict"] in {"deploy_candidate", "paper_only", "reject"}
    assert "blocked_count" in report
    assert "blocked_strategy_ids" in report


def test_research_profit_scorecard_exposes_blockers_for_synthetic_strategies(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    report = service.build_profit_scorecard(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of)},
    )

    row = report["rows"][0]
    assert row["data_source"] == "synthetic"
    assert row["data_ready"] is False
    assert row["promotion_blocked"] is True
    assert row["blocking_reasons"]
    assert report["blocked_count"] == 1
    assert report["blocked_strategy_ids"] == [strategy.strategy_id]


def test_research_profit_scorecard_supports_candidate_pool(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategies = [
        EtfRotationStrategy(),
        EquityMomentumStrategy(),
        OptionHedgeStrategy(),
        MeanReversionStrategy(),
        DefensiveTrendStrategy(),
    ]

    report = service.build_profit_scorecard(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )

    assert len(report["rows"]) == 5
    ids = {item["strategy_id"] for item in report["rows"]}
    assert "strategy_d_mean_reversion" in ids
    assert "strategy_e_defensive_trend" in ids
    assert "correlation_matrix" in report
    assert "reject_summary" in report
    assert "verdict_groups" in report


def test_research_strategy_detail_returns_curve(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    detail = service.strategy_detail(strategy.strategy_id, as_of, strategy.generate_signals(as_of))

    assert detail["strategy_id"] == strategy.strategy_id
    assert "nav_curve" in detail
    assert "drawdown_curve" in detail
    assert len(detail["nav_curve"]) >= 2
    assert "sample_split" in detail
    assert "history_coverage" in detail
    assert "monthly_table" in detail
    assert "recommendation" in detail
    assert "data_source" in detail
    assert "data_ready" in detail
    assert "promotion_blocked" in detail
    assert "blocking_reasons" in detail
    assert "minimum_coverage_ratio" in detail
    assert "history_coverage_threshold" in detail
    assert "missing_coverage_symbols" in detail
    assert "history_coverage_blockers" in detail
    assert "benchmark" in detail
    assert "symbol" in detail["benchmark"]
    assert "rolling_excess_curve" in detail["benchmark"]
    assert "yearly_performance" in detail


def test_research_strategy_detail_exposes_missing_history_symbols(tmp_path):
    class PartialFailureAdapter(StaticMarketDataAdapter):
        def fetch_bars(self, instrument, start, end):
            if instrument.symbol in {"QQQ", "510300"}:
                raise RuntimeError("history unavailable")
            return super().fetch_bars(instrument, start, end)

    market_data = MarketDataService(
        adapter=PartialFailureAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    detail = service.strategy_detail(strategy.strategy_id, as_of, strategy.generate_signals(as_of))

    assert detail["promotion_blocked"] is True
    assert detail["minimum_coverage_ratio"] < detail["history_coverage_threshold"]
    assert detail["history_coverage_threshold"] == 0.95
    assert detail["missing_coverage_symbols"] == ["QQQ"]
    assert any("QQQ" in reason for reason in detail["history_coverage_blockers"])


def test_research_strategy_detail_exposes_corporate_action_gaps(tmp_path):
    class MissingCorporateActionsAdapter(StaticMarketDataAdapter):
        def fetch_corporate_actions(self, instrument, start, end):
            if instrument.symbol in {"SPY", "QQQ", "510300"}:
                raise RuntimeError("corporate actions unavailable")
            return super().fetch_corporate_actions(instrument, start, end)

    market_data = MarketDataService(
        adapter=MissingCorporateActionsAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    detail = service.strategy_detail(strategy.strategy_id, as_of, strategy.generate_signals(as_of))

    assert detail["corporate_actions_ready"] is False
    assert detail["missing_corporate_action_symbols"] == ["QQQ", "SPY"]
    assert detail["corporate_action_blockers"]
    assert detail["corporate_action_coverage"]["ready"] is False


def test_research_report_blocks_missing_fx_coverage(tmp_path):
    class MissingFxMarketDataService(MarketDataService):
        def sync_fx_rates(self, base_currency="CNY", quote_currencies=None, start=None, end=None):
            return {
                "base_currency": base_currency,
                "quote_currencies": quote_currencies or [],
                "rate_count": 0,
                "start": start,
                "end": end,
            }

    market_data = MissingFxMarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    report = service.summarize_strategy_report(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of)},
    )

    strategy_report = report["strategy_reports"][0]
    assert strategy_report["data_source"] == "historical"
    assert strategy_report["data_ready"] is False
    assert strategy_report["fx_ready"] is False
    assert strategy_report["missing_fx_pairs"] == ["HKD", "USD"]
    assert strategy_report["fx_blockers"]
    assert report["hard_blocked"] is True
    assert any("fx coverage is incomplete" in reason.lower() for reason in report["blocking_reasons"])


def test_research_strategy_detail_exposes_fx_gaps(tmp_path):
    class MissingFxMarketDataService(MarketDataService):
        def sync_fx_rates(self, base_currency="CNY", quote_currencies=None, start=None, end=None):
            return {
                "base_currency": base_currency,
                "quote_currencies": quote_currencies or [],
                "rate_count": 0,
                "start": start,
                "end": end,
            }

    market_data = MissingFxMarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(tmp_path),
        history=HistoricalMarketDataRepository(tmp_path),
    )
    service = ResearchService(
        BacktestExperimentRepository(tmp_path),
        market_data=market_data,
    )
    as_of = date(2026, 3, 8)
    strategy = EtfRotationStrategy()

    detail = service.strategy_detail(strategy.strategy_id, as_of, strategy.generate_signals(as_of))

    assert detail["fx_ready"] is False
    assert detail["missing_fx_pairs"] == ["HKD", "USD"]
    assert detail["fx_blockers"]
    assert detail["fx_coverage"]["ready"] is False


def test_research_monthly_returns_support_mixed_timezone_bars(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    instrument = Instrument(symbol="QQQ", market=Market.US, asset_class=AssetClass.ETF)
    bars = [
        Bar(instrument=instrument, timestamp=datetime(2026, 3, 31, tzinfo=timezone.utc), open=105, high=105, low=105, close=105, volume=1),
        Bar(instrument=instrument, timestamp=datetime(2026, 1, 31, tzinfo=timezone.utc), open=100, high=100, low=100, close=100, volume=1),
        Bar(instrument=instrument, timestamp=datetime(2026, 2, 28), open=102, high=102, low=102, close=102, volume=1),
    ]

    returns = service.strategy_analysis._monthly_returns_from_bars(bars)

    assert returns == [0.02, 0.029412]


def test_research_suggest_experiments_returns_ideas(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategies = [
        EtfRotationStrategy(),
        EquityMomentumStrategy(),
        OptionHedgeStrategy(),
    ]

    report = service.suggest_experiments(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )

    assert "experiment_ideas" in report
    assert "next_actions" in report
    assert len(report["experiment_ideas"]) >= 1


def test_research_news_summary_extracts_topics(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))

    payload = service.summarize_news(
        [
            {
                "title": "Fed signals slower rate cuts while chip demand stays strong",
                "body": "AI cloud spending lifted guidance for NVDA and broader software names.",
                "symbols": ["NVDA", "QQQ"],
            },
            {
                "title": "CSRC reviews exchange filing requirements",
                "body": "New regulation may affect semi-automated CN workflows.",
                "symbols": ["510300"],
            },
        ]
    )

    assert payload["item_count"] == 2
    assert "macro" in payload["dominant_topics"]
    assert "regulation" in payload["dominant_topics"]
    assert "NVDA" in payload["impacted_symbols"]
    assert payload["next_actions"]


def test_research_news_summary_extracts_topics(tmp_path):
    service = ResearchService(BacktestExperimentRepository(tmp_path))

    payload = service.summarize_news(
        [
            {
                "title": "Fed signals slower rate cuts while chip demand stays strong",
                "body": "AI cloud spending lifted guidance for NVDA and broader software names.",
                "symbols": ["NVDA", "QQQ"],
            },
            {
                "title": "CSRC reviews exchange filing requirements",
                "body": "New regulation may affect semi-automated CN workflows.",
                "symbols": ["510300"],
            },
        ]
    )

    assert payload["item_count"] == 2
    assert "macro" in payload["dominant_topics"]
    assert "regulation" in payload["dominant_topics"]
    assert "NVDA" in payload["impacted_symbols"]
    assert payload["next_actions"]
