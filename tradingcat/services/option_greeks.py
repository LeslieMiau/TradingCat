from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

import numpy as np
from scipy.stats import norm


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


@dataclass
class Greeks:
    delta: float
    gamma: float
    theta: float  # daily theta
    vega: float  # per 1% vol change
    rho: float  # per 1% rate change
    iv: float
    price: float
    intrinsic_value: float
    time_value: float


@dataclass
class PortfolioGreeks:
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta: float = 0.0
    total_vega: float = 0.0
    total_rho: float = 0.0
    net_exposure: float = 0.0  # delta * underlying_price * quantity
    positions: list[dict] = field(default_factory=list)


class OptionGreeks:
    """Black-Scholes Greeks calculator."""

    @staticmethod
    def _d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T)) if T > 0 and sigma > 0 else 0.0

    @staticmethod
    def _d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
        d1 = OptionGreeks._d1(S, K, T, r, sigma)
        return d1 - sigma * math.sqrt(T) if T > 0 and sigma > 0 else 0.0

    @classmethod
    def price(cls, S: float, K: float, T: float, r: float, sigma: float,
              option_type: OptionType) -> float:
        if T <= 0:
            intrinsic = max(S - K, 0.0) if option_type == OptionType.CALL else max(K - S, 0.0)
            return intrinsic
        d1 = cls._d1(S, K, T, r, sigma)
        d2 = cls._d2(S, K, T, r, sigma)
        if option_type == OptionType.CALL:
            return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    @classmethod
    def compute_greeks(cls, S: float, K: float, T: float, r: float,
                       sigma: float, option_type: OptionType) -> Greeks:
        if T <= 0 or sigma <= 0:
            intrinsic = max(S - K, 0.0) if option_type == OptionType.CALL else max(K - S, 0.0)
            return Greeks(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0,
                          iv=sigma, price=intrinsic, intrinsic_value=intrinsic, time_value=0.0)

        d1 = cls._d1(S, K, T, r, sigma)
        d2 = cls._d2(S, K, T, r, sigma)
        nd1 = norm.pdf(d1)

        # Price
        if option_type == OptionType.CALL:
            p = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            p = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        intrinsic = max(S - K, 0.0) if option_type == OptionType.CALL else max(K - S, 0.0)
        time_value = max(p - intrinsic, 0.0)

        # Greeks
        if option_type == OptionType.CALL:
            delta = norm.cdf(d1)
            theta = (-S * nd1 * sigma / (2 * math.sqrt(T))
                     - r * K * math.exp(-r * T) * norm.cdf(d2)) / 365.0
            rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0
        else:
            delta = -norm.cdf(-d1)
            theta = (-S * nd1 * sigma / (2 * math.sqrt(T))
                     + r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365.0
            rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0

        gamma = nd1 / (S * sigma * math.sqrt(T)) if S > 0 and sigma > 0 and T > 0 else 0.0
        vega = S * nd1 * math.sqrt(T) / 100.0  # per 1% vol change

        return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega,
                      rho=rho, iv=sigma, price=p, intrinsic_value=intrinsic,
                      time_value=time_value)

    @staticmethod
    def implied_volatility(market_price: float, S: float, K: float, T: float,
                           r: float, option_type: OptionType,
                           guess: float = 0.20, tol: float = 1e-6,
                           max_iter: int = 100) -> float:
        """Newton's method to back out implied volatility from market price."""
        sigma = guess
        for _ in range(max_iter):
            greeks = OptionGreeks.compute_greeks(S, K, T, r, sigma, option_type)
            diff = greeks.price - market_price
            if abs(diff) < tol:
                return sigma
            vega = OptionGreeks._vega_raw(S, K, T, r, sigma)
            if abs(vega) < 1e-12:
                break
            sigma -= diff / vega
            sigma = max(sigma, 0.01)
        return sigma

    @staticmethod
    def _vega_raw(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = OptionGreeks._d1(S, K, T, r, sigma)
        return S * norm.pdf(d1) * math.sqrt(T)

    @classmethod
    def portfolio_greeks(cls, positions: list[dict]) -> PortfolioGreeks:
        """positions: list of {symbol, quantity, S, K, T, r, sigma, option_type}"""
        result = PortfolioGreeks()
        for pos in positions:
            g = cls.compute_greeks(
                S=pos["S"], K=pos["K"], T=pos["T"], r=pos["r"],
                sigma=pos["sigma"], option_type=OptionType(pos["option_type"]),
            )
            q = pos["quantity"]
            result.total_delta += g.delta * q
            result.total_gamma += g.gamma * q
            result.total_theta += g.theta * q
            result.total_vega += g.vega * q
            result.total_rho += g.rho * q
            result.net_exposure += g.delta * pos["S"] * q
            result.positions.append({
                "symbol": pos["symbol"],
                "quantity": q,
                "delta": g.delta,
                "gamma": g.gamma,
                "theta": g.theta,
                "vega": g.vega,
                "price": g.price,
            })
        return result

    @staticmethod
    def days_to_expiry(expiry: date, as_of: date | None = None) -> float:
        as_of = as_of or date.today()
        return max((expiry - as_of).days / 365.0, 0.0)
