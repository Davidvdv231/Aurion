from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.ticker_catalog import AssetType

EngineType = Literal["stat", "ai"]
EngineUsed = Literal["stat", "ai", "stat_fallback"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoryPoint(ApiModel):
    date: str
    close: float


class ForecastPoint(ApiModel):
    date: str
    predicted: float
    lower: float
    upper: float


class PredictStats(ApiModel):
    daily_trend_pct: float
    last_close: float


class PredictionSource(ApiModel):
    market_data: str
    forecast: str


class PredictRequest(ApiModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    horizon: int = Field(30, ge=7, le=45)
    engine: EngineType = "stat"
    asset_type: AssetType = "stock"

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or not normalized.isascii() or " " in normalized:
            raise ValueError("Ticker symbool is ongeldig.")
        return normalized


class PredictResponse(ApiModel):
    symbol: str
    requested_symbol: str
    asset_type: AssetType
    currency: str
    generated_at: str
    horizon_days: int
    engine_requested: EngineType
    engine_used: EngineUsed
    model_name: str
    engine_note: str
    source: PredictionSource
    degraded: bool = False
    degradation_reason: str | None = None
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]
    stats: PredictStats
    disclaimer: str


class HealthResponse(ApiModel):
    status: str
    timestamp: str


class TickerItem(ApiModel):
    symbol: str
    name: str
    exchange: str
    region: str
    popularity: int
    asset_type: AssetType
    score: int | None = None
    source: str | None = None


class TickerSearchResponse(ApiModel):
    query: str
    asset_type: AssetType
    tickers: list[TickerItem]


class TopAssetsResponse(ApiModel):
    generated_at: str
    asset_type: AssetType
    source: str
    items: list[TickerItem]
