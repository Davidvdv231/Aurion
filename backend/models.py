from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.ticker_catalog import AssetType

EngineType = Literal["stat", "ml", "ai"]
EngineUsed = Literal["stat", "ml", "ai", "stat_fallback", "ml_fallback"]


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


class PredictionSummary(ApiModel):
    expected_price: float
    expected_return_pct: float
    trend: Literal["bullish", "bearish", "neutral"]
    confidence_tier: Literal["low", "medium", "high"]
    probability_up: float = Field(ge=0.0, le=1.0)
    signal: Literal["bullish", "mildly_bullish", "neutral", "mildly_bearish", "bearish"]


class PredictionEvaluation(ApiModel):
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    directional_accuracy: float | None = None
    validation_windows: int | None = None


class ExplanationFeature(ApiModel):
    feature: str
    contribution: float
    value: float
    direction: Literal["bullish", "bearish", "neutral"]


class PredictionExplanation(ApiModel):
    top_features: list[ExplanationFeature]
    neighbors_used: int
    avg_neighbor_distance: float
    nearest_analog_date: str
    narrative: str


class PredictionSource(ApiModel):
    market_data: str
    forecast: str
    analysis: str | None = None
    data_quality: Literal["clean", "patched", "degraded"] = "clean"
    data_warnings: list[str] = Field(default_factory=list)
    stale: bool = False


class PredictRequest(ApiModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    horizon: int = Field(30, ge=7, le=45)
    engine: EngineType = "ml"
    asset_type: AssetType = "stock"

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or not normalized.isascii() or " " in normalized:
            raise ValueError("Invalid ticker symbol.")
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
    degradation_code: str | None = None
    degradation_message: str | None = None
    # Deprecated compatibility alias. Mirrors degradation_message for older clients.
    degradation_reason: str | None = None
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]
    stats: PredictStats
    summary: PredictionSummary
    evaluation: PredictionEvaluation | None = None
    explanation: PredictionExplanation | None = None
    disclaimer: str


class HealthResponse(ApiModel):
    status: str
    timestamp: str
    redis: str = "not_configured"
    cache_size: int = 0
    uptime_seconds: int = 0


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
