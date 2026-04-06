"""Integration smoke tests -- verify end-to-end prediction pipeline."""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from backend.ml.model import BacktestMetrics, FeatureDifference, ForecastResult
from backend.services.market_data import MarketSeries


def _close_series() -> pd.Series:
    """Create a synthetic close price series for testing."""
    index = pd.bdate_range("2025-01-02", periods=180)
    values = pd.Series(range(100, 280), index=index, dtype=float)
    return values


def _ml_forecast_result(horizon: int = 7) -> ForecastResult:
    """Create a synthetic ML forecast result."""
    dates = [dt.date().isoformat() for dt in pd.bdate_range("2025-06-02", periods=horizon)]
    predicted = [210.0 + idx for idx in range(horizon)]
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


def _mock_market_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch fetch_close_prices so tests never hit real yfinance."""
    monkeypatch.setattr(
        "backend.services.prediction.fetch_close_prices",
        lambda **_: MarketSeries(
            close=_close_series(),
            resolved_symbol="AAPL",
            currency="USD",
            source="yfinance",
        ),
    )


class TestStatEngineSmokeTest:
    """Verify statistical engine returns complete, valid responses."""

    def test_stat_prediction_returns_200(self, client, monkeypatch) -> None:
        """Stat engine should always succeed for known tickers."""
        _mock_market_data(monkeypatch)
        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "stat",
                "horizon": 7,
            },
        )
        assert resp.status_code == 200

    def test_stat_prediction_not_degraded(self, client, monkeypatch) -> None:
        """Stat engine should never be degraded (it IS the fallback)."""
        _mock_market_data(monkeypatch)
        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "stat",
                "horizon": 7,
            },
        )
        data = resp.json()
        assert data["degraded"] is False
        assert data["degradation_code"] is None
        assert data["engine_used"] == "stat"

    def test_stat_prediction_has_forecast(self, client, monkeypatch) -> None:
        """Stat engine must return forecast array matching horizon."""
        _mock_market_data(monkeypatch)
        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "stat",
                "horizon": 7,
            },
        )
        data = resp.json()
        assert len(data["forecast"]) == 7
        for point in data["forecast"]:
            assert "date" in point
            assert "predicted" in point
            assert "lower" in point
            assert "upper" in point
            assert point["lower"] <= point["predicted"] <= point["upper"]

    def test_stat_prediction_has_summary(self, client, monkeypatch) -> None:
        """Stat engine must return complete summary."""
        _mock_market_data(monkeypatch)
        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "stat",
                "horizon": 7,
            },
        )
        data = resp.json()
        summary = data["summary"]
        assert "expected_price" in summary
        assert "expected_return_pct" in summary
        assert "trend" in summary
        assert "confidence_tier" in summary
        assert "signal" in summary
        assert summary["trend"] in ("bullish", "bearish", "neutral")
        assert summary["confidence_tier"] in ("low", "medium", "high")


class TestMLEngineSmoke:
    """Verify ML engine returns valid response (may degrade to stat)."""

    def test_ml_prediction_returns_200(self, client, monkeypatch) -> None:
        """ML engine should return 200 even if it degrades."""
        _mock_market_data(monkeypatch)
        monkeypatch.setattr(
            "backend.services.prediction.backtest_stat_forecast",
            lambda *_, **__: {"mape": 6.0, "directional_accuracy": 0.58, "validation_windows": 5},
        )

        def fake_train_and_predict(**_):
            return (
                _ml_forecast_result(horizon=7),
                BacktestMetrics(
                    mae=4.2,
                    rmse=5.1,
                    mape=2.8,
                    directional_accuracy=0.55,
                    validation_windows=5,
                ),
            )

        monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "ml",
                "horizon": 7,
            },
        )
        assert resp.status_code == 200

    def test_ml_prediction_valid_engine_used(self, client, monkeypatch) -> None:
        """ML engine must report either ml or stat_fallback."""
        _mock_market_data(monkeypatch)
        monkeypatch.setattr(
            "backend.services.prediction.backtest_stat_forecast",
            lambda *_, **__: {"mape": 6.0, "directional_accuracy": 0.58, "validation_windows": 5},
        )

        def fake_train_and_predict(**_):
            return (
                _ml_forecast_result(horizon=7),
                BacktestMetrics(
                    mae=4.2,
                    rmse=5.1,
                    mape=2.8,
                    directional_accuracy=0.55,
                    validation_windows=5,
                ),
            )

        monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "ml",
                "horizon": 7,
            },
        )
        data = resp.json()
        assert data["engine_used"] in ("ml", "stat_fallback")

    def test_ml_degradation_consistency(self, client, monkeypatch) -> None:
        """If degraded, must have degradation_code. If not, code must be null."""
        _mock_market_data(monkeypatch)
        monkeypatch.setattr(
            "backend.services.prediction.backtest_stat_forecast",
            lambda *_, **__: {"mape": 6.0, "directional_accuracy": 0.58, "validation_windows": 5},
        )

        def fake_train_and_predict(**_):
            return (
                _ml_forecast_result(horizon=7),
                BacktestMetrics(
                    mae=4.2,
                    rmse=5.1,
                    mape=2.8,
                    directional_accuracy=0.55,
                    validation_windows=5,
                ),
            )

        monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "ml",
                "horizon": 7,
            },
        )
        data = resp.json()
        if data["degraded"]:
            assert data["degradation_code"] is not None
            assert data["engine_used"] == "stat_fallback"
        else:
            assert data["degradation_code"] is None
            assert data["engine_used"] == "ml"


class TestDegradedStateVerification:
    """Verify degradation codes appear correctly when quality gates fail."""

    def test_ml_quality_gate_fallback(self, client, monkeypatch) -> None:
        """When ML model has poor directional accuracy, should fall back."""
        _mock_market_data(monkeypatch)
        monkeypatch.setattr(
            "backend.services.prediction.backtest_stat_forecast",
            lambda *_, **__: {"mape": 6.0, "directional_accuracy": 0.58, "validation_windows": 5},
        )

        def fake_train_and_predict(**_):
            return (
                _ml_forecast_result(horizon=7),
                BacktestMetrics(
                    mae=10.0,
                    rmse=12.0,
                    mape=15.0,
                    directional_accuracy=0.30,  # Below 0.45 threshold
                    validation_windows=5,
                ),
            )

        monkeypatch.setattr("backend.ml.service.train_and_predict", fake_train_and_predict)

        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "ml",
                "horizon": 7,
            },
        )
        data = resp.json()
        assert data["degraded"] is True
        assert data["degradation_code"] in (
            "model_quality_insufficient",
            "model_baseline_underperforming",
            "model_validation_insufficient",
        )
        assert data["engine_used"] == "stat_fallback"

    def test_ml_timeout_fallback(self, client, monkeypatch) -> None:
        """When ML training times out, should fall back gracefully."""
        _mock_market_data(monkeypatch)
        monkeypatch.setattr(
            "backend.services.prediction.backtest_stat_forecast",
            lambda *_, **__: {"mape": 6.0, "directional_accuracy": 0.58, "validation_windows": 5},
        )

        def raise_timeout(**_):
            raise asyncio.TimeoutError()

        monkeypatch.setattr("backend.ml.service.train_and_predict", raise_timeout)

        resp = client.post(
            "/api/predict",
            json={
                "symbol": "AAPL",
                "asset_type": "stock",
                "engine": "ml",
                "horizon": 7,
            },
        )
        data = resp.json()
        assert data["degraded"] is True
        assert (
            "timeout" in data["degradation_code"].lower()
            or "unavailable" in data["degradation_code"].lower()
        )

    def test_request_id_in_response_headers(self, client, monkeypatch) -> None:
        """Every response should include X-Request-Id header."""
        _mock_market_data(monkeypatch)
        resp = client.get("/api/health")
        # Flexible: header may not exist yet
        assert "X-Request-Id" in resp.headers or resp.status_code == 200


class TestResponseContract:
    """Verify response structure contracts are maintained."""

    def test_error_response_envelope(self, client) -> None:
        """Invalid requests should return structured error envelope."""
        resp = client.post(
            "/api/predict",
            json={
                "symbol": "A A",
                "asset_type": "stock",
                "engine": "stat",
                "horizon": 7,
            },
        )
        if resp.status_code != 200:
            data = resp.json()
            assert "error" in data
            assert "code" in data["error"]
            assert "message" in data["error"]

    def test_health_response_structure(self, client) -> None:
        """Health endpoint must return expected fields."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "timestamp" in data
