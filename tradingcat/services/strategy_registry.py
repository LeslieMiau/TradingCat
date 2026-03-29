from __future__ import annotations

from datetime import date

from tradingcat.domain.models import Signal


class StrategyRegistry:
    def __init__(self, strategies: list[object]) -> None:
        self._strategies = {strategy.strategy_id: strategy for strategy in strategies}  # type: ignore[attr-defined]

    def all(self) -> list[object]:
        return list(self._strategies.values())

    def get(self, strategy_id: str) -> object:
        return self._strategies[strategy_id]

    def select(self, strategy_ids: list[str] | set[str]) -> list[object]:
        allowed = set(strategy_ids)
        return [strategy for strategy_id, strategy in self._strategies.items() if strategy_id in allowed]


class StrategySignalProvider:
    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def execution_signals_for_strategy(self, strategy: object, as_of: date) -> list[Signal]:
        return [
            signal
            for signal in strategy.generate_signals(as_of)  # type: ignore[attr-defined]
            if str(signal.metadata.get("execution_mode", "live")) != "research_only"
        ]

    def strategy_signal_map(
        self,
        as_of: date,
        *,
        strategy_ids: list[str] | None = None,
    ) -> dict[str, list[Signal]]:
        strategies = self._registry.all() if strategy_ids is None else self._registry.select(strategy_ids)
        return {
            strategy.strategy_id: strategy.generate_signals(as_of)  # type: ignore[attr-defined]
            for strategy in strategies
        }

    def execution_signals(self, as_of: date, *, strategy_ids: list[str]) -> list[Signal]:
        signals: list[Signal] = []
        for strategy in self._registry.select(strategy_ids):
            signals.extend(self.execution_signals_for_strategy(strategy, as_of))
        return signals

    def execution_signals_with_fallback(
        self,
        as_of: date,
        *,
        strategy_ids: list[str],
        fallback_strategy_ids: list[str],
        minimum_signal_count: int = 3,
    ) -> list[Signal]:
        signals = self.execution_signals(as_of, strategy_ids=strategy_ids)
        if len(signals) >= minimum_signal_count:
            return signals
        fallback: list[Signal] = []
        for strategy in self._registry.select(fallback_strategy_ids):
            fallback.extend(self.execution_signals_for_strategy(strategy, as_of))
        return fallback or signals
