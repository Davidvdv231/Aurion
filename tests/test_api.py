from __future__ import annotations

import pandas as pd

from backend.ml.model import BacktestMetrics, FeatureContribution, ForecastResult
from backend.errors import ServiceError
from backend.services.market_data import MarketSeries


def _close_series() -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=120)
    values = pd.Series(range(100, 220), index=index, dtype=float)
    return values


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
    assert {"market_data", "forecast", "analysis", "data_quality", "data_warnings", "stale"} <= set(payload["source"])
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
        "bullish",
        "mildly_bullish",
        "neutral",
        "mildly_bearish",
        "bearish",
    }
    assert isinstance(payload["history"], list) and payload["history"]
    assert isinstance(payload["forecast"], list) and payload["forecast"]
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
    assert payload["summary"]["confidence_tier"] in {"low", "medium", "high"}


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
        raise ServiceError(status_code=404, code="not_found", message="Geen koersdata gevonden.")

    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", raise_not_found)

    response = client.post(
        "/api/predict",
        json={"symbol": "MISS", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_predict_maps_rate_limit_errors(client, monkeypatch) -> None:
    def raise_rate_limit(*_, **__):
        raise ServiceError(status_code=429, code="rate_limited", message="Te veel requests.", retryable=True)

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
            message="Marktdataprovider tijdelijk niet bereikbaar.",
            retryable=True,
        )

    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", raise_provider_unavailable)

    response = client.post(
        "/api/predict",
        json={"symbol": "AAPL", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unavailable"


def test_predict_degrades_to_statistical_fallback_when_ml_quality_gate_fails(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: MarketSeries(
            close=_close_series(),
            resolved_symbol="AAPL",
            currency="USD",
            source="yfinance",
        ),
    )

    def fake_train_and_predict(**_):
        return (
            ForecastResult(
                dates=["2025-06-02", "2025-06-03"],
                predicted=[210.0, 211.0],
                lower=[205.0, 206.0],
                upper=[215.0, 216.0],
                neighbors_used=12,
                top_features=[
                    FeatureContribution(
                        feature="rsi_14",
                        contribution=0.8,
                        value=68.0,
                        direction="bullish",
                    )
                ],
                avg_neighbor_distance=0.17,
                nearest_analog_date="2024-09-18",
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
    assert payload["degradation_message"] == (
        "ML model quality was insufficient for production use. "
        "Returned the statistical fallback forecast instead."
    )
    assert payload["degradation_reason"] == payload["degradation_message"]
    assert payload["source"]["forecast"] == "stat_fallback"
    assert payload["source"]["analysis"] == "ml_analog"
    assert payload["evaluation"]["directional_accuracy"] == 0.45
    assert payload["evaluation"]["validation_windows"] == 3
    assert payload["explanation"] is not None
    assert payload["explanation"]["nearest_analog_date"] == "2024-09-18"
    assert payload["explanation"]["top_features"][0]["feature"] == "rsi_14"


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
            message="OpenAI niet bereikbaar.",
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
    assert payload["degradation_message"] == "AI unavailable (OpenAI niet bereikbaar.). Fell back to statistical forecast."
    assert payload["degradation_reason"] == payload["degradation_message"]
    assert payload["source"]["forecast"] == "stat_fallback"
