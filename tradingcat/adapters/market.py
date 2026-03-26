from __future__ import annotations

from datetime import date, datetime, timedelta

from tradingcat.domain.models import AssetClass, Bar, Instrument, Market, OptionContract


class StaticMarketDataAdapter:
    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        total_days = (end - start).days
        if total_days > 370:
            return self._fetch_monthly_bars(instrument, start, end)
        current = start
        price = 100.0
        bars: list[Bar] = []
        while current <= end:
            price *= 1.001
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=datetime.combine(current, datetime.min.time()),
                    open=price * 0.99,
                    high=price * 1.01,
                    low=price * 0.98,
                    close=price,
                    volume=1_000_000,
                )
            )
            current += timedelta(days=1)
        return bars

    def _fetch_monthly_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        current = date(start.year, start.month, 1)
        price = 100.0
        bars: list[Bar] = []
        while current <= end:
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
            sample_date = min(end, next_month - timedelta(days=1))
            if sample_date < start:
                current = next_month
                continue
            while sample_date.weekday() >= 5 and sample_date > current:
                sample_date -= timedelta(days=1)
            price *= 1.01
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=datetime.combine(sample_date, datetime.min.time()),
                    open=price * 0.99,
                    high=price * 1.01,
                    low=price * 0.98,
                    close=price,
                    volume=1_000_000,
                )
            )
            current = next_month
        return bars

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]:
        return {instrument.symbol: 100.0 for instrument in instruments}

    def fetch_option_chain(self, underlying: str, as_of: date) -> list[OptionContract]:
        return [
            OptionContract(
                symbol=f"{underlying}-P-100",
                underlying=underlying,
                strike=100.0,
                expiry=as_of + timedelta(days=30),
                option_type="put",
            ),
            OptionContract(
                symbol=f"{underlying}-C-105",
                underlying=underlying,
                strike=105.0,
                expiry=as_of + timedelta(days=30),
                option_type="call",
            ),
        ]

    def fetch_corporate_actions(self, instrument: Instrument, start: date, end: date) -> list[dict]:
        return []


def sample_instruments() -> list[Instrument]:
    return [
        Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD", name="SPDR S&P 500 ETF"),
        Instrument(symbol="QQQ", market=Market.US, asset_class=AssetClass.ETF, currency="USD", name="Invesco QQQ Trust"),
        Instrument(symbol="0700", market=Market.HK, asset_class=AssetClass.STOCK, currency="HKD", name="Tencent"),
        Instrument(symbol="510300", market=Market.CN, asset_class=AssetClass.ETF, currency="CNY", name="CSI 300 ETF"),
        Instrument(symbol="TLT", market=Market.US, asset_class=AssetClass.ETF, currency="USD", name="iShares 20+ Year Treasury Bond ETF"),
        Instrument(symbol="IEF", market=Market.US, asset_class=AssetClass.ETF, currency="USD", name="iShares 7-10 Year Treasury Bond ETF"),
        Instrument(symbol="GLD", market=Market.US, asset_class=AssetClass.ETF, currency="USD", name="SPDR Gold Shares"),
        Instrument(symbol="GSG", market=Market.US, asset_class=AssetClass.ETF, currency="USD", name="iShares S&P GSCI Commodity-Indexed Trust"),
    ]
