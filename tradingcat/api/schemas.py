from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class DecisionPayload(BaseModel):
    reason: str | None = None


class ChecklistItemPayload(BaseModel):
    status: str
    notes: str | None = None


class RiskStatePayload(BaseModel):
    drawdown: float
    daily_pnl: float
    weekly_pnl: float


class MarketDataSmokePayload(BaseModel):
    symbols: list[str] | None = None
    include_bars: bool = True
    include_option_chain: bool = False


class InstrumentPayload(BaseModel):
    symbol: str
    market: Literal["US", "HK", "CN"]
    asset_class: Literal["stock", "etf", "option", "crypto", "bond", "cash"] = "stock"
    currency: str = "USD"
    name: str = ""
    lot_size: float = 1.0
    enabled: bool = True
    tradable: bool = True
    liquidity_bucket: str = "medium"
    avg_daily_dollar_volume_m: float | None = None
    tags: list[str] = Field(default_factory=list)


class InstrumentCatalogPayload(BaseModel):
    instruments: list[InstrumentPayload]


class HistorySyncPayload(BaseModel):
    symbols: list[str] | None = None
    start: date | None = None
    end: date | None = None
    include_corporate_actions: bool = True


class HistoryRepairPayload(HistorySyncPayload):
    pass


class FxSyncPayload(BaseModel):
    base_currency: str = "CNY"
    quote_currencies: list[str] | None = None
    start: date | None = None
    end: date | None = None


class ResearchNewsItemPayload(BaseModel):
    title: str
    body: str | None = None
    symbols: list[str] = Field(default_factory=list)


class ResearchNewsSummaryPayload(BaseModel):
    items: list[ResearchNewsItemPayload]


class ManualFillImportPayload(BaseModel):
    csv_text: str
    delimiter: str = ","


class ExecutionPreviewPayload(BaseModel):
    as_of: date | None = None


class ManualOrderPayload(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    market: Literal["US", "HK", "CN"]
    quantity: float
    emotional_tag: str | None = None
    algo_strategy: Literal["TWAP", "VWAP", "LADDER", "NONE"] | None = None
    algo_levels: int | None = None
    algo_price_start: float | None = None
    algo_price_end: float | None = None


class RiskUpdatePayload(BaseModel):
    daily_stop_loss: float | None = None
    max_single_stock_weight: float | None = None
    max_single_etf_weight: float | None = None
    half_risk_drawdown: float | None = None
    no_new_risk_drawdown: float | None = None


class ExecutionRunPayload(BaseModel):
    as_of: date | None = None
    enforce_gate: bool = False


class RebalancePlanPayload(BaseModel):
    as_of: date | None = None


class RolloutPolicyPayload(BaseModel):
    stage: str
    reason: str | None = None


class AssetCorrelationPayload(BaseModel):
    symbols: list[str]
    days: int = 90
