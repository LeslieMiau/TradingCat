"""Map instrument symbols to coarse-grained sectors and sector benchmarks."""

from __future__ import annotations

from tradingcat.domain.models import Instrument


# Default symbol → sector mapping for sample_instruments() and common ETFs/stocks.
DEFAULT_SYMBOL_TO_SECTOR: dict[str, str] = {
    # US broad market
    "SPY": "broad_market",
    "VTI": "broad_market",
    # US technology
    "QQQ": "technology",
    "XLK": "technology",
    # US financials
    "XLF": "financial",
    # US energy
    "XLE": "energy",
    # US healthcare
    "XLV": "healthcare",
    # US consumer
    "XLP": "consumer",
    # HK technology
    "0700": "technology",
    "9988": "technology",
    # CN broad market
    "510300": "broad_market",
    # CN growth enterprise
    "159915": "growth_enterprise",
    # CN technology
    "300308": "technology",
    "603986": "technology",
}

# Per-sector benchmark ETFs used as representative return series.
DEFAULT_SECTOR_BENCHMARKS: dict[str, str] = {
    "technology": "QQQ",
    "financial": "XLF",
    "energy": "XLE",
    "healthcare": "XLV",
    "consumer": "XLP",
    "broad_market": "SPY",
    "growth_enterprise": "159915",
}


class SectorMap:
    """Maps instrument symbols to coarse-grained sectors.

    Usage::

        sm = SectorMap()
        sm.get_sector("0700")         # → "technology"
        sm.get_sector_benchmark("technology")  # → "QQQ"
        sm.get_symbols_in_sector("technology", watchlist)
    """

    def __init__(
        self,
        symbol_to_sector: dict[str, str] | None = None,
        sector_benchmarks: dict[str, str] | None = None,
    ) -> None:
        self._symbol_to_sector = dict(symbol_to_sector or DEFAULT_SYMBOL_TO_SECTOR)
        self._sector_benchmarks = dict(sector_benchmarks or DEFAULT_SECTOR_BENCHMARKS)

    def get_sector(self, symbol: str) -> str | None:
        """Return the coarse-grained sector for *symbol*, or ``None``."""
        return self._symbol_to_sector.get(symbol)

    def get_sector_benchmark(self, sector: str) -> str | None:
        """Return the benchmark symbol for *sector*, or ``None``."""
        return self._sector_benchmarks.get(sector)

    def get_symbols_in_sector(
        self,
        sector: str,
        watchlist: list[Instrument],
    ) -> list[Instrument]:
        """Return instruments in *watchlist* that belong to *sector*."""
        return [inst for inst in watchlist if self._symbol_to_sector.get(inst.symbol) == sector]

    def group_by_sector(
        self,
        watchlist: list[Instrument],
    ) -> dict[str, list[Instrument]]:
        """Group *watchlist* instruments by their sector.

        Returns ``{sector_name: [Instrument, ...]}``. Instruments without a
        known sector are omitted.
        """
        groups: dict[str, list[Instrument]] = {}
        for inst in watchlist:
            sector = self._symbol_to_sector.get(inst.symbol)
            if sector is not None:
                groups.setdefault(sector, []).append(inst)
        return groups
