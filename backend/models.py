from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ticker_catalog import AssetType

EngineType = Literal["stat", "ml"]
EngineUsed = Literal["stat", "ml", "stat_fallback"]

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"}


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
    signal: Literal[
        "Strongly Bullish", "Bullish Outlook", "Neutral", "Bearish Outlook", "Strongly Bearish"
    ]


class PredictionEvaluation(ApiModel):
    """Backtest of the forecast that is returned, on its own validation windows."""

    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    directional_accuracy: float | None = None
    validation_windows: int | None = None
    # MAPE of holding the last close flat over the same windows.
    no_change_mape: float | None = None
    beats_no_change: bool | None = None


class ExplanationFeature(ApiModel):
    feature: str
    difference_score: float = Field(ge=0.0)
    value: float
    relation: Literal["higher", "lower", "similar"]


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
    engine: EngineType = Field(
        "ml",
        description="Defaults to 'stat' for crypto, where the ML model showed no edge in backtests.",
    )
    asset_type: AssetType = "stock"
    display_currency: str = "USD"

    @model_validator(mode="before")
    @classmethod
    def default_engine_for_asset_type(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("engine") is None:
            return {**data, "engine": "stat" if data.get("asset_type") == "crypto" else "ml"}
        return data

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or not normalized.isascii() or " " in normalized:
            raise ValueError("Invalid ticker symbol.")
        return normalized

    @field_validator("display_currency")
    @classmethod
    def validate_display_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"Unsupported currency '{normalized}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_CURRENCIES))}"
            )
        return normalized


class PredictResponse(ApiModel):
    symbol: str
    requested_symbol: str
    asset_type: AssetType
    currency: str
    native_currency: str
    display_currency: str
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
