from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.optimize import minimize

warnings.filterwarnings("ignore", category=RuntimeWarning)

OptimizationMethod = Literal["risk_parity", "mean_variance", "min_cvar", "black_litterman"]


@dataclass
class OptimizationResult:
    weights: dict[str, float]
    method: OptimizationMethod
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    max_weight: float
    concentration: float  # Herfindahl index (1/N = diverse, 1.0 = concentrated)
    success: bool
    message: str


@dataclass
class OptimizerConfig:
    max_single_weight: float = 0.20
    max_market_exposure: dict[str, float] = field(default_factory=lambda: {"US": 0.6, "HK": 0.4, "CN": 0.3})
    min_weight: float = 0.01
    max_turnover: float = 0.30
    risk_free_rate: float = 0.025


class PortfolioOptimizer:
    """Multi-method portfolio optimizer with constraints."""

    def __init__(self, config: OptimizerConfig | None = None) -> None:
        self._config = config or OptimizerConfig()

    def optimize(self, symbols: list[str], expected_returns: np.ndarray | None = None,
                 cov_matrix: np.ndarray | None = None,
                 method: OptimizationMethod = "risk_parity",
                 current_weights: dict[str, float] | None = None,
                 market_map: dict[str, str] | None = None,
                 turnover: float | None = None) -> OptimizationResult:
        if cov_matrix is None:
            n = len(symbols)
            cov_matrix = np.eye(n) * 0.04 + 0.01
        if expected_returns is None:
            expected_returns = np.array([0.12] * len(symbols))

        n = len(symbols)
        bounds = [(self._config.min_weight, self._config.max_single_weight)] * n
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        if market_map:
            for mkt, limit in self._config.max_market_exposure.items():
                mkt_indices = [i for i, s in enumerate(symbols) if market_map.get(s) == mkt]
                if mkt_indices:
                    constraints.append({
                        "type": "ineq",
                        "fun": lambda w, idx=mkt_indices, lim=limit: lim - np.sum(w[idx]),
                    })

        if current_weights and turnover is not None:
            constraints.append({
                "type": "ineq",
                "fun": lambda w, cw=current_weights, sym=symbols: self._config.max_turnover - 0.5 * np.sum(np.abs(w - np.array([cw.get(s, 0.0) for s in sym]))),
            })

        x0 = np.array([1.0 / n] * n)
        x_start = x0.copy()
        # Enforce market exposure constraints in starting point
        if market_map:
            for mkt, mkt_limit in self._config.max_market_exposure.items():
                mkt_indices = [i for i, s in enumerate(symbols) if market_map.get(s) == mkt]
                if mkt_indices and len(mkt_indices) > 0:
                    current = np.sum(x_start[mkt_indices])
                    if current > mkt_limit:
                        scale = mkt_limit / current
                        x_start[mkt_indices] *= scale
        x_start = np.clip(x_start, self._config.min_weight, self._config.max_single_weight)
        x_start = x_start / np.sum(x_start)

        if method == "risk_parity":
            result = self._risk_parity(x_start, cov_matrix, bounds, constraints)
        elif method == "mean_variance":
            result = self._mean_variance(x_start, expected_returns, cov_matrix, bounds, constraints)
        elif method == "min_cvar":
            result = self._min_cvar(x_start, expected_returns, cov_matrix, bounds, constraints)
        else:
            result = self._risk_parity(x_start, cov_matrix, bounds, constraints)

        w = result.x if result.success else x0
        w = w / np.sum(w)  # renormalize
        weights = dict(zip(symbols, [round(float(v), 6) for v in w]))
        port_return = float(np.dot(w, expected_returns))
        port_vol = float(np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))))
        sharpe = (port_return - self._config.risk_free_rate) / port_vol if port_vol > 0 else 0.0
        concentration = float(np.sum(w ** 2) * n)  # 1.0 = uniform
        return OptimizationResult(
            weights=weights, method=method, expected_return=port_return,
            expected_volatility=port_vol, sharpe_ratio=sharpe,
            max_weight=float(np.max(w)), concentration=concentration,
            success=result.success,
            message=result.message if hasattr(result, "message") else "OK",
        )

    def _risk_parity(self, x0: np.ndarray, cov: np.ndarray,
                     bounds: list[tuple[float, float]], constraints: list[dict],
                     maxiter: int = 2000):
        def risk_contribution(w: np.ndarray) -> np.ndarray:
            portfolio_var = np.dot(w.T, np.dot(cov, w))
            return w * (np.dot(cov, w)) / np.sqrt(portfolio_var) if portfolio_var > 0 else w

        def risk_parity_objective(w: np.ndarray) -> float:
            rc = risk_contribution(w)
            target = 1.0 / len(w)
            return float(np.sum((rc - target) ** 2))

        res = minimize(risk_parity_objective, x0, method="SLSQP",
                       bounds=bounds, constraints=constraints,
                       options={"maxiter": maxiter, "ftol": 1e-14, "eps": 1e-8})
        if not res.success:
            res = minimize(risk_parity_objective, x0 + np.random.RandomState(42).uniform(-0.02, 0.02, len(x0)),
                          method="SLSQP", bounds=bounds, constraints=constraints,
                          options={"maxiter": maxiter, "ftol": 1e-14, "eps": 1e-8})
        return res

    def _mean_variance(self, x0: np.ndarray, mu: np.ndarray, cov: np.ndarray,
                       bounds: list[tuple[float, float]], constraints: list[dict],
                       maxiter: int = 2000):
        def neg_sharpe(w: np.ndarray) -> float:
            ret = float(np.dot(w, mu))
            vol = float(np.sqrt(np.dot(w.T, np.dot(cov, w))))
            return -(ret - self._config.risk_free_rate) / vol if vol > 0 else 0.0

        res = minimize(neg_sharpe, x0, method="SLSQP",
                        bounds=bounds, constraints=constraints,
                        options={"maxiter": maxiter, "ftol": 1e-14, "eps": 1e-8})
        if not res.success:
            res = minimize(neg_sharpe, x0 + np.random.RandomState(42).uniform(-0.02, 0.02, len(x0)),
                          method="SLSQP", bounds=bounds, constraints=constraints,
                          options={"maxiter": maxiter, "ftol": 1e-14, "eps": 1e-8})
        return res

    def _min_cvar(self, x0: np.ndarray, mu: np.ndarray, cov: np.ndarray,
                  bounds: list[tuple[float, float]], constraints: list[dict],
                  alpha: float = 0.05, n_scenarios: int = 10000,
                  maxiter: int = 1000):
        np.random.seed(42)
        L = np.linalg.cholesky(cov + np.eye(len(cov)) * 1e-8)
        scenarios = mu.reshape(-1, 1) + L @ np.random.randn(len(mu), n_scenarios)

        def cvar(w: np.ndarray) -> float:
            port_returns = np.dot(w.T, scenarios)
            var = np.percentile(port_returns, alpha * 100)
            cvar_val = float(np.mean(port_returns[port_returns <= var])) if np.any(port_returns <= var) else var
            return cvar_val  # minimize negative = maximize CVaR (less negative is better)

        return minimize(cvar, x0, method="SLSQP",
                        bounds=bounds, constraints=constraints,
                        options={"maxiter": maxiter, "ftol": 1e-10})

    @staticmethod
    def ledoit_wolf_covariance(returns_matrix: np.ndarray) -> np.ndarray:
        """Ledoit-Wolf shrinkage covariance estimation."""
        n, p = returns_matrix.shape
        if n < 2:
            return np.cov(returns_matrix, rowvar=False) if p > 1 else np.array([[1.0]])

        sample_cov = np.cov(returns_matrix, rowvar=False)
        if p == 1:
            return np.array([[np.var(returns_matrix)]])

        mean_returns = np.mean(returns_matrix, axis=0)
        var_mean = np.mean(np.diag(sample_cov))

        # Shrinkage towards constant correlation
        correlation = np.corrcoef(returns_matrix, rowvar=False)
        avg_corr = (np.sum(correlation) - p) / (p * (p - 1))
        prior = np.ones_like(sample_cov) * (avg_corr * np.sqrt(np.outer(np.diag(sample_cov), np.diag(sample_cov))))
        np.fill_diagonal(prior, np.diag(sample_cov))

        # Shrinkage intensity
        diff = sample_cov - prior
        gamma = float(np.sum(diff ** 2))
        if gamma == 0:
            return sample_cov

        pi_sum = 0.0
        for i in range(n):
            centered = returns_matrix[i] - mean_returns
            pi_sum += np.sum((np.outer(centered, centered) - sample_cov) ** 2)
        pi_hat = pi_sum / n
        kappa = min(1.0, pi_hat / gamma) if gamma > 0 else 1.0

        return (1 - kappa) * sample_cov + kappa * prior
