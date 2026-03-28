from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import date
from statistics import mean

from tradingcat.backtest.engine import EventDrivenBacktester
from tradingcat.domain.models import BacktestExperiment, Signal
from tradingcat.services.market_data import MarketDataService
from tradingcat.strategies.simple import strategy_metadata


logger = logging.getLogger(__name__)


class StrategyAnalysisService:
    def __init__(
        self,
        experiment_runner: Callable[[str, date, list[Signal]], BacktestExperiment],
        backtester: EventDrivenBacktester,
        market_data: MarketDataService | None = None,
    ) -> None:
        self._run_experiment = experiment_runner
        self._backtester = backtester
        self._market_data = market_data

    def summarize_strategy_report(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        experiments = [self._run_experiment(strategy_id, as_of, signals) for strategy_id, signals in strategy_signals.items()]
        correlations = self._pairwise_correlations(experiments)
        strategy_reports = []

        accepted_strategy_ids: list[str] = []
        accepted_peer_ids: list[str] = []
        for experiment in sorted(experiments, key=lambda item: item.metrics.sharpe, reverse=True):
            peer_correlations = correlations.get(experiment.strategy_id, {})
            max_correlation = max((abs(value) for value in peer_correlations.values()), default=0.0)
            max_selected_correlation = max((abs(peer_correlations.get(peer_id, 0.0)) for peer_id in accepted_peer_ids), default=0.0)
            stability = self._stability_summary(experiment)
            research_passed = bool(experiment.passed_validation) or (
                float(experiment.metrics.annualized_return) > 0.12
                and float(experiment.metrics.max_drawdown) < 0.12
                and float(experiment.metrics.sharpe) > 1.0
                and float(stability["validation_pass_rate"]) >= 0.6
                and float(stability["stability_score"]) >= 0.65
            )
            report = {
                "strategy_id": experiment.strategy_id,
                "passed_validation": research_passed,
                "strict_validation_passed": experiment.passed_validation,
                "window_count": experiment.window_count,
                "metrics": experiment.metrics.model_dump(mode="json"),
                "sample_start": experiment.sample_start,
                "sample_end": experiment.as_of,
                "market_distribution": self._market_distribution(strategy_signals.get(experiment.strategy_id, [])),
                "capacity_tier": self._capacity_tier(strategy_signals.get(experiment.strategy_id, [])),
                "capacity_score": self._capacity_score(strategy_signals.get(experiment.strategy_id, [])),
                "correlation_to_peers": peer_correlations,
                "max_correlation": round(max_correlation, 4),
                "max_selected_correlation": round(max_selected_correlation, 4),
                "data_source": experiment.assumptions.get("data_source", "synthetic"),
                "history_complete": bool(experiment.assumptions.get("history_complete", False)),
                "history_symbols": int(experiment.assumptions.get("history_symbols", 0)),
                "missing_history_symbols": int(experiment.assumptions.get("missing_history_symbols", 0)),
                **stability,
            }
            if research_passed and max_selected_correlation < 0.7:
                accepted_strategy_ids.append(experiment.strategy_id)
                accepted_peer_ids.append(experiment.strategy_id)
            strategy_reports.append(report)

        accepted_reports = [report for report in strategy_reports if report["strategy_id"] in accepted_strategy_ids]
        portfolio_metrics = self._portfolio_metrics(accepted_reports)
        portfolio_passed = (
            portfolio_metrics["annualized_return"] > 0.15
            and portfolio_metrics["max_drawdown"] < 0.15
            and portfolio_metrics["calmar"] > 1.0
        )

        return {
            "as_of": as_of,
            "minimum_history_start": date(2018, 1, 1),
            "strategy_reports": strategy_reports,
            "accepted_strategy_ids": accepted_strategy_ids,
            "rejected_strategy_ids": [report["strategy_id"] for report in strategy_reports if report["strategy_id"] not in accepted_strategy_ids],
            "portfolio_metrics": portfolio_metrics,
            "portfolio_passed": portfolio_passed,
        }

    def summarize_strategy_stability(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        report = self.summarize_strategy_report(as_of, strategy_signals)
        stable = [item for item in report["strategy_reports"] if item["stability_bucket"] == "stable"]
        unstable = [item for item in report["strategy_reports"] if item["stability_bucket"] == "unstable"]
        constrained = [item for item in report["strategy_reports"] if item["capacity_tier"] == "limited"]
        return {
            "as_of": as_of,
            "stable_count": len(stable),
            "unstable_count": len(unstable),
            "capacity_constrained_count": len(constrained),
            "average_validation_pass_rate": round(mean(float(item["validation_pass_rate"]) for item in report["strategy_reports"]), 4)
            if report["strategy_reports"]
            else 0.0,
            "strategy_stability": [
                {
                    "strategy_id": item["strategy_id"],
                    "validation_pass_rate": item["validation_pass_rate"],
                    "stability_score": item["stability_score"],
                    "stability_bucket": item["stability_bucket"],
                    "capacity_tier": item["capacity_tier"],
                    "capacity_score": item["capacity_score"],
                }
                for item in report["strategy_reports"]
            ],
            "next_actions": self._stability_next_actions(stable, unstable, constrained),
        }

    def recommend_strategy_actions(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        report = self.summarize_strategy_report(as_of, strategy_signals)
        recommendations = []
        accepted = set(report["accepted_strategy_ids"])

        for strategy_report in sorted(
            report["strategy_reports"],
            key=lambda item: (
                bool(item["passed_validation"]),
                -float(item["max_selected_correlation"]),
                float(item["metrics"]["sharpe"]),
            ),
            reverse=True,
        ):
            metrics = strategy_report["metrics"]
            action = "keep"
            reasons: list[str] = []
            if strategy_report["strategy_id"] not in accepted:
                action = "drop"
                if not strategy_report["passed_validation"]:
                    reasons.append("Failed out-of-sample validation thresholds.")
                if float(strategy_report["max_selected_correlation"]) >= 0.7:
                    reasons.append("Correlation gate exceeded the 0.7 limit.")
            elif (
                not bool(strategy_report["history_complete"])
                and int(strategy_report["history_symbols"]) > 0
                and int(strategy_report["missing_history_symbols"]) > 0
            ):
                action = "paper_only"
                reasons.append("Local history coverage is incomplete for required symbols; keep it in paper-only mode.")
            elif strategy_report["capacity_tier"] == "limited":
                action = "paper_only"
                reasons.append("Capacity is limited, keep it in research or low-allocation mode.")
            else:
                reasons.append("Passed validation and correlation gate.")

            if float(metrics["turnover"]) > 1.5:
                reasons.append("Turnover is elevated and should be monitored for implementation drag.")
            if float(metrics["max_drawdown"]) >= 0.1:
                reasons.append("Drawdown is near the single-strategy ceiling.")
            if strategy_report["stability_bucket"] != "stable":
                reasons.append(f"Walk-forward stability is {strategy_report['stability_bucket']}.")

            recommendations.append(
                {
                    "strategy_id": strategy_report["strategy_id"],
                    "action": action,
                    "priority": self._action_priority(action),
                    "reasons": reasons,
                    "metrics": metrics,
                    "capacity_tier": strategy_report["capacity_tier"],
                    "capacity_score": strategy_report["capacity_score"],
                    "max_selected_correlation": strategy_report["max_selected_correlation"],
                    "validation_pass_rate": strategy_report["validation_pass_rate"],
                    "stability_score": strategy_report["stability_score"],
                    "stability_bucket": strategy_report["stability_bucket"],
                    "market_distribution": strategy_report["market_distribution"],
                }
            )

        next_actions = []
        if not report["portfolio_passed"]:
            next_actions.append("Portfolio layer does not yet clear the admission gate; keep allocation in paper-trading mode.")
        if any(item["action"] == "drop" for item in recommendations):
            next_actions.append("Remove failed or over-correlated strategies from the candidate set before the next rollout review.")
        if any(item["action"] == "paper_only" for item in recommendations):
            next_actions.append("Keep limited-capacity option overlays in research or low-allocation mode.")
        if not next_actions:
            next_actions.append("Current accepted strategies can stay in the candidate set for the next validation cycle.")

        return {**report, "recommendations": recommendations, "next_actions": next_actions}

    def build_profit_scorecard(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        recommendation_report = self.recommend_strategy_actions(as_of, strategy_signals)
        rows: list[dict[str, object]] = []
        deployable = 0
        paper_only = 0
        rejected = 0

        for recommendation in recommendation_report["recommendations"]:
            metrics = recommendation["metrics"]
            score = self._profitability_score(
                annualized_return=float(metrics["annualized_return"]),
                sharpe=float(metrics["sharpe"]),
                max_drawdown=float(metrics["max_drawdown"]),
                calmar=float(metrics["calmar"]),
                stability_score=float(recommendation["stability_score"]),
                capacity_score=float(recommendation["capacity_score"]),
                max_selected_correlation=float(recommendation["max_selected_correlation"]),
            )
            verdict = self._profitability_verdict(str(recommendation["action"]), score)
            if verdict == "deploy_candidate":
                deployable += 1
            elif verdict == "paper_only":
                paper_only += 1
            else:
                rejected += 1
            rows.append(
                {
                    "strategy_id": recommendation["strategy_id"],
                    "action": recommendation["action"],
                    "verdict": verdict,
                    "profitability_score": score,
                    "annualized_return": float(metrics["annualized_return"]),
                    "sharpe": float(metrics["sharpe"]),
                    "max_drawdown": float(metrics["max_drawdown"]),
                    "calmar": float(metrics["calmar"]),
                    "validation_pass_rate": recommendation["validation_pass_rate"],
                    "stability_score": recommendation["stability_score"],
                    "stability_bucket": recommendation["stability_bucket"],
                    "capacity_tier": recommendation["capacity_tier"],
                    "capacity_score": recommendation["capacity_score"],
                    "max_selected_correlation": recommendation["max_selected_correlation"],
                    "market_distribution": recommendation["market_distribution"],
                    "reasons": recommendation["reasons"],
                }
            )

        rows.sort(key=lambda item: (item["verdict"] != "deploy_candidate", -float(item["profitability_score"])))
        return {
            "as_of": as_of,
            "portfolio_passed": recommendation_report["portfolio_passed"],
            "accepted_strategy_ids": recommendation_report["accepted_strategy_ids"],
            "deploy_candidate_count": deployable,
            "paper_only_count": paper_only,
            "rejected_count": rejected,
            "rows": rows,
            "correlation_matrix": self._correlation_matrix(recommendation_report["strategy_reports"]),
            "reject_summary": self._reject_summary(rows),
            "verdict_groups": self._verdict_groups(rows),
            "next_actions": recommendation_report["next_actions"],
        }

    def strategy_detail(self, strategy_id: str, as_of: date, signals: list[Signal]) -> dict[str, object]:
        experiment = self._run_experiment(strategy_id, as_of, signals)
        scorecard = self.build_profit_scorecard(as_of, {strategy_id: signals})
        recommendation = scorecard["rows"][0] if scorecard["rows"] else {}
        metadata = strategy_metadata(strategy_id)
        monthly_returns = self._decode_monthly_returns(experiment)
        nav_curve = self._nav_curve_from_monthly_returns(monthly_returns)
        split_metrics = self._sample_split_metrics(monthly_returns, signals)
        coverage = self._strategy_history_coverage(signals, experiment.sample_start, as_of)
        benchmark = self._benchmark_comparison(signals, experiment.sample_start, as_of, nav_curve)
        yearly_performance = self._yearly_performance(monthly_returns, benchmark.get("monthly_returns", []), experiment.sample_start)
        return {
            "as_of": as_of,
            "strategy_id": strategy_id,
            "signal_count": len(signals),
            "signals": [
                {
                    "symbol": signal.instrument.symbol,
                    "market": signal.instrument.market.value,
                    "asset_class": signal.instrument.asset_class.value,
                    "side": signal.side.value,
                    "target_weight": signal.target_weight,
                    "reason": signal.reason,
                    "metadata": signal.metadata,
                }
                for signal in signals
            ],
            "metadata": metadata,
            "metrics": experiment.metrics.model_dump(mode="json"),
            "sample_start": experiment.sample_start,
            "window_count": experiment.window_count,
            "walk_forward_windows": self._decode_walk_forward_details(experiment),
            "monthly_returns": monthly_returns,
            "monthly_table": self._monthly_return_table(monthly_returns, experiment.sample_start),
            "nav_curve": nav_curve,
            "drawdown_curve": self._drawdown_curve_from_nav_curve(nav_curve),
            "sample_split": split_metrics,
            "history_coverage": coverage,
            "benchmark": benchmark,
            "yearly_performance": yearly_performance,
            "recommendation": recommendation,
            "assumptions": {
                "data_source": experiment.assumptions.get("data_source"),
                "history_complete": experiment.assumptions.get("history_complete"),
                "history_symbols": experiment.assumptions.get("history_symbols"),
                "missing_history_symbols": experiment.assumptions.get("missing_history_symbols"),
                "commission_bps": experiment.assumptions.get("commission_bps"),
                "slippage_bps": experiment.assumptions.get("slippage_bps"),
                "total_cost_bps": experiment.assumptions.get("total_cost_bps"),
            },
        }

    def calculate_asset_correlation(self, symbols: list[str], start: date, end: date) -> dict[str, dict[str, float]]:
        if self._market_data is None or len(symbols) < 2:
            return {symbol: {} for symbol in symbols}

        bars_by_symbol = self._market_data.ensure_history(symbols, start, end)
        daily_closes: dict[date, dict[str, float]] = {}
        for symbol in symbols:
            for bar in bars_by_symbol.get(symbol, []):
                timestamp_date = bar.timestamp.date()
                daily_closes.setdefault(timestamp_date, {})
                daily_closes[timestamp_date][symbol] = bar.close

        sorted_dates = sorted(daily_closes.keys())
        returns_by_symbol: dict[str, list[float]] = {symbol: [] for symbol in symbols}
        for index in range(1, len(sorted_dates)):
            prev_date = sorted_dates[index - 1]
            current_date = sorted_dates[index]
            for symbol in symbols:
                prev_close = daily_closes[prev_date].get(symbol)
                current_close = daily_closes[current_date].get(symbol)
                if prev_close is not None and current_close is not None and prev_close > 0:
                    returns_by_symbol[symbol].append((current_close / prev_close) - 1.0)
                else:
                    returns_by_symbol[symbol].append(0.0)

        matrix: dict[str, dict[str, float]] = {symbol: {} for symbol in symbols}
        for left in symbols:
            for right in symbols:
                matrix[left][right] = 1.0 if left == right else round(self._correlation(returns_by_symbol[left], returns_by_symbol[right]), 4)
        return matrix

    async def calculate_asset_correlation_async(self, symbols: list[str], start: date, end: date) -> dict[str, dict[str, float]]:
        return await asyncio.to_thread(self.calculate_asset_correlation, symbols, start, end)

    def _market_distribution(self, signals: list[Signal]) -> dict[str, float]:
        if not signals:
            return {}
        total_weight = sum(abs(signal.target_weight) for signal in signals) or 1.0
        distribution: dict[str, float] = {}
        for signal in signals:
            distribution.setdefault(signal.instrument.market.value, 0.0)
            distribution[signal.instrument.market.value] += abs(signal.target_weight) / total_weight
        return {market: round(weight, 4) for market, weight in distribution.items()}

    def _capacity_tier(self, signals: list[Signal]) -> str:
        if not signals:
            return "inactive"
        if all(signal.instrument.asset_class.value == "etf" for signal in signals):
            return "high"
        if any(signal.instrument.asset_class.value == "option" for signal in signals):
            return "limited"
        return "medium"

    def _capacity_score(self, signals: list[Signal]) -> float:
        return {"high": 1.0, "medium": 0.7, "limited": 0.35, "inactive": 0.0}.get(self._capacity_tier(signals), 0.5)

    def _pairwise_correlations(self, experiments: list[BacktestExperiment]) -> dict[str, dict[str, float]]:
        mapping = {experiment.strategy_id: self._decode_monthly_returns(experiment) for experiment in experiments}
        correlations: dict[str, dict[str, float]] = {experiment.strategy_id: {} for experiment in experiments}
        for left in experiments:
            for right in experiments:
                if left.strategy_id == right.strategy_id:
                    continue
                correlations[left.strategy_id][right.strategy_id] = round(self._correlation(mapping[left.strategy_id], mapping[right.strategy_id]), 4)
        return correlations

    def _decode_monthly_returns(self, experiment: BacktestExperiment) -> list[float]:
        encoded = str(experiment.assumptions.get("correlation_key", ""))
        if not encoded:
            return []
        return [float(chunk) for chunk in encoded.split("|") if chunk]

    def _decode_walk_forward_details(self, experiment: BacktestExperiment) -> list[dict[str, object]]:
        raw = experiment.assumptions.get("walk_forward_details", "")
        if not raw:
            return []
        try:
            payload = str(raw).replace("'", '"').replace("True", "true").replace("False", "false")
            parsed = json.loads(payload)
        except Exception:
            logger.exception("Failed to decode walk-forward details", extra={"strategy_id": experiment.strategy_id, "experiment_id": experiment.id})
            return []
        return parsed if isinstance(parsed, list) else []

    def _nav_curve_from_monthly_returns(self, monthly_returns: list[float]) -> list[dict[str, float]]:
        nav = 1.0
        curve = [{"index": 0, "nav": 1.0}]
        for index, monthly_return in enumerate(monthly_returns, start=1):
            nav *= 1 + monthly_return
            curve.append({"index": index, "nav": round(nav, 4)})
        return curve

    def _monthly_return_table(self, monthly_returns: list[float], sample_start: date) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        current_year = sample_start.year
        current_month = sample_start.month
        grouped: dict[int, dict[str, object]] = {}
        month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for monthly_return in monthly_returns:
            row = grouped.setdefault(current_year, {"year": current_year, "months": {}})
            row["months"][month_labels[current_month - 1]] = round(monthly_return, 4)
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1
        return [grouped[year] for year in sorted(grouped)]

    def _drawdown_curve_from_nav_curve(self, nav_curve: list[dict[str, float]]) -> list[dict[str, float]]:
        peak = 0.0
        drawdowns: list[dict[str, float]] = []
        for point in nav_curve:
            nav = float(point["nav"])
            peak = max(peak, nav)
            drawdown = 0.0 if peak <= 0 else 1.0 - (nav / peak)
            drawdowns.append({"index": int(point["index"]), "drawdown": round(drawdown, 4)})
        return drawdowns

    def _sample_split_metrics(self, monthly_returns: list[float], signals: list[Signal]) -> dict[str, object]:
        if not monthly_returns:
            empty = self._backtester.run(signals).model_dump(mode="json")
            return {"in_sample": empty, "out_of_sample": empty, "split_index": 0}
        split_index = max(12, int(len(monthly_returns) * 0.7))
        split_index = min(split_index, len(monthly_returns))
        costs = self._backtester.cost_assumptions(signals)["total_cost_bps"]
        turnover = self._backtester._estimate_turnover(signals)
        in_sample = self._backtester._metrics_from_monthly_returns(monthly_returns[:split_index], turnover=turnover, total_cost_bps=costs)
        out_sample_returns = monthly_returns[split_index:] or monthly_returns[-12:]
        out_of_sample = self._backtester._metrics_from_monthly_returns(out_sample_returns, turnover=turnover, total_cost_bps=costs)
        return {"split_index": split_index, "in_sample": in_sample.model_dump(mode="json"), "out_of_sample": out_of_sample.model_dump(mode="json")}

    def _strategy_history_coverage(self, signals: list[Signal], start: date, end: date) -> dict[str, object]:
        if self._market_data is None or not signals:
            return {"ready": False, "reports": [], "minimum_coverage_ratio": 0.0}
        symbols = sorted({signal.instrument.symbol for signal in signals if signal.instrument.asset_class != "option"})
        if not symbols:
            return {"ready": True, "reports": [], "minimum_coverage_ratio": 1.0}
        coverage = self._market_data.summarize_history_coverage(symbols=symbols, start=start, end=end)
        reports = coverage.get("reports", [])
        minimum = min((float(item["coverage_ratio"]) for item in reports), default=1.0)
        return {"ready": minimum >= 0.95, "minimum_coverage_ratio": round(minimum, 4), "reports": reports}

    def _benchmark_comparison(self, signals: list[Signal], start: date, end: date, strategy_nav_curve: list[dict[str, float]]) -> dict[str, object]:
        benchmark_symbol = self._benchmark_symbol(signals)
        if self._market_data is None or benchmark_symbol is None:
            return {"ready": False, "symbol": benchmark_symbol, "monthly_returns": [], "nav_curve": [], "drawdown_curve": [], "relative_curve": [], "rolling_excess_curve": [], "comparison": {}, "metrics": {}}
        bars = self._market_data.ensure_history([benchmark_symbol], start, end).get(benchmark_symbol, [])
        if not bars:
            return {"ready": False, "symbol": benchmark_symbol, "monthly_returns": [], "nav_curve": [], "drawdown_curve": [], "relative_curve": [], "rolling_excess_curve": [], "comparison": {}, "metrics": {}}
        monthly_returns = self._monthly_returns_from_bars(bars)
        benchmark_nav_curve = self._nav_curve_from_monthly_returns(monthly_returns)
        relative_curve = self._relative_curve(strategy_nav_curve, benchmark_nav_curve)
        benchmark_metrics = self._backtester._metrics_from_monthly_returns(monthly_returns, turnover=0.0, total_cost_bps=0.0).model_dump(mode="json")
        return {
            "ready": True,
            "symbol": benchmark_symbol,
            "monthly_returns": monthly_returns,
            "nav_curve": benchmark_nav_curve,
            "drawdown_curve": self._drawdown_curve_from_nav_curve(benchmark_nav_curve),
            "relative_curve": relative_curve,
            "rolling_excess_curve": self._rolling_relative_curve(relative_curve),
            "comparison": self._benchmark_summary(strategy_nav_curve, benchmark_nav_curve, benchmark_metrics),
            "metrics": benchmark_metrics,
        }

    def _benchmark_symbol(self, signals: list[Signal]) -> str | None:
        for signal in signals:
            if signal.instrument.asset_class.value != "option":
                return signal.instrument.symbol
        for signal in signals:
            underlying = signal.metadata.get("underlying_symbol")
            if underlying:
                return str(underlying)
        return None

    def _monthly_returns_from_bars(self, bars) -> list[float]:
        if not bars:
            return []
        # Historical bars can mix naive and timezone-aware datetimes depending on
        # which adapter populated local history. Sort by wall-clock components so
        # Python 3.12+ does not raise on direct datetime comparisons.
        ordered = sorted(
            bars,
            key=lambda item: (
                item.timestamp.year,
                item.timestamp.month,
                item.timestamp.day,
                item.timestamp.hour,
                item.timestamp.minute,
                item.timestamp.second,
                item.timestamp.microsecond,
            ),
        )
        month_end_closes: list[float] = []
        current_period = None
        current_close = None
        for bar in ordered:
            period = (bar.timestamp.year, bar.timestamp.month)
            if current_period is None:
                current_period = period
            if period != current_period and current_close is not None:
                month_end_closes.append(float(current_close))
                current_period = period
            current_close = float(bar.close)
        if current_close is not None:
            month_end_closes.append(float(current_close))
        returns: list[float] = []
        for previous, current in zip(month_end_closes, month_end_closes[1:], strict=False):
            returns.append(0.0 if previous <= 0 else round((current / previous) - 1.0, 6))
        return returns

    def _relative_curve(self, strategy_nav_curve: list[dict[str, float]], benchmark_nav_curve: list[dict[str, float]]) -> list[dict[str, float]]:
        size = min(len(strategy_nav_curve), len(benchmark_nav_curve))
        relative: list[dict[str, float]] = []
        for index in range(size):
            strategy_nav = float(strategy_nav_curve[index]["nav"])
            benchmark_nav = float(benchmark_nav_curve[index]["nav"])
            excess = 0.0 if benchmark_nav <= 0 else (strategy_nav / benchmark_nav) - 1.0
            relative.append({"index": index, "excess": round(excess, 4)})
        return relative

    def _rolling_relative_curve(self, relative_curve: list[dict[str, float]], window: int = 12) -> list[dict[str, float]]:
        if not relative_curve:
            return []
        result: list[dict[str, float]] = []
        for index, point in enumerate(relative_curve):
            start = max(0, index - window + 1)
            window_points = relative_curve[start : index + 1]
            average_excess = mean(float(item["excess"]) for item in window_points)
            result.append({"index": int(point["index"]), "excess": round(average_excess, 4)})
        return result

    def _benchmark_summary(self, strategy_nav_curve: list[dict[str, float]], benchmark_nav_curve: list[dict[str, float]], benchmark_metrics: dict[str, object]) -> dict[str, object]:
        strategy_final = float(strategy_nav_curve[-1]["nav"]) if strategy_nav_curve else 1.0
        benchmark_final = float(benchmark_nav_curve[-1]["nav"]) if benchmark_nav_curve else 1.0
        excess_total_return = 0.0 if benchmark_final <= 0 else (strategy_final / benchmark_final) - 1.0
        return {
            "strategy_final_nav": round(strategy_final, 4),
            "benchmark_final_nav": round(benchmark_final, 4),
            "outperformed": strategy_final > benchmark_final,
            "excess_total_return": round(excess_total_return, 4),
            "benchmark_annualized_return": benchmark_metrics.get("annualized_return"),
            "benchmark_sharpe": benchmark_metrics.get("sharpe"),
            "benchmark_max_drawdown": benchmark_metrics.get("max_drawdown"),
        }

    def _yearly_performance(self, strategy_monthly_returns: list[float], benchmark_monthly_returns: list[float], sample_start: date) -> list[dict[str, object]]:
        strategy_by_year = self._yearly_returns_from_monthlies(strategy_monthly_returns, sample_start)
        benchmark_by_year = self._yearly_returns_from_monthlies(benchmark_monthly_returns, sample_start)
        years = sorted(set(strategy_by_year) | set(benchmark_by_year))
        rows: list[dict[str, object]] = []
        for year in years:
            strategy_return = strategy_by_year.get(year)
            benchmark_return = benchmark_by_year.get(year)
            excess_return = round(strategy_return - benchmark_return, 4) if strategy_return is not None and benchmark_return is not None else None
            rows.append({"year": year, "strategy_return": strategy_return, "benchmark_return": benchmark_return, "excess_return": excess_return})
        return rows

    def _yearly_returns_from_monthlies(self, monthly_returns: list[float], sample_start: date) -> dict[int, float]:
        current_year = sample_start.year
        current_month = sample_start.month
        grouped: dict[int, list[float]] = {}
        for monthly_return in monthly_returns:
            grouped.setdefault(current_year, []).append(float(monthly_return))
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1
        yearly: dict[int, float] = {}
        for year, values in grouped.items():
            nav = 1.0
            for value in values:
                nav *= 1.0 + value
            yearly[year] = round(nav - 1.0, 4)
        return yearly

    def _correlation_matrix(self, strategy_reports: list[dict[str, object]]) -> dict[str, object]:
        ids = [str(item["strategy_id"]) for item in strategy_reports if "strategy_id" in item]
        rows: list[dict[str, object]] = []
        for report in strategy_reports:
            strategy_id = str(report["strategy_id"])
            peers = report.get("correlation_to_peers", {})
            values = []
            for peer_id in ids:
                values.append({"peer_id": peer_id, "value": 1.0 if peer_id == strategy_id else float(peers.get(peer_id, 0.0))})
            rows.append({"strategy_id": strategy_id, "values": values})
        return {"strategy_ids": ids, "rows": rows}

    def _reject_summary(self, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        rejected_rows = [row for row in rows if row["verdict"] == "reject"]
        rejected_rows.sort(key=lambda item: (-len(item.get("reasons", [])), -abs(float(item.get("max_selected_correlation", 0.0))), -float(item.get("max_drawdown", 0.0))))
        return [
            {
                "strategy_id": row["strategy_id"],
                "primary_reason": row["reasons"][0] if row.get("reasons") else "Rejected by scorecard.",
                "reason_count": len(row.get("reasons", [])),
                "profitability_score": row["profitability_score"],
                "max_selected_correlation": row["max_selected_correlation"],
                "max_drawdown": row["max_drawdown"],
            }
            for row in rejected_rows
        ]

    def _verdict_groups(self, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        groups: list[dict[str, object]] = []
        for verdict in ("deploy_candidate", "paper_only", "reject"):
            members = [row for row in rows if row["verdict"] == verdict]
            if members:
                avg_score = mean(float(row["profitability_score"]) for row in members)
                avg_return = mean(float(row["annualized_return"]) for row in members)
                avg_sharpe = mean(float(row["sharpe"]) for row in members)
                avg_drawdown = mean(float(row["max_drawdown"]) for row in members)
                representative = sorted(members, key=lambda row: float(row["profitability_score"]), reverse=True)[0]
                summary = representative["reasons"][0] if representative.get("reasons") else "No summary."
            else:
                avg_score = 0.0
                avg_return = 0.0
                avg_sharpe = 0.0
                avg_drawdown = 0.0
                summary = "No strategies in this bucket."
            groups.append(
                {
                    "verdict": verdict,
                    "count": len(members),
                    "average_profitability_score": round(avg_score, 4),
                    "average_annualized_return": round(avg_return, 4),
                    "average_sharpe": round(avg_sharpe, 4),
                    "average_max_drawdown": round(avg_drawdown, 4),
                    "summary": summary,
                    "strategy_ids": [str(row["strategy_id"]) for row in members],
                }
            )
        return groups

    def _correlation(self, left: list[float], right: list[float]) -> float:
        size = min(len(left), len(right))
        if size == 0:
            return 0.0
        left = left[:size]
        right = right[:size]
        left_mean = mean(left)
        right_mean = mean(right)
        numerator = sum((lx - left_mean) * (rx - right_mean) for lx, rx in zip(left, right, strict=False))
        left_variance = sum((value - left_mean) ** 2 for value in left)
        right_variance = sum((value - right_mean) ** 2 for value in right)
        denominator = (left_variance * right_variance) ** 0.5
        return 0.0 if denominator == 0 else numerator / denominator

    def _portfolio_metrics(self, accepted_reports: list[dict[str, object]]) -> dict[str, float]:
        if not accepted_reports:
            return {"annualized_return": 0.0, "max_drawdown": 0.0, "calmar": 0.0, "strategy_count": 0}
        annualized_return = mean(float(report["metrics"]["annualized_return"]) for report in accepted_reports)
        max_drawdown = mean(float(report["metrics"]["max_drawdown"]) for report in accepted_reports)
        calmar = annualized_return / max_drawdown if max_drawdown > 0 else annualized_return
        return {
            "annualized_return": round(annualized_return, 4),
            "max_drawdown": round(max_drawdown, 4),
            "calmar": round(calmar, 4),
            "strategy_count": len(accepted_reports),
        }

    def _stability_summary(self, experiment: BacktestExperiment) -> dict[str, object]:
        windows = max(1, int(experiment.assumptions.get("walk_forward_windows", experiment.window_count or 1)))
        passed = int(experiment.assumptions.get("passed_windows", windows if experiment.passed_validation else 0))
        pass_rate = round(passed / windows, 4) if windows else 0.0
        sharpe = float(experiment.metrics.sharpe)
        drawdown = float(experiment.metrics.max_drawdown)
        stability_score = max(0.0, min(1.0, 0.7 * pass_rate + 0.2 * min(max(sharpe / 2.0, 0.0), 1.0) + 0.1 * (1.0 - min(drawdown / 0.2, 1.0))))
        if stability_score >= 0.75:
            bucket = "stable"
        elif stability_score >= 0.45:
            bucket = "watch"
        else:
            bucket = "unstable"
        return {"validation_pass_rate": pass_rate, "stability_score": round(stability_score, 4), "stability_bucket": bucket}

    def _action_priority(self, action: str) -> int:
        return {"keep": 1, "paper_only": 2, "drop": 3}.get(action, 9)

    def _profitability_score(
        self,
        *,
        annualized_return: float,
        sharpe: float,
        max_drawdown: float,
        calmar: float,
        stability_score: float,
        capacity_score: float,
        max_selected_correlation: float,
    ) -> float:
        return_score = min(max(annualized_return / 0.2, 0.0), 1.0)
        sharpe_score = min(max(sharpe / 2.0, 0.0), 1.0)
        drawdown_score = 1.0 - min(max(max_drawdown / 0.2, 0.0), 1.0)
        calmar_score = min(max(calmar / 2.0, 0.0), 1.0)
        correlation_penalty = 1.0 - min(max(max_selected_correlation / 0.9, 0.0), 1.0)
        score = (
            0.24 * return_score
            + 0.22 * sharpe_score
            + 0.16 * drawdown_score
            + 0.14 * calmar_score
            + 0.12 * float(stability_score)
            + 0.07 * float(capacity_score)
            + 0.05 * correlation_penalty
        )
        return round(score, 4)

    def _profitability_verdict(self, action: str, score: float) -> str:
        if action == "drop":
            return "reject"
        if action == "paper_only" or score < 0.55:
            return "paper_only"
        return "deploy_candidate"

    def _stability_next_actions(self, stable: list[dict[str, object]], unstable: list[dict[str, object]], constrained: list[dict[str, object]]) -> list[str]:
        actions: list[str] = []
        if unstable:
            actions.append("Re-run unstable strategies with tighter filters or smaller universes before admission.")
        if constrained:
            actions.append("Keep capacity-constrained strategies in paper-only or low-allocation mode.")
        if stable:
            actions.append("Stable strategies can be prioritized in the next allocation review.")
        return actions or ["No stability-specific follow-up is required for the current sample."]
