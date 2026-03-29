from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from tradingcat.backtest.engine import EventDrivenBacktester
from tradingcat.domain.models import BacktestExperiment, Signal
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.services.market_data import MarketDataService


logger = logging.getLogger(__name__)


class StrategyExperimentService:
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
        corporate_action_coverage = self._load_signal_corporate_action_coverage(all_signals or signals, sample_start, as_of)
        corporate_actions_by_symbol = dict(corporate_action_coverage.get("actions_by_symbol", {}))
        fx_coverage = self._load_signal_fx_coverage(all_signals or signals, sample_start, as_of, base_currency="CNY")
        fx_rates_by_pair = dict(fx_coverage.get("rates_by_pair", {}))
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
        threshold_validation_passed = (
            metrics.annualized_return > 0.12
            and metrics.max_drawdown < 0.12
            and metrics.sharpe > 1.0
            and bool(windows)
            and all(bool(window["passed"]) for window in windows)
        )
        missing_history_symbols = len(signal_symbols - set(history_by_symbol))
        corporate_actions_ready = bool(corporate_action_coverage.get("ready", True))
        missing_corporate_action_symbols = [str(item) for item in corporate_action_coverage.get("missing_symbols", [])]
        corporate_action_blockers = [str(item) for item in corporate_action_coverage.get("blockers", [])]
        fx_ready = bool(fx_coverage.get("ready", True))
        missing_fx_pairs = [str(item) for item in fx_coverage.get("missing_quote_currencies", [])]
        fx_blockers = [str(item) for item in fx_coverage.get("blockers", [])]
        data_ready = data_source == "historical" and complete_history and bool(history_by_symbol) and corporate_actions_ready and fx_ready
        data_blockers = self._research_data_blockers(
            data_source=data_source,
            signal_symbol_count=len(signal_symbols),
            history_symbol_count=len(history_by_symbol),
            missing_history_symbols=missing_history_symbols,
            missing_corporate_action_symbols=missing_corporate_action_symbols,
            corporate_action_blockers=corporate_action_blockers,
            missing_fx_pairs=missing_fx_pairs,
            fx_blockers=fx_blockers,
        )
        correlation_key = "|".join(f"{value:.6f}" for value in monthly_returns)
        replay_inputs = self._build_replay_inputs(strategy_id, as_of, signals, sample_start, data_source)
        experiment = BacktestExperiment(
            strategy_id=strategy_id,
            as_of=as_of,
            signal_count=len(signals),
            metrics=metrics,
            sample_start=sample_start,
            window_count=len(windows),
            passed_validation=threshold_validation_passed and data_ready,
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
                "data_ready": data_ready,
                "data_blockers": data_blockers,
                "threshold_validation_passed": threshold_validation_passed,
                "history_symbols": len(history_by_symbol),
                "missing_history_symbols": missing_history_symbols,
                "history_complete": complete_history,
                "fx_pairs": len(fx_rates_by_pair),
                "fx_ready": fx_ready,
                "missing_fx_pairs": missing_fx_pairs,
                "fx_blockers": fx_blockers,
                "fx_coverage": self._serialize_fx_coverage(fx_coverage),
                "corporate_action_symbols": len([symbol for symbol, actions in corporate_actions_by_symbol.items() if actions]),
                "corporate_actions_ready": corporate_actions_ready,
                "missing_corporate_action_symbols": missing_corporate_action_symbols,
                "corporate_action_blockers": corporate_action_blockers,
                "corporate_action_coverage": self._serialize_corporate_action_coverage(corporate_action_coverage),
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

    def clear(self) -> None:
        self._experiments = {}
        self._repository.save(self._experiments)

    def _load_signal_history(self, signals: list[Signal], start: date, end: date):
        if self._market_data is None or not signals:
            return {}
        # Long walk-forward reads should not overwrite the short-window cache used by live signal generation.
        return self._market_data.history_snapshot(sorted({signal.instrument.symbol for signal in signals}), start, end)

    def _load_signal_corporate_action_coverage(self, signals: list[Signal], start: date, end: date) -> dict[str, object]:
        if self._market_data is None or not signals:
            return {
                "ready": True,
                "missing_symbols": [],
                "blockers": [],
                "reports": [],
                "actions_by_symbol": {},
            }
        symbols = sorted(
            {
                str(signal.metadata.get("underlying_symbol") or signal.instrument.symbol)
                for signal in signals
                if signal.instrument.asset_class.value != "option"
            }
        )
        if not symbols:
            return {
                "ready": True,
                "missing_symbols": [],
                "blockers": [],
                "reports": [],
                "actions_by_symbol": {},
            }
        return self._market_data.summarize_corporate_actions_coverage(symbols, start, end)

    def _load_signal_fx_coverage(self, signals: list[Signal], start: date, end: date, base_currency: str) -> dict[str, object]:
        if self._market_data is None or not signals:
            return {
                "ready": True,
                "missing_quote_currencies": [],
                "blockers": [],
                "reports": [],
                "rates_by_pair": {},
            }
        quote_currencies = sorted(
            {
                signal.instrument.currency.upper()
                for signal in signals
                if signal.instrument.currency.upper() != base_currency.upper()
            }
        )
        return self._market_data.summarize_fx_coverage(base_currency, quote_currencies, start, end)

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
                    "reason": signal.reason,
                    "metadata": signal.metadata,
                }
                for signal in signals
            ],
        }

    def _fingerprint(self, payload: dict[str, object]) -> str:
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _normalize_replay_inputs(self, payload: object) -> dict[str, object]:
        if isinstance(payload, dict):
            return payload
        if not payload:
            return {}
        try:
            return json.loads(str(payload))
        except Exception:
            return {}

    def _diff_dicts(self, left: dict[str, object], right: dict[str, object]) -> dict[str, dict[str, object]]:
        changed_keys = sorted(set(left.keys()) | set(right.keys()))
        diff: dict[str, dict[str, object]] = {}
        for key in changed_keys:
            if left.get(key) != right.get(key):
                diff[key] = {"left": left.get(key), "right": right.get(key)}
        return diff

    def _diff_metrics(self, left: dict[str, object], right: dict[str, object]) -> dict[str, float]:
        diff: dict[str, float] = {}
        for key in sorted(set(left.keys()) & set(right.keys())):
            left_value = left.get(key)
            right_value = right.get(key)
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                diff[key] = round(float(right_value) - float(left_value), 6)
        return diff

    def _research_data_blockers(
        self,
        *,
        data_source: str,
        signal_symbol_count: int,
        history_symbol_count: int,
        missing_history_symbols: int,
        missing_corporate_action_symbols: list[str],
        corporate_action_blockers: list[str],
        missing_fx_pairs: list[str],
        fx_blockers: list[str],
    ) -> list[str]:
        blockers: list[str] = []
        if data_source != "historical":
            blockers.append("Research used synthetic fallback data; keep the strategy out of keep/active until local history is complete.")
        elif signal_symbol_count == 0:
            blockers.append("Strategy produced no historical-underlying symbols for validation.")
        elif history_symbol_count < signal_symbol_count:
            blockers.append(
                f"Historical coverage is incomplete for {missing_history_symbols} symbol(s); repair local history before promoting the strategy."
            )
        blockers.extend(corporate_action_blockers)
        blockers.extend(fx_blockers)
        if missing_corporate_action_symbols:
            blockers.append(
                "Corporate actions are missing for: "
                + ", ".join(sorted(dict.fromkeys(missing_corporate_action_symbols)))
                + "."
            )
        if missing_fx_pairs:
            blockers.append(
                "FX conversion data is missing for quote currencies: "
                + ", ".join(sorted(dict.fromkeys(missing_fx_pairs)))
                + "."
            )
        deduped: list[str] = []
        seen: set[str] = set()
        for blocker in blockers:
            if blocker in seen:
                continue
            seen.add(blocker)
            deduped.append(blocker)
        return deduped

    def _serialize_fx_coverage(self, coverage: dict[str, object]) -> dict[str, object]:
        reports = [
            {
                "quote_currency": item.get("quote_currency"),
                "status": item.get("status"),
                "rate_count": int(item.get("rate_count", 0)),
            }
            for item in coverage.get("reports", [])
            if isinstance(item, dict)
        ]
        return {
            "ready": bool(coverage.get("ready", True)),
            "missing_quote_currencies": list(coverage.get("missing_quote_currencies", [])),
            "blockers": list(coverage.get("blockers", [])),
            "reports": reports,
        }

    def _serialize_corporate_action_coverage(self, coverage: dict[str, object]) -> dict[str, object]:
        reports = [
            {
                "symbol": item.get("symbol"),
                "status": item.get("status"),
                "action_count": int(item.get("action_count", 0)),
            }
            for item in coverage.get("reports", [])
            if isinstance(item, dict)
        ]
        return {
            "ready": bool(coverage.get("ready", True)),
            "missing_symbols": list(coverage.get("missing_symbols", [])),
            "blockers": list(coverage.get("blockers", [])),
            "reports": reports,
        }
