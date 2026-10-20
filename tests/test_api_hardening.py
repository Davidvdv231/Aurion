from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import get_settings
from backend.services.rate_limit import RateLimiter


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize(
    "invalid",
    [{"symbol": "AAPL\tMSFT"}, {"symbol": "../AAPL"}, {"symbol": " "}, {"display_currency": "XYZ"}],
)
def test_invalid_prediction_input_is_422(method, invalid, monkeypatch):
    def no_provider(**_):
        pytest.fail("Invalid input reached the market data provider")

    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", no_provider)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        payload = {"symbol": "AAPL", "engine": "stat", **invalid}
        response = getattr(client, method)(
            "/api/predict", **({"params": payload} if method == "get" else {"json": payload})
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_invalid_nonfinite_input_has_serializable_validation_error(client):
    response = client.post(
        "/api/predict",
        content='{"symbol":"AAPL","horizon":NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "input" not in response.json()["error"]["details"]["issues"][0]


@pytest.mark.parametrize(
    "forwarded, expected",
    [
        ("203.0.113.99, 198.51.100.44", "198.51.100.44"),
        ("spoofed, 198.51.100.44, 10.0.0.2", "198.51.100.44"),
        ("203.0.113.99, garbage", "10.0.0.1"),
        ("2001:0db8:0:0:0:0:0:1", "2001:db8::1"),
    ],
)
def test_forwarded_chain_uses_nearest_untrusted_valid_ip(forwarded, expected):
    limiter = RateLimiter(replace(get_settings(), trusted_proxy_ips=("10.0.0.0/8",)))
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.1"), headers={"x-forwarded-for": forwarded}
    )
    assert limiter._client_identifier(request) == expected


def test_top_assets_is_rate_limited_before_provider_work(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS_SEARCH", "1")
    monkeypatch.setattr("backend.routes.api.resolve_top_assets", lambda **_: ([], "catalog"))
    with TestClient(create_app()) as client:
        assert client.get("/api/top-assets").status_code == 200
        response = client.get("/api/top-stocks")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.parametrize(
    "path", ["/api/metrics", "/api/metrics/prometheus", "/api/validation-summary"]
)
def test_production_operational_endpoints_fail_closed_without_token(client, path):
    client.app.state.settings = replace(
        client.app.state.settings, app_env="production", metrics_token=""
    )
    assert client.get(path).status_code == 503


def test_oversized_request_keeps_security_and_cache_headers(client):
    response = client.post("/api/predict", content="x" * 1_048_577)
    assert response.status_code == 413
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_crash_keeps_security_and_cors_headers(monkeypatch):
    def crash(**_):
        raise RuntimeError("private details")

    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", crash)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/predict",
            json={"symbol": "AAPL", "engine": "stat"},
            headers={"Origin": "http://localhost:8000"},
        )
    assert response.status_code == 500
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8000"
    assert "private details" not in response.text
