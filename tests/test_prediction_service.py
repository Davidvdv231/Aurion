from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace

import pandas as pd

from backend.config import Settings
from backend.errors import ServiceError
from backend.ml.model import BacktestMetrics, FeatureDifference, ForecastResult
from backend.models import PredictRequest
from backend.runtime import BlockingTaskRunner
from backend.services.cache import CacheBackend
from backend.services.market_data import MarketSeries
from backend.services.prediction import build_prediction_response


def _settings() -> Settings:
    return Settings(
        app_env="development",
        app_title="Aurion test",
        version="test",
        cors_allow_origins=(),
        top_cache_ttl_seconds=300,
        history_cache_ttl_seconds=300,
        blocking_task_timeout_seconds=15.0,
        top_assets_timeout_seconds=8.0,
        executor_max_workers=4,
        memory_cache_max_items=64,
        memory_cache_sweep_batch_size=4,
        rate_limit_window_seconds=60,
        rate_limit_max_requests_stat=30,
        rate_limit_max_requests_ai=8,
        rate_limit_max_requests_search=60,
        rate_limit_fail_open=True,
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
    index = pd.bdate_range("2025-01-02", periods=180)
    values = pd.Series(range(100, 280), index=index, dtype=float)
    return values


def _market_series(symbol: str = "AAPL", currency: str = "USD") -> MarketSeries:
    return MarketSeries(
        close=_close_series(),
        resolved_symbol=symbol,
        currency=currency,
        source="yfinance",
    )


def _forecast_result(
    *,
    neighbors_used: int = 12,
    feature: str = "momentum_10",
    difference_score: float = 0.62,
    value: float = 0.041,
    relation: str = "higher",
) -> ForecastResult:
    dates = [dt.date().isoformat() for dt in pd.bdate_range("2025-06-02", periods=30)]
    predicted = [210.0 + idx for idx in range(30)]
    return ForecastResult(
        dates=dates,
        predicted=predicted,
        lower=[value - 5 for value in predicted],
        upper=[value + 5 for value in predicted],
        neighbors_used=neighbors_used,
        top_features=[
            FeatureDifference(
                feature=feature,
                difference_score=difference_score,
                value=value,
                relation=relation,
            )
        ],
        avg_neighbor_distance=0.13,
        nearest_analog_date="2024-11-08",
    )


def _run_prediction(payload: PredictRequest, *, settings: Settings | None = None):
    settings = settings or _settings()
    cache_backend = CacheBackend(settings)
    blocking_runner = BlockingTaskRunner(
        max_workers=settings.executor_max_workers,
        max_in_flight_calls=settings.executor_max_workers,
        thread_name_prefix="aurion-test",
    )
    try:
        return asyncio.run(
            build_prediction_response(
                payload,
                settings=settings,
                cache_backend=cache_backend,
                blocking_runner=blocking_runner,
            )
        )
    finally:
        blocking_runner.shutdown(wait=True, cancel_futures=True)


def test_prediction_service_uses_stat_engine_and_logs_completion(monkeypatch, caplog) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())

    with caplog.at_level(logging.INFO, logger="stock_predictor.prediction"):
        response = _run_prediction(
            PredictRequest(symbol="AAPL", horizon=30, engine="stat", asset_type="stock")
        )

    assert response.engine_used == "stat"
    assert response.source.forecast == "stat"
    assert response.degraded is False
    assert response.summary.confidence_tier in {"low", "medium", "high"}
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
    monkeypatch.setattr(
        "backend.services.prediction.backtest_stat_forecast",
        lambda *_, **__: {"mape": 3.5, "directional_accuracy": 0.52, "validation_windows": 5},
    )

    def fake_train_and_predict(**_):
        return (
            _forecast_result(),
            BacktestMetrics(
                mae=2.4,
                rmse=3.1,
                mape=1.8,
                directional_accuracy=0.71,
                validation_windows=5,
            ),
        )

    monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

    response = _run_prediction(
        PredictRequest(symbol="AAPL", horizon=30, engine="ml", asset_type="stock")
    )

    assert response.engine_requested == "ml"
    assert response.engine_used == "ml"
    assert response.source.forecast == "ml_analog"
    assert response.source.analysis == "ml_pattern_difference"
    assert response.degraded is False
    assert response.evaluation is not None
    assert response.evaluation.directional_accuracy == 0.71
    assert response.explanation is not None
    assert response.explanation.nearest_analog_date == "2024-11-08"
    assert response.explanation.top_features[0].difference_score == 0.62
    assert response.explanation.top_features[0].relation == "higher"


