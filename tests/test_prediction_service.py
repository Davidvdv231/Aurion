from __future__ import annotations

import asyncio
import logging

import pandas as pd

from backend.config import Settings
from backend.errors import ServiceError
from backend.ml.model import BacktestMetrics, ForecastResult
from backend.models import PredictRequest
from backend.services.cache import CacheBackend
from backend.services.market_data import MarketSeries
from backend.services.prediction import build_prediction_response


def _settings() -> Settings:
    return Settings(
        app_title="Aurion test",
        version="test",
        cors_allow_origins=(),
        top_cache_ttl_seconds=300,
        history_cache_ttl_seconds=300,
        rate_limit_window_seconds=60,
        rate_limit_max_requests_stat=30,
        rate_limit_max_requests_ai=8,
        openai_chat_completions_url="https://api.openai.com/v1/chat/completions",
        openai_model="gpt-4o-mini",
        openai_api_key="",
        stock_llm_api_url="",
        stock_llm_api_key="",
        redis_url="",
        redis_prefix="test",
        redis_socket_timeout_seconds=1.0,
        trusted_proxy_ips=(),
    )


def _close_series() -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=120)
    values = pd.Series(range(100, 220), index=index, dtype=float)
    return values


def _market_series(symbol: str = "AAPL", currency: str = "USD") -> MarketSeries:
    return MarketSeries(
        close=_close_series(),
        resolved_symbol=symbol,
        currency=currency,
        source="yfinance",
    )


def _run_prediction(payload: PredictRequest):
    settings = _settings()
    cache_backend = CacheBackend(settings)
    return asyncio.run(
        build_prediction_response(
            payload,
            settings=settings,
            cache_backend=cache_backend,
        )
    )


def test_prediction_service_uses_stat_engine_and_logs_completion(monkeypatch, caplog) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())

    with caplog.at_level(logging.INFO, logger="stock_predictor.prediction"):
        response = _run_prediction(
            PredictRequest(symbol="AAPL", horizon=30, engine="stat", asset_type="stock")
        )

    assert response.engine_used == "stat"
    assert response.source.forecast == "stat"
    assert response.degraded is False
    assert any(
        getattr(record, "prediction_event", None) == "prediction.started"
        and getattr(record, "prediction_engine_requested", None) == "stat"
        for record in caplog.records
    )
    assert any(
        getattr(record, "prediction_event", None) == "prediction.completed"
        and getattr(record, "prediction_engine_used", None) == "stat"
        and getattr(record, "prediction_forecast_source", None) == "stat"
        for record in caplog.records
    )


def test_prediction_service_uses_ml_engine_when_quality_gate_passes(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())

    def fake_train_and_predict(**_):
        return (
            ForecastResult(
                dates=["2025-06-02", "2025-06-03"],
                predicted=[210.0, 212.0],
                lower=[205.0, 207.0],
                upper=[215.0, 217.0],
                neighbors_used=12,
            ),
            BacktestMetrics(
                mae=2.4,
                rmse=3.1,
                mape=1.8,
                directional_accuracy=0.71,
                validation_windows=3,
            ),
        )

    monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

    response = _run_prediction(
        PredictRequest(symbol="AAPL", horizon=30, engine="ml", asset_type="stock")
    )

    assert response.engine_requested == "ml"
    assert response.engine_used == "ml"
    assert response.source.forecast == "ml_analog"
    assert response.degraded is False
    assert response.evaluation is not None
    assert response.evaluation.directional_accuracy == 0.71


def test_prediction_service_falls_back_to_stat_when_ml_quality_is_insufficient(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())

    def fake_train_and_predict(**_):
        return (
            ForecastResult(
                dates=["2025-06-02", "2025-06-03"],
                predicted=[210.0, 211.0],
                lower=[205.0, 206.0],
                upper=[215.0, 216.0],
                neighbors_used=12,
            ),
            BacktestMetrics(
                mae=4.2,
                rmse=5.1,
                mape=2.8,
                directional_accuracy=0.45,
                validation_windows=3,
            ),
        )

    monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

    response = _run_prediction(
        PredictRequest(symbol="AAPL", horizon=30, engine="ml", asset_type="stock")
    )

    assert response.engine_used == "stat_fallback"
    assert response.degraded is True
    assert response.degradation_code == "model_quality_insufficient"
    assert response.source.forecast == "stat_fallback"
    assert response.evaluation is not None
    assert response.evaluation.validation_windows == 3


def test_prediction_service_falls_back_to_stat_when_ml_runtime_fails(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())
    monkeypatch.setattr(
        "backend.ml.service.train_and_predict",
        lambda **_: (_ for _ in ()).throw(RuntimeError("model offline")),
    )

    response = _run_prediction(
        PredictRequest(symbol="AAPL", horizon=30, engine="ml", asset_type="stock")
    )

    assert response.engine_used == "stat_fallback"
    assert response.degraded is True
    assert response.degradation_code == "ml_engine_unavailable"
    assert response.degradation_message is not None
    assert "model offline" in response.degradation_message
    assert response.source.forecast == "stat_fallback"


def test_prediction_service_falls_back_to_stat_when_ai_provider_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: _market_series(symbol="BTC-USD"),
    )

    def raise_ai_failure(*_, **__):
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message="OpenAI niet bereikbaar.",
            provider="openai",
            retryable=True,
        )

    monkeypatch.setattr("backend.services.prediction.build_ai_forecast", raise_ai_failure)

    response = _run_prediction(
        PredictRequest(symbol="BTC", horizon=30, engine="ai", asset_type="crypto")
    )

    assert response.engine_requested == "ai"
    assert response.engine_used == "stat_fallback"
    assert response.degraded is True
    assert response.degradation_code == "ai_provider_unavailable"
    assert response.degradation_message == "AI unavailable (OpenAI niet bereikbaar.). Fell back to statistical forecast."
    assert response.source.forecast == "stat_fallback"
