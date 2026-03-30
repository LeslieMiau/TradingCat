from __future__ import annotations

from datetime import date

from tradingcat.domain.models import Signal
from tradingcat.strategies.simple import strategy_metadata


class StrategyReportingService:
    _DEFAULT_BLOCKING_REASON = "Research data is blocked, but no specific blocker was recorded."

    def __init__(self, analysis: object) -> None:
        self._analysis = analysis

    def summarize_strategy_report(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        experiments = [
            self._analysis._run_experiment(strategy_id, as_of, signals)
            for strategy_id, signals in strategy_signals.items()
        ]
        return self._report_from_experiments(as_of, strategy_signals, experiments)

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
            "average_validation_pass_rate": round(sum(float(item["validation_pass_rate"]) for item in report["strategy_reports"]) / len(report["strategy_reports"]), 4)
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
            "next_actions": self._analysis._stability_next_actions(stable, unstable, constrained),
        }

    def recommend_strategy_actions(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        report = self.summarize_strategy_report(as_of, strategy_signals)
        return self._recommendations_from_report(report)

    def build_profit_scorecard_from_experiments(
        self,
        as_of: date,
        strategy_signals: dict[str, list[Signal]],
        experiments_by_strategy: dict[str, object],
    ) -> dict[str, object]:
        experiments = [
            experiments_by_strategy[strategy_id]
            for strategy_id in strategy_signals
            if strategy_id in experiments_by_strategy
        ]
        report = self._report_from_experiments(as_of, strategy_signals, experiments)
        recommendation_report = self._recommendations_from_report(report)
        return self._scorecard_from_recommendation_report(recommendation_report)

    def _report_from_experiments(self, as_of: date, strategy_signals: dict[str, list[Signal]], experiments: list[object]) -> dict[str, object]:
        correlations = self._analysis._pairwise_correlations(experiments)
        strategy_reports = []

        accepted_strategy_ids: list[str] = []
        accepted_peer_ids: list[str] = []
        for experiment in sorted(experiments, key=lambda item: item.metrics.sharpe, reverse=True):
            peer_correlations = correlations.get(experiment.strategy_id, {})
            max_correlation = max((abs(value) for value in peer_correlations.values()), default=0.0)
            max_selected_correlation = max((abs(peer_correlations.get(peer_id, 0.0)) for peer_id in accepted_peer_ids), default=0.0)
            stability = self._analysis._stability_summary(experiment)
            signals = strategy_signals.get(experiment.strategy_id, [])
            history_coverage = self._analysis._strategy_history_coverage(signals, experiment.sample_start, as_of)
            data_ready = bool(experiment.assumptions.get("data_ready", False))
            threshold_validation_passed = bool(experiment.assumptions.get("threshold_validation_passed", experiment.passed_validation))
            blocking_reasons = self._blocking_reasons(experiment.assumptions, data_ready)
            missing_history_symbol_list = [str(item) for item in experiment.assumptions.get("missing_history_symbol_list", [])]
            missing_corporate_action_symbols = [str(item) for item in experiment.assumptions.get("missing_corporate_action_symbols", [])]
            missing_fx_pairs = [str(item) for item in experiment.assumptions.get("missing_fx_pairs", [])]
            if missing_history_symbol_list:
                blocking_reasons.append(f"History coverage is incomplete for: {', '.join(missing_history_symbol_list)}.")
            if missing_corporate_action_symbols:
                blocking_reasons.append(
                    f"Corporate action coverage is incomplete for: {', '.join(missing_corporate_action_symbols)}."
                )
            if missing_fx_pairs:
                blocking_reasons.append(f"FX coverage is incomplete for: {', '.join(missing_fx_pairs)}.")
            blocking_reasons = list(dict.fromkeys(blocking_reasons))
            research_passed = bool(experiment.passed_validation)
            minimum_coverage_ratio = round(float(history_coverage.get("minimum_coverage_ratio", 0.0)), 4)
            corporate_action_coverage = experiment.assumptions.get("corporate_action_coverage", {})
            validation_status = self._analysis._validation_status(
                passed_validation=research_passed,
                promotion_blocked=not data_ready,
            )
            report = {
                "strategy_id": experiment.strategy_id,
                "passed_validation": research_passed,
                "validation_status": validation_status,
                "strict_validation_passed": experiment.passed_validation,
                "threshold_validation_passed": threshold_validation_passed,
                "window_count": experiment.window_count,
                "metrics": experiment.metrics.model_dump(mode="json"),
                "sample_start": experiment.sample_start,
                "sample_end": experiment.as_of,
                "market_distribution": self._analysis._market_distribution(signals),
                "capacity_tier": self._analysis._capacity_tier(signals),
                "capacity_score": self._analysis._capacity_score(signals),
                "correlation_to_peers": peer_correlations,
                "max_correlation": round(max_correlation, 4),
                "max_selected_correlation": round(max_selected_correlation, 4),
                "data_source": experiment.assumptions.get("data_source", "synthetic"),
                "data_ready": data_ready,
                "promotion_blocked": not data_ready,
                "blocking_reasons": blocking_reasons,
                "history_coverage": history_coverage,
                "minimum_coverage_ratio": minimum_coverage_ratio,
                "history_complete": bool(experiment.assumptions.get("history_complete", False)),
                "history_symbols": int(experiment.assumptions.get("history_symbols", 0)),
                "missing_history_symbols": int(experiment.assumptions.get("missing_history_symbols", 0)),
                "missing_history_symbol_list": missing_history_symbol_list,
                "fx_ready": bool(experiment.assumptions.get("fx_ready", True)),
                "missing_fx_pairs": missing_fx_pairs,
                "fx_blockers": list(experiment.assumptions.get("fx_blockers", [])),
                "fx_coverage": experiment.assumptions.get("fx_coverage", {}),
                "corporate_actions_ready": bool(experiment.assumptions.get("corporate_actions_ready", True)),
                "missing_corporate_action_symbols": missing_corporate_action_symbols,
                "corporate_action_blockers": list(experiment.assumptions.get("corporate_action_blockers", [])),
                "corporate_action_coverage": corporate_action_coverage,
                "signal_insights": [
                    {
                        "symbol": signal.instrument.symbol,
                        "signal_source": signal.metadata.get("signal_source"),
                        "indicator_snapshot": signal.metadata.get("indicator_snapshot", {}),
                    }
                    for signal in signals
                ],
                **stability,
            }
            if research_passed and max_selected_correlation < 0.7:
                accepted_strategy_ids.append(experiment.strategy_id)
                accepted_peer_ids.append(experiment.strategy_id)
            strategy_reports.append(report)

        blocked_strategy_ids = [report["strategy_id"] for report in strategy_reports if bool(report["promotion_blocked"])]
        ready_strategy_ids = [report["strategy_id"] for report in strategy_reports if bool(report["data_ready"])]
        accepted_reports = [report for report in strategy_reports if report["strategy_id"] in accepted_strategy_ids]
        portfolio_metrics = self._analysis._portfolio_metrics(accepted_reports)
        hard_blocked = bool(blocked_strategy_ids)
        portfolio_passed = (
            not hard_blocked
            and bool(accepted_reports)
            and portfolio_metrics["annualized_return"] > 0.15
            and portfolio_metrics["max_drawdown"] < 0.15
            and portfolio_metrics["calmar"] > 1.0
        )
        minimum_history_coverage_ratio = round(
            min((float(report.get("minimum_coverage_ratio", 1.0)) for report in strategy_reports), default=1.0),
            4,
        )
        report_blocking_reasons = self._analysis._report_blocking_reasons(strategy_reports)

        return {
            "as_of": as_of,
            "minimum_history_start": date(2018, 1, 1),
            "strategy_reports": strategy_reports,
            "accepted_strategy_ids": accepted_strategy_ids,
            "ready_strategy_ids": ready_strategy_ids,
            "blocked_strategy_ids": blocked_strategy_ids,
            "blocked_count": len(blocked_strategy_ids),
            "hard_blocked": hard_blocked,
            "report_status": "blocked" if hard_blocked else ("passed" if portfolio_passed else "review"),
            "blocking_reasons": report_blocking_reasons,
            "minimum_history_coverage_ratio": minimum_history_coverage_ratio,
            "rejected_strategy_ids": [report["strategy_id"] for report in strategy_reports if report["strategy_id"] not in accepted_strategy_ids],
            "portfolio_metrics": portfolio_metrics,
            "portfolio_passed": portfolio_passed,
        }

    def _recommendations_from_report(self, report: dict[str, object]) -> dict[str, object]:
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
            reasons: list[str] = list(strategy_report.get("blocking_reasons", []))
            if bool(strategy_report.get("promotion_blocked")):
                action = "paper_only"
                if not reasons:
                    reasons.append("Research data is not ready; keep the strategy in paper-only mode.")
            elif strategy_report["strategy_id"] not in accepted:
                action = "drop"
                if not strategy_report["passed_validation"]:
                    reasons.append("Failed out-of-sample validation thresholds.")
                if float(strategy_report["max_selected_correlation"]) >= 0.7:
                    reasons.append("Correlation gate exceeded the 0.7 limit.")
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
                    "priority": self._analysis._action_priority(action),
                    "reasons": reasons,
                    "metrics": metrics,
                    "capacity_tier": strategy_report["capacity_tier"],
                    "capacity_score": strategy_report["capacity_score"],
                    "max_selected_correlation": strategy_report["max_selected_correlation"],
                    "data_source": strategy_report["data_source"],
                    "data_ready": strategy_report["data_ready"],
                    "promotion_blocked": strategy_report["promotion_blocked"],
                    "blocking_reasons": strategy_report["blocking_reasons"],
                    "validation_pass_rate": strategy_report["validation_pass_rate"],
                    "stability_score": strategy_report["stability_score"],
                    "stability_bucket": strategy_report["stability_bucket"],
                    "market_distribution": strategy_report["market_distribution"],
                }
            )

        next_actions = []
        if not report["portfolio_passed"]:
            next_actions.append("Portfolio layer does not yet clear the admission gate; keep allocation in paper-trading mode.")
        if any(bool(item.get("promotion_blocked")) for item in recommendations):
            next_actions.append("Complete local historical data coverage before promoting any blocked strategy beyond paper-only mode.")
        if any(item["action"] == "drop" for item in recommendations):
            next_actions.append("Remove failed or over-correlated strategies from the candidate set before the next rollout review.")
        if any(item["action"] == "paper_only" for item in recommendations):
            next_actions.append("Keep limited-capacity option overlays in research or low-allocation mode.")
        if not next_actions:
            next_actions.append("Current accepted strategies can stay in the candidate set for the next validation cycle.")

        return {**report, "recommendations": recommendations, "next_actions": next_actions}

    def build_profit_scorecard(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        recommendation_report = self.recommend_strategy_actions(as_of, strategy_signals)
        return self._scorecard_from_recommendation_report(recommendation_report)

    def _scorecard_from_recommendation_report(self, recommendation_report: dict[str, object]) -> dict[str, object]:
        as_of = recommendation_report["as_of"]
        rows: list[dict[str, object]] = []
        deployable = 0
        paper_only = 0
        rejected = 0

        for recommendation in recommendation_report["recommendations"]:
            metrics = recommendation["metrics"]
            score = self._analysis._profitability_score(
                annualized_return=float(metrics["annualized_return"]),
                sharpe=float(metrics["sharpe"]),
                max_drawdown=float(metrics["max_drawdown"]),
                calmar=float(metrics["calmar"]),
                stability_score=float(recommendation["stability_score"]),
                capacity_score=float(recommendation["capacity_score"]),
                max_selected_correlation=float(recommendation["max_selected_correlation"]),
            )
            verdict = self._analysis._profitability_verdict(str(recommendation["action"]), score)
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
                    "data_source": recommendation["data_source"],
                    "data_ready": recommendation["data_ready"],
                    "promotion_blocked": recommendation["promotion_blocked"],
                    "blocking_reasons": recommendation["blocking_reasons"],
                    "market_distribution": recommendation["market_distribution"],
                    "reasons": recommendation["reasons"],
                }
            )

        rows.sort(key=lambda item: (item["verdict"] != "deploy_candidate", -float(item["profitability_score"])))
        blocked_strategy_ids = [
            str(item["strategy_id"])
            for item in rows
            if bool(item.get("promotion_blocked"))
        ]
        return {
            "as_of": as_of,
            "portfolio_passed": recommendation_report["portfolio_passed"],
            "portfolio_metrics": recommendation_report["portfolio_metrics"],
            "accepted_strategy_ids": recommendation_report["accepted_strategy_ids"],
            "blocked_strategy_ids": blocked_strategy_ids,
            "blocked_count": len(blocked_strategy_ids),
            "deploy_candidate_count": deployable,
            "paper_only_count": paper_only,
            "rejected_count": rejected,
            "rows": rows,
            "correlation_matrix": self._analysis._correlation_matrix(recommendation_report["strategy_reports"]),
            "reject_summary": self._analysis._reject_summary(rows),
            "verdict_groups": self._analysis._verdict_groups(rows),
            "next_actions": recommendation_report["next_actions"],
        }

    def strategy_detail(self, strategy_id: str, as_of: date, signals: list[Signal]) -> dict[str, object]:
        experiment = self._analysis._run_experiment(strategy_id, as_of, signals)
        scorecard = self.build_profit_scorecard(as_of, {strategy_id: signals})
        recommendation = scorecard["rows"][0] if scorecard["rows"] else {}
        metadata = strategy_metadata(strategy_id)
        monthly_returns = self._analysis._decode_monthly_returns(experiment)
        nav_curve = self._analysis._nav_curve_from_monthly_returns(monthly_returns)
        split_metrics = self._analysis._sample_split_metrics(monthly_returns, signals)
        coverage = self._analysis._strategy_history_coverage(signals, experiment.sample_start, as_of)
        coverage_threshold = self._analysis._history_coverage_threshold()
        data_ready = bool(experiment.assumptions.get("data_ready", False))
        blocking_reasons = self._blocking_reasons(experiment.assumptions, data_ready)
        missing_coverage_symbols = [
            str(item) for item in experiment.assumptions.get("missing_history_symbol_list", [])
        ] or self._analysis._missing_coverage_symbols(coverage, coverage_threshold)
        benchmark = self._analysis._benchmark_comparison(signals, experiment.sample_start, as_of, nav_curve)
        yearly_performance = self._analysis._yearly_performance(monthly_returns, benchmark.get("monthly_returns", []), experiment.sample_start)
        return {
            "as_of": as_of,
            "strategy_id": strategy_id,
            "signal_count": len(signals),
            "data_source": experiment.assumptions.get("data_source"),
            "data_ready": data_ready,
            "promotion_blocked": not data_ready,
            "blocking_reasons": blocking_reasons,
            "minimum_coverage_ratio": round(float(coverage.get("minimum_coverage_ratio", 0.0)), 4),
            "history_coverage_threshold": coverage_threshold,
            "missing_coverage_symbols": missing_coverage_symbols,
            "history_coverage_blockers": self._analysis._history_coverage_blockers(coverage, blocking_reasons),
            "fx_ready": bool(experiment.assumptions.get("fx_ready", True)),
            "missing_fx_pairs": list(experiment.assumptions.get("missing_fx_pairs", [])),
            "fx_blockers": list(experiment.assumptions.get("fx_blockers", [])),
            "fx_coverage": experiment.assumptions.get("fx_coverage", {}),
            "corporate_actions_ready": bool(experiment.assumptions.get("corporate_actions_ready", True)),
            "missing_corporate_action_symbols": list(experiment.assumptions.get("missing_corporate_action_symbols", [])),
            "corporate_action_blockers": list(experiment.assumptions.get("corporate_action_blockers", [])),
            "corporate_action_coverage": experiment.assumptions.get("corporate_action_coverage", {}),
            "signals": [
                {
                    "symbol": signal.instrument.symbol,
                    "market": signal.instrument.market.value,
                    "asset_class": signal.instrument.asset_class.value,
                    "side": signal.side.value,
                    "target_weight": signal.target_weight,
                    "reason": signal.reason,
                    "metadata": signal.metadata,
                    "signal_source": signal.metadata.get("signal_source"),
                    "indicator_snapshot": signal.metadata.get("indicator_snapshot", {}),
                }
                for signal in signals
            ],
            "signal_sources": sorted({str(signal.metadata.get("signal_source")) for signal in signals if signal.metadata.get("signal_source")}),
            "indicator_snapshots": [
                {
                    "symbol": signal.instrument.symbol,
                    "indicator_snapshot": signal.metadata.get("indicator_snapshot", {}),
                }
                for signal in signals
            ],
            "metadata": metadata,
            "metrics": experiment.metrics.model_dump(mode="json"),
            "sample_start": experiment.sample_start,
            "window_count": experiment.window_count,
            "walk_forward_windows": self._analysis._decode_walk_forward_details(experiment),
            "monthly_returns": monthly_returns,
            "monthly_table": self._analysis._monthly_return_table(monthly_returns, experiment.sample_start),
            "nav_curve": nav_curve,
            "drawdown_curve": self._analysis._drawdown_curve_from_nav_curve(nav_curve),
            "sample_split": split_metrics,
            "history_coverage": coverage,
            "benchmark": benchmark,
            "yearly_performance": yearly_performance,
            "recommendation": recommendation,
            "assumptions": {
                "data_source": experiment.assumptions.get("data_source"),
                "data_ready": experiment.assumptions.get("data_ready"),
                "data_blockers": experiment.assumptions.get("data_blockers"),
                "threshold_validation_passed": experiment.assumptions.get("threshold_validation_passed"),
                "history_complete": experiment.assumptions.get("history_complete"),
                "history_symbols": experiment.assumptions.get("history_symbols"),
                "missing_history_symbols": experiment.assumptions.get("missing_history_symbols"),
                "fx_ready": experiment.assumptions.get("fx_ready"),
                "missing_fx_pairs": experiment.assumptions.get("missing_fx_pairs"),
                "fx_blockers": experiment.assumptions.get("fx_blockers"),
                "corporate_actions_ready": experiment.assumptions.get("corporate_actions_ready"),
                "missing_corporate_action_symbols": experiment.assumptions.get("missing_corporate_action_symbols"),
                "corporate_action_blockers": experiment.assumptions.get("corporate_action_blockers"),
                "commission_bps": experiment.assumptions.get("commission_bps"),
                "slippage_bps": experiment.assumptions.get("slippage_bps"),
                "total_cost_bps": experiment.assumptions.get("total_cost_bps"),
            },
        }

    def _blocking_reasons(self, assumptions: dict[str, object], data_ready: bool) -> list[str]:
        blocking_reasons = [str(item) for item in assumptions.get("data_blockers", [])]
        if not data_ready and not blocking_reasons:
            return [self._DEFAULT_BLOCKING_REASON]
        return blocking_reasons
