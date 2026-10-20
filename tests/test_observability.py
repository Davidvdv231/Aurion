"""Integration tests for observability and hardening surfaces.

These tests lock in behavior that is easy to silently regress:

* Security headers (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
* Request-id sanitization + echo
* 500 exception handler carrying request_id
* /api/health/ready actually probing live dependencies
* /api/metrics token gating and Prometheus exposition shape
* Production startup fail-fast on unreplaced deploy-time placeholders
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import _JsonFormatter, create_app


def test_json_logs_preserve_operational_fields_without_arbitrary_secrets():
    record = logging.makeLogRecord(
        {
            "msg": "startup.complete",
            "levelname": "INFO",
            "boot_ms": 42,
            "app_env": "production",
            "request_id": "trace",
            "metrics_token": "must-not-be-logged",
        }
    )
    payload = json.loads(_JsonFormatter().format(record))
    assert payload["boot_ms"] == 42 and payload["app_env"] == "production"
    assert "metrics_token" not in payload


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------


def test_security_headers_present_on_api_response(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    # API responses must never be cached anywhere.
    assert response.headers["Cache-Control"] == "no-store"


def test_security_headers_on_frontend_shell(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-cache"


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------


def test_request_id_echoed_when_client_provides_one(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-Id": "abc-123_DEF"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "abc-123_DEF"


def test_request_id_is_sanitized_to_safe_charset(client: TestClient) -> None:
    # Injected control chars and CRLF must be stripped before the value is echoed
    # or logged — otherwise this is a textbook log-injection vector.
    response = client.get(
        "/api/health",
        headers={"X-Request-Id": "abc\r\n123<script>"},
    )

    assert response.status_code == 200
    echoed = response.headers["X-Request-Id"]
    assert "\r" not in echoed and "\n" not in echoed
    assert "<" not in echoed and ">" not in echoed
    assert echoed == "abc123script"


def test_request_id_generated_when_missing(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["X-Request-Id"]
    # uuid4().hex → 32 hex chars
    assert len(response.headers["X-Request-Id"]) == 32


# ---------------------------------------------------------------------------
# 500 handler must carry request_id
# ---------------------------------------------------------------------------


def test_unhandled_exception_response_includes_request_id(monkeypatch) -> None:
    # TestClient re-raises server exceptions by default for debuggability.
    # The 500 handler is exactly what we're exercising here, so we disable that.
    monkeypatch.delenv("REDIS_URL", raising=False)

    def boom(**_):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("backend.services.prediction.fetch_close_prices", boom)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as crash_client:
        response = crash_client.post(
            "/api/predict",
            json={"symbol": "AAPL", "horizon": 30, "engine": "stat", "asset_type": "stock"},
            headers={"X-Request-Id": "trace-42"},
        )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["details"]["request_id"] == "trace-42"
    assert response.headers["X-Request-Id"] == "trace-42"


# ---------------------------------------------------------------------------
# /api/health/ready deep-probe
# ---------------------------------------------------------------------------


def test_health_ready_reports_executor_and_redis_status(client: TestClient) -> None:
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    # Without REDIS_URL the dev default is "not_configured", which is acceptable
    # in non-production. Production config is covered by the fail-fast test below.
    assert payload["checks"]["redis"] in {"not_configured", "connected"}
    assert payload["checks"]["executor"] == "available"


def test_health_ready_returns_503_when_executor_is_unresponsive(
    client: TestClient, monkeypatch
) -> None:
    # Force the blocking runner to time out — this simulates a saturated pool
    # or a dead event-loop/semaphore binding. K8s must see 503 and stop routing.
    import asyncio

    async def always_timeout(*_args, **_kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(client.app.state.blocking_runner, "run", always_timeout)

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert payload["checks"]["executor"] == "timeout"


# ---------------------------------------------------------------------------
# /api/metrics and /api/metrics/prometheus
# ---------------------------------------------------------------------------


def test_metrics_json_without_token_returns_snapshot_shape(client: TestClient) -> None:
    response = client.get("/api/metrics")

    assert response.status_code == 200
    payload = response.json()
    # Lock in the dashboard contract so a refactor doesn't silently rename keys.
    assert "predictions_total" in payload
    assert "predictions_by_engine" in payload
    assert "predictions_by_requested_engine" in payload
    assert "fallbacks_total" in payload
    assert "fallbacks_by_code" in payload


def test_metrics_prometheus_without_token_returns_exposition_format(client: TestClient) -> None:
    response = client.get("/api/metrics/prometheus")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "aurion_predictions_total" in body
    assert "aurion_prediction_duration_seconds" in body


def test_metrics_requires_token_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("METRICS_TOKEN", "s3cret")

    with TestClient(create_app()) as token_client:
        unauthorized = token_client.get("/api/metrics")
        authorized = token_client.get("/api/metrics", headers={"Authorization": "Bearer s3cret"})
        wrong = token_client.get("/api/metrics", headers={"Authorization": "Bearer nope"})

    assert unauthorized.status_code == 403
    assert authorized.status_code == 200
    assert wrong.status_code == 403


# ---------------------------------------------------------------------------
# /api/validation-summary
# ---------------------------------------------------------------------------


def test_validation_summary_returns_configured_quality_gates(client: TestClient) -> None:
    response = client.get("/api/validation-summary")

    assert response.status_code == 200
    payload = response.json()
    gates = payload["quality_gates"]
    assert set(gates) == {
        "ml_min_validation_windows",
        "ml_min_directional_accuracy",
        "ml_max_mape_vs_baseline",
    }
    assert isinstance(gates["ml_min_validation_windows"], int)


# ---------------------------------------------------------------------------
# Production fail-fast on unreplaced deploy-time placeholders
# ---------------------------------------------------------------------------


def _prod_env(monkeypatch: pytest.MonkeyPatch, **extra: str) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://unit-test")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)

    class _DummyRedis:
        def register_script(self, _script):
            return lambda *args, **kwargs: 1

        def ping(self) -> bool:
            return True

    monkeypatch.setattr(
        "backend.services.rate_limit.Redis.from_url", lambda *args, **kwargs: _DummyRedis()
    )


def test_production_refuses_to_start_with_template_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prod_env(
        monkeypatch,
        CORS_ALLOW_ORIGINS="https://your-domain.example",
    )

    app = create_app()
    with pytest.raises(RuntimeError, match="CORS template origins"):
        with TestClient(app):
            pass


def test_production_refuses_to_start_with_placeholder_metrics_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prod_env(
        monkeypatch,
        CORS_ALLOW_ORIGINS="https://real-domain.example.com",
        METRICS_TOKEN="replace-me",
    )

    app = create_app()
    with pytest.raises(RuntimeError, match="placeholder METRICS_TOKEN"):
        with TestClient(app):
            pass


def test_production_starts_with_real_cors_and_real_metrics_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prod_env(
        monkeypatch,
        CORS_ALLOW_ORIGINS="https://real-domain.example.com",
        METRICS_TOKEN="a-real-long-random-token-7f3e9",
    )

    # Should not raise — production boot is allowed when placeholders are gone.
    with TestClient(create_app()) as prod_client:
        response = prod_client.get("/api/health")
        assert response.status_code == 200
