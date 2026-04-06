from __future__ import annotations

import asyncio
import time
from dataclasses import replace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import RequestSizeLimitMiddleware, create_app
from backend.errors import ServiceError
from backend.ml.model import BacktestMetrics, FeatureDifference, ForecastResult
from backend.services.market_data import MarketSeries


def _close_series() -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=180)
    values = pd.Series(range(100, 280), index=index, dtype=float)
    return values


def _ml_forecast_result() -> ForecastResult:
    dates = [dt.date().isoformat() for dt in pd.bdate_range("2025-06-02", periods=30)]
    predicted = [210.0 + idx for idx in range(30)]
    return ForecastResult(
        dates=dates,
        predicted=predicted,
        lower=[value - 5 for value in predicted],
        upper=[value + 5 for value in predicted],
        neighbors_used=12,
        top_features=[
            FeatureDifference(
                feature="rsi_14",
                difference_score=0.8,
                value=68.0,
                relation="higher",
            )
        ],
        avg_neighbor_distance=0.17,
        nearest_analog_date="2024-09-18",
    )


def _assert_predict_contract(payload: dict, *, evaluation_expected: bool) -> None:
    assert payload["symbol"]
    assert payload["requested_symbol"]
    assert payload["asset_type"] in {"stock", "crypto"}
    assert payload["currency"]
    assert payload["generated_at"]
    assert isinstance(payload["horizon_days"], int)
    assert payload["engine_requested"] in {"stat", "ml", "ai"}
    assert payload["engine_used"] in {"stat", "ml", "ai", "stat_fallback", "ml_fallback"}
    assert payload["model_name"]
    assert payload["engine_note"]
    assert {"market_data", "forecast", "analysis", "data_quality", "data_warnings", "stale"} <= set(
        payload["source"]
    )
    assert payload["source"]["data_quality"] in {"clean", "patched", "degraded"}
    assert isinstance(payload["source"]["data_warnings"], list)
    assert isinstance(payload["source"]["stale"], bool)
    assert set(payload["stats"]) == {"daily_trend_pct", "last_close"}
    assert set(payload["summary"]) == {
        "expected_price",
        "expected_return_pct",
        "trend",
        "confidence_tier",
        "signal",
    }
    assert payload["summary"]["trend"] in {"bullish", "bearish", "neutral"}
    assert payload["summary"]["confidence_tier"] in {"low", "medium", "high"}
    assert "probability_up" not in payload["summary"]
    assert payload["summary"]["signal"] in {
        "Strongly Bullish",
        "Bullish Outlook",
        "Neutral",
        "Bearish Outlook",
        "Strongly Bearish",
    }
    assert isinstance(payload["history"], list) and payload["history"]
    assert isinstance(payload["forecast"], list) and payload["forecast"]
    assert len(payload["forecast"]) == payload["horizon_days"]
    assert isinstance(payload["disclaimer"], str) and payload["disclaimer"]
    assert {"degradation_code", "degradation_message", "degradation_reason"} <= set(payload)
    if payload["degraded"]:
        assert payload["degradation_message"]
        assert payload["degradation_reason"] == payload["degradation_message"]
        assert payload["degradation_code"]
    else:
        assert payload["degradation_code"] is None
        assert payload["degradation_message"] is None
        assert payload["degradation_reason"] is None

    if evaluation_expected:
        assert payload["evaluation"] is not None
        assert set(payload["evaluation"]) == {
            "mae",
            "rmse",
            "mape",
            "directional_accuracy",
            "validation_windows",
        }
    else:
        assert payload["evaluation"] is None

    if payload["explanation"] is not None:
        assert set(payload["explanation"]) == {
            "top_features",
            "neighbors_used",
            "avg_neighbor_distance",
            "nearest_analog_date",
            "narrative",
        }
        assert isinstance(payload["explanation"]["top_features"], list)
        assert payload["source"]["analysis"]
        top_feature = payload["explanation"]["top_features"][0]
        assert {"feature", "difference_score", "value", "relation"} <= set(top_feature)


