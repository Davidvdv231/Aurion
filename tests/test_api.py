from __future__ import annotations

import pandas as pd

from backend.errors import ServiceError
from backend.services.market_data import MarketSeries


def _close_series() -> pd.Series:
    index = pd.bdate_range("2025-01-02", periods=120)
    values = pd.Series(range(100, 220), index=index, dtype=float)
    return values


def test_predict_success_returns_typed_contract(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.routes.api.fetch_close_prices",
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
    assert payload["currency"] == "USD"
    assert payload["source"] == {"market_data": "yfinance", "forecast": "stat"}
    assert payload["degraded"] is False


def test_predict_get_is_kept_for_backward_compatibility(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.routes.api.fetch_close_prices",
        lambda **_: MarketSeries(
            close=_close_series(),
            resolved_symbol="AAPL",
            currency="USD",
            source="yfinance",
        ),
    )

    response = client.get("/api/predict?symbol=AAPL&horizon=30&engine=stat&asset_type=stock")

    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"


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

    monkeypatch.setattr("backend.routes.api.fetch_close_prices", raise_not_found)

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

    monkeypatch.setattr("backend.routes.api.fetch_close_prices", raise_provider_unavailable)

    response = client.post(
        "/api/predict",
        json={"symbol": "AAPL", "horizon": 30, "engine": "stat", "asset_type": "stock"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unavailable"


def test_predict_degrades_to_statistical_fallback_when_ai_fails(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.routes.api.fetch_close_prices",
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

    monkeypatch.setattr("backend.routes.api.build_ai_forecast", raise_ai_failure)

    response = client.post(
        "/api/predict",
        json={"symbol": "BTC", "horizon": 30, "engine": "ai", "asset_type": "crypto"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_used"] == "stat_fallback"
    assert payload["degraded"] is True
    assert payload["degradation_reason"] == "OpenAI niet bereikbaar."
    assert payload["source"]["forecast"] == "stat_fallback"
