#!/usr/bin/env python3
"""Bootstrap market data for the 3 default execution strategies.

Syncs historical bars, corporate actions, and FX rates from 2018-01-01
to today using whatever market data adapter is available (YFinance by
default when OpenD is not running).

Usage:
    .venv/bin/python scripts/bootstrap_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import date

# Ensure the project root is on sys.path when invoked as a script.
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradingcat.app import TradingCatApplication  # noqa: E402


def main() -> int:
    print("Initializing application …")
    app = TradingCatApplication()

    strategy_symbols = ["SPY", "QQQ", "0700", "510300"]
    start = date(2018, 1, 1)
    end = date.today()

    print(f"Syncing history for {strategy_symbols} from {start} to {end} …")
    sync = app.sync_market_history(
        symbols=strategy_symbols,
        start=start,
        end=end,
        include_corporate_actions=True,
    )
    print(f"  bars synced for {sync['instrument_count']} instruments, failures={sync['failure_count']}")
    if sync["failure_count"]:
        for f in sync["failures"]:
            print(f"  FAIL: {f['symbol']} — {f['error']}")

    coverage = sync.get("coverage", {})
    if coverage:
        print(f"  minimum coverage ratio: {coverage.get('minimum_coverage_ratio', '?')}")

    fx = sync.get("fx_sync", {})
    if fx:
        print(f"  FX rates: {fx.get('rate_count', 0)} rates for {fx.get('quote_currencies', [])}")

    # Clear cached summaries so readiness picks up the new data.
    app.reset_state()

    print("\nChecking research readiness …")
    readiness = app.research_readiness_summary()
    strategies = readiness.get("strategies", [])
    all_ready = True
    for s in strategies:
        status = "READY" if s.get("data_ready") else "BLOCKED"
        reasons = s.get("blocking_reasons", [])
        print(f"  {s.get('strategy_id', '?'):40s} {status}")
        for r in reasons:
            print(f"    - {r}")
        if not s.get("data_ready"):
            all_ready = False

    print()
    if all_ready:
        print("All execution strategies are data-ready.")
        return 0
    else:
        print("Some strategies are still blocked. Review the output above.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
