from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from tradingcat.backtest.engine import EventDrivenBacktester
from tradingcat.domain.models import BacktestExperiment, Signal
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.research_ideas import ResearchIdeasService
from tradingcat.services.strategy_analysis import StrategyAnalysisService


logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(
        self,
        repository: BacktestExperimentRepository,
        backtester: EventDrivenBacktester | None = None,
        market_data: MarketDataService | None = None,
    ) -> None:
        self._repository = repository
        self._backtester = backtester or EventDrivenBacktester()
        self._market_data = market_data
        self._experiments = repository.load()
        self._strategy_registry: dict[str, object] = {}
        self.strategy_analysis = StrategyAnalysisService(self.run_experiment, self._backtester, self._market_data)
        self.research_ideas = ResearchIdeasService(self.strategy_analysis)

    def register_strategies(self, strategies: list[object]) -> None:
        for strategy in strategies:
            self._strategy_registry[strategy.strategy_id] = strategy  # type: ignore[attr-defined]

    def run_experiment(self, strategy_id: str, as_of: date, signals: list[Signal], strategy: object | None = None) -> BacktestExperiment:
        if strategy is None:
            strategy = self._strategy_registry.get(strategy_id)
        sample_start = date(2018, 1, 1)
        all_signals = list(signals)
        if strategy is not None:
            for probe_month in range(1, 13):
                probe_date = date(as_of.year, probe_month, 1)
                for day_offset in [0, 7, 14, 24]:
                    try:
                        probe = date(probe_date.year, probe_date.month, min(probe_date.day + day_offset, 28))
                        all_signals.extend(strategy.generate_signals(probe))  # type: ignore[union-attr]
                    except Exception:
                        logger.exception("Strategy signal probe failed", extra={"strategy_id": strategy_id, "probe_date": probe_date.isoformat()})
        cost_assumptions = self._backtester.cost_assumptions(all_signals or signals)
        history_by_symbol = self._load_signal_history(all_signals or signals, sample_start, as_of)
        signal_symbols = {signal.instrument.symbol for signal in all_signals} if all_signals else {signal.instrument.symbol for signal in signals}
        complete_history = bool(signal_symbols) and signal_symbols.issubset(set(history_by_symbol))
        corporate_actions_by_symbol = self._load_signal_corporate_actions(all_signals or signals, sample_start, as_of)
        fx_rates_by_pair = self._load_signal_fx_rates(all_signals or signals, sample_start, as_of, base_currency="CNY")
        if complete_history:
            metrics, windows, monthly_returns, ledger = self._backtester.run_walk_forward_from_history(
                strategy_id,
                signals,
                history_by_symbol,
                corporate_actions_by_symbol,
                fx_rates_by_pair,
                as_of,
                base_currency="CNY",
                start_date=sample_start,
                strategy=strategy,
            )
            data_source = "historical"
        else:
            metrics, windows, monthly_returns = self._backtester.run_walk_forward(strategy_id, signals, as_of, start_date=sample_start)
            ledger = self._backtester._build_portfolio_ledger(monthly_returns, self._backtester._estimate_turnover(signals), cost_assumptions["total_cost_bps"])
            data_source = "synthetic"
        correlation_key = "|".join(f"{value:.6f}" for value in monthly_returns)
        replay_inputs = self._build_replay_inputs(strategy_id, as_of, signals, sample_start, data_source)
        experiment = BacktestExperiment(
            strategy_id=strategy_id,
            as_of=as_of,
            signal_count=len(signals),
            metrics=metrics,
            sample_start=sample_start,
            window_count=len(windows),
            passed_validation=(
                metrics.annualized_return > 0.12
                and metrics.max_drawdown < 0.12
                and metrics.sharpe > 1.0
                and bool(windows)
                and all(bool(window["passed"]) for window in windows)
            ),
            assumptions={
                "commission_bps": cost_assumptions["commission_bps"],
                "slippage_bps": cost_assumptions["slippage_bps"],
                "total_cost_bps": cost_assumptions["total_cost_bps"],
                "walk_forward_start": "2018-01-01",
                "walk_forward_window_months": 6,
                "walk_forward_windows": len(windows),
                "passed_windows": sum(1 for window in windows if bool(window["passed"])),
                "market_count": len({signal.instrument.market.value for signal in signals}),
                "correlation_key": correlation_key,
                "monthly_return_count": len(monthly_returns),
                "data_source": data_source,
                "history_symbols": len(history_by_symbol),
                "missing_history_symbols": len(signal_symbols - set(history_by_symbol)),
                "history_complete": complete_history,
                "fx_pairs": len(fx_rates_by_pair),
                "corporate_action_symbols": len([symbol for symbol, actions in corporate_actions_by_symbol.items() if actions]),
                "ledger_entries": len(ledger),
                "replay_inputs": replay_inputs,
                "replay_fingerprint": self._fingerprint(replay_inputs),
            },
        )
        experiment.assumptions["walk_forward_details"] = str(windows)
        experiment.assumptions["ledger_preview"] = str([entry.model_dump(mode="json") for entry in (ledger[:2] + ledger[-2:] if len(ledger) > 4 else ledger)])
        self._experiments[experiment.id] = experiment
        self._repository.save(self._experiments)
        return experiment

    def list_experiments(self) -> list[BacktestExperiment]:
        return sorted(self._experiments.values(), key=lambda item: item.started_at, reverse=True)

    def compare_experiments(self, left_id: str, right_id: str) -> dict[str, object]:
        left = self._experiments[left_id]
        right = self._experiments[right_id]
        left_inputs = self._normalize_replay_inputs(left.assumptions.get("replay_inputs", {}))
        right_inputs = self._normalize_replay_inputs(right.assumptions.get("replay_inputs", {}))
        left_metrics = left.metrics.model_dump(mode="json")
        right_metrics = right.metrics.model_dump(mode="json")
        return {
            "left": {"id": left.id, "strategy_id": left.strategy_id, "replay_fingerprint": left.assumptions.get("replay_fingerprint")},
            "right": {"id": right.id, "strategy_id": right.strategy_id, "replay_fingerprint": right.assumptions.get("replay_fingerprint")},
            "same_inputs": left_inputs == right_inputs,
            "input_diff": self._diff_dicts(left_inputs, right_inputs),
            "metric_diff": self._diff_metrics(left_metrics, right_metrics),
        }

    def summarize_strategy_report(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.summarize_strategy_report(as_of, strategy_signals)

    def summarize_strategy_stability(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.summarize_strategy_stability(as_of, strategy_signals)

    def recommend_strategy_actions(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.recommend_strategy_actions(as_of, strategy_signals)

    def build_profit_scorecard(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.build_profit_scorecard(as_of, strategy_signals)

    def strategy_detail(self, strategy_id: str, as_of: date, signals: list[Signal]) -> dict[str, object]:
        return self.strategy_analysis.strategy_detail(strategy_id, as_of, signals)

    def suggest_experiments(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.research_ideas.suggest_experiments(as_of, strategy_signals)

    def summarize_news(self, items: list[dict[str, object]]) -> dict[str, object]:
        return self.research_ideas.summarize_news(items)

    def calculate_asset_correlation(self, symbols: list[str], start: date, end: date) -> dict[str, dict[str, float]]:
        return self.strategy_analysis.calculate_asset_correlation(symbols, start, end)

    def clear(self) -> None:
        self._experiments = {}
        self._repository.save(self._experiments)

    def _load_signal_history(self, signals: list[Signal], start: date, end: date):
        if self._market_data is None or not signals:
            return {}
        return self._market_data.ensure_history(sorted({signal.instrument.symbol for signal in signals}), start, end)

    def _load_signal_corporate_actions(self, signals: list[Signal], start: date, end: date):
        if self._market_data is None or not signals:
            return {}
        return self._market_data.ensure_corporate_actions(sorted({signal.instrument.symbol for signal in signals}), start, end)

    def _load_signal_fx_rates(self, signals: list[Signal], start: date, end: date, base_currency: str):
        if self._market_data is None or not signals:
            return {}
        quote_currencies = sorted(
            {
                signal.instrument.currency.upper()
                for signal in signals
                if signal.instrument.currency.upper() != base_currency.upper()
            }
        )
        return self._market_data.ensure_fx_rates(base_currency, quote_currencies, start, end)

    def _build_replay_inputs(self, strategy_id: str, as_of: date, signals: list[Signal], sample_start: date, data_source: str) -> dict[str, object]:
        return {
            "strategy_id": strategy_id,
            "as_of": as_of.isoformat(),
            "sample_start": sample_start.isoformat(),
            "data_source": data_source,
            "signal_count": len(signals),
            "signals": [
                {
                    "symbol": signal.instrument.symbol,
                    "market": signal.instrument.market.value,
                    "side": signal.side.value,
                    "target_weight": signal.target_weight,
                    "asset_class": signal.instrument.asset_class.value,
                }
                for signal in sorted(signals, key=lambda item: (item.instrument.market.value, item.instrument.symbol))
            ],
            "parameters": {
                "commission_bps": 5.0,
                "slippage_bps": 10.0,
                "walk_forward_window_months": 6,
                "base_currency": "CNY",
            },
        }

    def _fingerprint(self, payload: dict[str, object]) -> str:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def _normalize_replay_inputs(self, payload: object) -> dict[str, object]:
        return payload if isinstance(payload, dict) else {}

    def _diff_dicts(self, left: dict[str, object], right: dict[str, object]) -> dict[str, dict[str, object]]:
        diff: dict[str, dict[str, object]] = {}
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                diff[key] = {"left": left.get(key), "right": right.get(key)}
        return diff

    def _diff_metrics(self, left: dict[str, object], right: dict[str, object]) -> dict[str, dict[str, object]]:
        diff: dict[str, dict[str, object]] = {}
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                diff[key] = {"left": left.get(key), "right": right.get(key)}
        return diff