def test_predict_success_returns_typed_contract(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: MarketSeries(
            close=_close_series(),
            resolved_symbol="AAPL",
            currency="USD",
            source="yfinance",
        ),
    )

    response = client.post(
        "/api/predict",
        json={"symbol": "AAPL", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_predict_contract(payload, evaluation_expected=False)
    assert payload["currency"] == "USD"
    assert payload["engine_requested"] == "stat"
    assert payload["engine_used"] == "stat"
    assert payload["source"]["market_data"] == "yfinance"
    assert payload["source"]["forecast"] == "stat"
    assert payload["source"]["data_quality"] == "clean"
    assert payload["degraded"] is False


def test_predict_get_is_kept_for_backward_compatibility(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: MarketSeries(
            close=_close_series(),
            resolved_symbol="AAPL",
            currency="USD",
            source="yfinance",
        ),
    )

    response = client.get("/api/predict?symbol=AAPL&horizon=30&engine=stat&asset_type=stock")

    assert response.status_code == 200
    payload = response.json()
    _assert_predict_contract(payload, evaluation_expected=False)
    assert payload["symbol"] == "AAPL"


def test_predict_rejects_invalid_payload_shape(client) -> None:
    response = client.post(
        "/api/predict",
        json={"symbol": "A A", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_predict_maps_not_found_errors(client, monkeypatch) -> None:
    def raise_not_found(**_):
        raise ServiceError(status_code=404, code="not_found", message="No price data found.")

    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", raise_not_found)

    response = client.post(
        "/api/predict",
        json={"symbol": "MISS", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_predict_maps_rate_limit_errors(client, monkeypatch) -> None:
    def raise_rate_limit(*_, **__):
        raise ServiceError(
            status_code=429, code="rate_limited", message="Too many requests.", retryable=True
        )

    monkeypatch.setattr(client.app.state.rate_limiter, "enforce_predict_limit", raise_rate_limit)

    response = client.post(
        "/api/predict",
        json={"symbol": "AAPL", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_predict_maps_provider_errors(client, monkeypatch) -> None:
    def raise_provider_unavailable(**_):
        raise ServiceError(
            status_code=502,
            code="provider_unavailable",
            message="Market data provider temporarily unavailable.",
            retryable=True,
        )

    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices", raise_provider_unavailable
    )

    response = client.post(
        "/api/predict",
        json={"symbol": "AAPL", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unavailable"


def test_predict_degrades_to_statistical_fallback_when_ml_quality_gate_fails(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: MarketSeries(
            close=_close_series(),
            resolved_symbol="AAPL",
            currency="USD",
            source="yfinance",
        ),
    )
    monkeypatch.setattr(
        "backend.services.prediction.backtest_stat_forecast",
        lambda *_, **__: {"mape": 6.0, "directional_accuracy": 0.58, "validation_windows": 5},
    )

    def fake_train_and_predict(**_):
        return (
            _ml_forecast_result(),
            BacktestMetrics(
                mae=4.2,
                rmse=5.1,
                mape=2.8,
                directional_accuracy=0.40,
                validation_windows=5,
            ),
        )

    monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

    response = client.post(
        "/api/predict",
        json={"symbol": "AAPL", "horizon": 30, "engine": "ml", "asset_type": "stock"},
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_predict_contract(payload, evaluation_expected=True)
    assert payload["engine_requested"] == "ml"
    assert payload["engine_used"] == "stat_fallback"
    assert payload["degraded"] is True
    assert payload["degradation_code"] == "model_quality_insufficient"
    assert payload["source"]["forecast"] == "stat_fallback"
    assert payload["source"]["analysis"] == "ml_pattern_difference"
    assert payload["evaluation"]["directional_accuracy"] == 0.40
    assert payload["evaluation"]["validation_windows"] == 5
    assert payload["explanation"] is not None
    assert payload["explanation"]["nearest_analog_date"] == "2024-09-18"
    assert payload["explanation"]["top_features"][0]["feature"] == "rsi_14"
    assert payload["explanation"]["top_features"][0]["relation"] == "higher"


def test_predict_degrades_to_statistical_fallback_when_ai_fails(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: MarketSeries(
            close=_close_series(),
            resolved_symbol="BTC-USD",
            currency="USD",
            source="yfinance",
        ),
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

    response = client.post(
        "/api/predict",
        json={"symbol": "BTC", "horizon": 30, "engine": "ai", "asset_type": "crypto"},
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_predict_contract(payload, evaluation_expected=False)
    assert payload["engine_used"] == "stat_fallback"
    assert payload["degraded"] is True
    assert payload["degradation_code"] == "ai_provider_unavailable"
    assert (
        payload["degradation_message"]
        == "AI unavailable (OpenAI service unreachable.). Fell back to statistical forecast."
    )
    assert payload["degradation_reason"] == payload["degradation_message"]
    assert payload["source"]["forecast"] == "stat_fallback"


def test_request_size_limit_rejects_large_body_without_content_length() -> None:
    sent_messages: list[dict] = []
    app_called = False

    async def app(scope, receive, send) -> None:
        nonlocal app_called
        app_called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    middleware = RequestSizeLimitMiddleware(app, max_body_bytes=32)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/predict",
        "headers": [(b"content-type", b"application/json")],
    }
    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 33, "more_body": False},
        ]
    )

    async def receive():
        return next(messages)

    async def send(message):
        sent_messages.append(message)

    asyncio.run(middleware(scope, receive, send))

    assert app_called is False
    assert sent_messages[0]["status"] == 413


def test_request_size_limit_rejects_large_body_with_misleading_content_length() -> None:
    sent_messages: list[dict] = []
    app_called = False

    async def app(scope, receive, send) -> None:
        nonlocal app_called
        app_called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    middleware = RequestSizeLimitMiddleware(app, max_body_bytes=32)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/predict",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", b"16"),
        ],
    }
    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 16, "more_body": True},
            {"type": "http.request", "body": b"y" * 17, "more_body": False},
        ]
    )

    async def receive():
        return next(messages)

    async def send(message):
        sent_messages.append(message)

    asyncio.run(middleware(scope, receive, send))

    assert app_called is False
    assert sent_messages[0]["status"] == 413


def test_request_size_limit_replays_buffered_body_for_downstream() -> None:
    sent_messages: list[dict] = []
    received_messages: list[dict] = []

    async def app(scope, receive, send) -> None:
        while True:
            message = await receive()
            received_messages.append(message)
            if message["type"] == "http.request" and not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    middleware = RequestSizeLimitMiddleware(app, max_body_bytes=32)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/predict",
        "headers": [(b"content-type", b"application/json")],
    }
    expected_messages = [
        {"type": "http.request", "body": b"x" * 16, "more_body": True},
        {"type": "http.request", "body": b"y" * 16, "more_body": False},
    ]
    messages = iter(expected_messages)

    async def receive():
        return next(messages)

    async def send(message):
        sent_messages.append(message)

    asyncio.run(middleware(scope, receive, send))

    assert sent_messages[0]["status"] == 200
    assert received_messages == expected_messages


def test_top_assets_returns_timeout_when_blocking_lookup_exceeds_request_timeout(
    monkeypatch,
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    def slow_top_assets(**_):
        time.sleep(0.05)
        return ([], "provider")

    monkeypatch.setattr("backend.routes.api.resolve_top_assets", slow_top_assets)

    with TestClient(create_app()) as client:
        client.app.state.settings = replace(
            client.app.state.settings, top_assets_timeout_seconds=0.01
        )
        response = client.get("/api/top-assets?limit=10&asset_type=stock")

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "top_assets_timeout"


def test_production_startup_requires_redis(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)

    app = create_app()
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass
