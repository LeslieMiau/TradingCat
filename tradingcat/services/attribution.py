from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np


@dataclass
class BrinsonAttribution:
    allocation_effect: float  # from sector/country allocation decisions
    selection_effect: float  # from stock selection within sectors
    interaction_effect: float
    total_excess_return: float

    def to_dict(self) -> dict:
        return {
            "allocation_effect": round(self.allocation_effect, 6),
            "selection_effect": round(self.selection_effect, 6),
            "interaction_effect": round(self.interaction_effect, 6),
            "total_excess_return": round(self.total_excess_return, 6),
        }


@dataclass
class FactorAttribution:
    factor_exposures: dict[str, float]  # factor name -> exposure
    factor_returns: dict[str, float]  # factor name -> period return
    factor_contribution: dict[str, float]  # factor name -> contribution to return
    specific_return: float  # return not explained by factors
    total_return: float
    r_squared: float  # how much variance is explained by factors

    def to_dict(self) -> dict:
        return {
            "factor_exposures": {k: round(v, 4) for k, v in self.factor_exposures.items()},
            "factor_returns": {k: round(v, 6) for k, v in self.factor_returns.items()},
            "factor_contribution": {k: round(v, 6) for k, v in self.factor_contribution.items()},
            "specific_return": round(self.specific_return, 6),
            "total_return": round(self.total_return, 6),
            "r_squared": round(self.r_squared, 4),
        }


class PerformanceAttribution:
    """Decompose portfolio returns into sources."""

    @staticmethod
    def brinson_attribution(
        portfolio_weights: dict[str, float],
        benchmark_weights: dict[str, float],
        portfolio_returns: dict[str, float],
        benchmark_returns: dict[str, float],
        sector_map: dict[str, str],
    ) -> BrinsonAttribution:
        """Brinson-style return decomposition by sector."""
        sectors = set(sector_map.values())
        alloc_eff = 0.0
        select_eff = 0.0
        interact_eff = 0.0

        for sector in sectors:
            pw_sector = sum(portfolio_weights.get(s, 0.0) for s in portfolio_weights if sector_map.get(s) == sector)
            bw_sector = sum(benchmark_weights.get(s, 0.0) for s in benchmark_weights if sector_map.get(s) == sector)
            pr_sector = np.mean([portfolio_returns.get(s, 0.0) for s in portfolio_weights if sector_map.get(s) == sector]) if any(sector_map.get(s) == sector for s in portfolio_weights) else 0.0
            br_sector = np.mean([benchmark_returns.get(s, 0.0) for s in benchmark_weights if sector_map.get(s) == sector]) if any(sector_map.get(s) == sector for s in benchmark_weights) else 0.0

            alloc_eff += (pw_sector - bw_sector) * br_sector
            select_eff += bw_sector * (pr_sector - br_sector)
            interact_eff += (pw_sector - bw_sector) * (pr_sector - br_sector)

        total_excess = sum(portfolio_weights.get(s, 0.0) * portfolio_returns.get(s, 0.0) for s in set(list(portfolio_weights.keys()) + list(benchmark_weights.keys()))) - \
                       sum(benchmark_weights.get(s, 0.0) * benchmark_returns.get(s, 0.0) for s in set(list(portfolio_weights.keys()) + list(benchmark_weights.keys())))

        return BrinsonAttribution(
            allocation_effect=alloc_eff,
            selection_effect=select_eff,
            interaction_effect=interact_eff,
            total_excess_return=total_excess,
        )

    @staticmethod
    def factor_attribution(
        portfolio_exposures: dict[str, float],  # factor -> exposure
        factor_returns_data: dict[str, float],  # factor -> period return
        portfolio_return: float,
    ) -> FactorAttribution:
        """Simple factor attribution: contribution = exposure * factor_return."""
        factor_contribution = {}
        explained = 0.0
        for factor in portfolio_exposures:
            exp = portfolio_exposures[factor]
            ret = factor_returns_data.get(factor, 0.0)
            contrib = exp * ret
            factor_contribution[factor] = contrib
            explained += contrib

        specific_return = portfolio_return - explained
        r2 = explained / portfolio_return if abs(portfolio_return) > 1e-10 else 0.0

        return FactorAttribution(
            factor_exposures=portfolio_exposures,
            factor_returns=factor_returns_data,
            factor_contribution=factor_contribution,
            specific_return=specific_return,
            total_return=portfolio_return,
            r_squared=min(abs(r2), 1.0),
        )

    def daily_report(self, portfolio_weights: dict, benchmark_weights: dict,
                     portfolio_returns: dict, benchmark_returns: dict,
                     sector_map: dict, factor_exposures: dict,
                     factor_returns_data: dict, portfolio_return: float) -> dict:
        brinson = self.brinson_attribution(
            portfolio_weights, benchmark_weights,
            portfolio_returns, benchmark_returns, sector_map,
        )
        factor = self.factor_attribution(
            factor_exposures, factor_returns_data, portfolio_return,
        )
        return {
            "brinson": brinson.to_dict(),
            "factor": factor.to_dict(),
            "date": str(date.today()),
        }

    def save_report(self, report: dict, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
