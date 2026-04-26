from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.stats import spearmanr

from tradingcat.domain.models import Bar


@dataclass
class FactorResult:
    name: str
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_win_rate: float
    layer_returns: list[float]  # L1..L5 forward returns
    monotonicity: float  # 1.0 = perfectly monotonic, -1.0 = inverse, 0.0 = flat
    is_significant: bool
    sample_count: int


@dataclass
class FactorReport:
    as_of: date
    total_factors: int
    significant_count: int
    top_factors: list[FactorResult]
    factor_correlation: dict[str, dict[str, float]] = field(default_factory=dict)


class FactorAnalyzer:
    """Evaluate predictive power of features via IC and layer backtest."""

    def __init__(self, features: dict[str, dict[str, float | None]],
                 forward_returns: dict[str, float]) -> None:
        self._features = features
        self._forward_returns = forward_returns

    def rank_ic(self, feature_name: str) -> float | None:
        values: list[float] = []
        returns: list[float] = []
        for symbol in self._features:
            val = self._features[symbol].get(feature_name)
            ret = self._forward_returns.get(symbol)
            if val is not None and ret is not None and np.isfinite(val):
                values.append(val)
                returns.append(ret)
        if len(values) < 10:
            return None
        rho, _ = spearmanr(values, returns)
        return float(rho) if not np.isnan(rho) else None

    def ic_history(self, feature_name: str,
                   period_features: list[dict[str, dict[str, float | None]]],
                   period_returns: list[dict[str, float]]) -> list[float]:
        """Compute IC for each period, return the time series."""
        ics: list[float] = []
        for feat_dict, ret_dict in zip(period_features, period_returns):
            self._features = feat_dict
            self._forward_returns = ret_dict
            ic = self.rank_ic(feature_name)
            if ic is not None:
                ics.append(ic)
        return ics

    def factor_result(self, feature_name: str,
                      period_features: list[dict[str, dict[str, float | None]]],
                      period_returns: list[dict[str, float]]) -> FactorResult:
        ics = self.ic_history(feature_name, period_features, period_returns)
        if len(ics) < 3:
            return FactorResult(
                name=feature_name, ic_mean=0.0, ic_std=0.0, ic_ir=0.0,
                ic_win_rate=0.0, layer_returns=[0.0]*5, monotonicity=0.0,
                is_significant=False, sample_count=len(ics),
            )
        ic_mean = float(np.mean(ics))
        ic_std = float(np.std(ics, ddof=1)) if len(ics) > 1 else 0.0
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0
        ic_win_rate = float(np.mean([1.0 if ic > 0 else 0.0 for ic in ics]))
        layer_returns = self._layer_backtest(feature_name)
        monotonicity = self._monotonicity(layer_returns)
        is_significant = abs(ic_ir) > 0.5 and abs(ic_mean) > 0.02 and len(ics) >= 5
        return FactorResult(
            name=feature_name, ic_mean=ic_mean, ic_std=ic_std, ic_ir=ic_ir,
            ic_win_rate=ic_win_rate, layer_returns=layer_returns,
            monotonicity=monotonicity, is_significant=is_significant,
            sample_count=len(ics),
        )

    def _layer_backtest(self, feature_name: str, layers: int = 5) -> list[float]:
        """Sort symbols by feature value, split into N layers, compute avg forward return per layer."""
        paired: list[tuple[float, float]] = []
        for symbol in self._features:
            val = self._features[symbol].get(feature_name)
            ret = self._forward_returns.get(symbol)
            if val is not None and ret is not None and np.isfinite(val):
                paired.append((float(val), float(ret)))
        if len(paired) < layers * 3:
            return [0.0] * layers
        paired.sort(key=lambda x: x[0])
        size = len(paired) // layers
        layer_returns = []
        for i in range(layers):
            batch = paired[i * size: (i + 1) * size] if i < layers - 1 else paired[i * size:]
            layer_returns.append(float(np.mean([r for _, r in batch])))
        return layer_returns

    @staticmethod
    def _monotonicity(layer_returns: list[float]) -> float:
        """Score how monotonic the layer returns are. 1.0 = perfectly increasing."""
        if len(layer_returns) < 2:
            return 0.0
        ups = sum(1 for i in range(1, len(layer_returns)) if layer_returns[i] > layer_returns[i-1])
        downs = sum(1 for i in range(1, len(layer_returns)) if layer_returns[i] < layer_returns[i-1])
        return float((ups - downs) / (len(layer_returns) - 1))

    def factor_correlation_matrix(self,
                                   factor_names: list[str]) -> dict[str, dict[str, float]]:
        """Compute pairwise Spearman correlation between factor values."""
        vectors: dict[str, list[float]] = {name: [] for name in factor_names}
        for symbol in self._features:
            for name in factor_names:
                val = self._features[symbol].get(name)
                vectors[name].append(float(val) if val is not None and np.isfinite(val) else 0.0)
        matrix: dict[str, dict[str, float]] = {}
        for n1 in factor_names:
            matrix[n1] = {}
            for n2 in factor_names:
                rho, _ = spearmanr(vectors[n1], vectors[n2])
                matrix[n1][n2] = float(rho) if not np.isnan(rho) else 0.0
        return matrix

    def build_report(self, as_of: date, feature_names: list[str],
                     period_features: list[dict[str, dict[str, float | None]]],
                     period_returns: list[dict[str, float]]) -> FactorReport:
        results = [self.factor_result(name, period_features, period_returns)
                   for name in feature_names]
        results.sort(key=lambda r: abs(r.ic_ir), reverse=True)
        significant = [r for r in results if r.is_significant]
        corr = self.factor_correlation_matrix([r.name for r in results[:20]])
        return FactorReport(
            as_of=as_of,
            total_factors=len(results),
            significant_count=len(significant),
            top_factors=results[:20],
            factor_correlation=corr,
        )

    def save_report(self, report: FactorReport, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "as_of": str(report.as_of),
            "total_factors": report.total_factors,
            "significant_count": report.significant_count,
            "top_factors": [
                {"name": r.name, "ic_mean": r.ic_mean, "ic_std": r.ic_std,
                 "ic_ir": r.ic_ir, "ic_win_rate": r.ic_win_rate,
                 "layer_returns": r.layer_returns, "monotonicity": r.monotonicity,
                 "is_significant": r.is_significant, "sample_count": r.sample_count}
                for r in report.top_factors
            ],
            "factor_correlation": report.factor_correlation,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Factor report saved to {path}")