def test_prediction_service_falls_back_when_validation_windows_are_insufficient(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())
    monkeypatch.setattr(
        "backend.services.prediction.backtest_stat_forecast",
        lambda *_, **__: {"mape": 6.0, "directional_accuracy": 0.51, "validation_windows": 5},
    )

    def fake_train_and_predict(**_):
        return (
            _forecast_result(feature="rsi_14", difference_score=0.8, value=68.0),
            BacktestMetrics(
                mae=4.2,
                rmse=5.1,
                mape=2.8,
                directional_accuracy=0.74,
                validation_windows=3,
            ),
        )

    monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

    response = _run_prediction(
        PredictRequest(symbol="AAPL", horizon=30, engine="ml", asset_type="stock")
    )

    assert response.engine_used == "stat_fallback"
    assert response.degraded is True
    assert response.degradation_code == "model_validation_insufficient"
    assert response.source.forecast == "stat_fallback"
    assert response.source.analysis == "ml_pattern_difference"
    assert response.evaluation is not None
    assert response.evaluation.validation_windows == 3
    assert response.explanation is not None
    assert response.explanation.nearest_analog_date == "2024-11-08"
    assert "historical patterns" in response.explanation.narrative


def test_prediction_service_falls_back_when_ml_underperforms_stat_baseline(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())
    monkeypatch.setattr(
        "backend.services.prediction.backtest_stat_forecast",
        lambda *_, **__: {"mape": 1.5, "directional_accuracy": 0.58, "validation_windows": 5},
    )

    def fake_train_and_predict(**_):
        return (
            _forecast_result(feature="rsi_14", difference_score=0.7, value=68.0, relation="lower"),
            BacktestMetrics(
                mae=4.2,
                rmse=5.1,
                mape=2.8,
                directional_accuracy=0.65,
                validation_windows=5,
            ),
        )

    monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

    response = _run_prediction(
        PredictRequest(symbol="AAPL", horizon=30, engine="ml", asset_type="stock")
    )

    assert response.engine_used == "stat_fallback"
    assert response.degraded is True
    assert response.degradation_code == "model_baseline_underperforming"


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
    assert response.source.analysis is None
    assert response.explanation is None


def test_prediction_service_falls_back_when_ml_task_times_out(monkeypatch) -> None:
    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", lambda **_: _market_series())
    monkeypatch.setattr(
        "backend.services.prediction.backtest_stat_forecast",
        lambda *_, **__: {"mape": 3.5, "directional_accuracy": 0.52, "validation_windows": 5},
    )

    def slow_train_and_predict(**_):
        time.sleep(0.05)
        return (
            _forecast_result(),
            BacktestMetrics(
                mae=2.4,
                rmse=3.1,
                mape=1.8,
                directional_accuracy=0.71,
                validation_windows=5,
            ),
        )

    monkeypatch.setattr("backend.ml.service.train_and_predict", slow_train_and_predict)

    response = _run_prediction(
        PredictRequest(symbol="AAPL", horizon=30, engine="ml", asset_type="stock"),
        settings=replace(_settings(), blocking_task_timeout_seconds=0.01),
    )

    assert response.engine_used == "stat_fallback"
    assert response.degraded is True
    assert response.degradation_code == "ml_engine_timeout"
    assert response.degradation_message == "ML engine timed out. Fell back to statistical forecast."
    assert response.source.forecast == "stat_fallback"
    assert response.source.analysis is None
    assert response.explanation is None


def test_prediction_service_falls_back_to_stat_when_ai_provider_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: _market_series(symbol="BTC-USD"),
    )

    def raise_ai_failure(*_, **__):
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message="OpenAI service unreachable.",
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
    assert response.degradation_message == "AI unavailable (OpenAI service unreachable.). Fell back to statistical forecast."
    assert response.source.forecast == "stat_fallback"
    assert response.source.analysis is None
    assert response.explanation is None
