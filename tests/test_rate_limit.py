from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from backend.app import create_app
from backend.services.redis_health import RedisFailureTracker


class _HealthyRedis:
    def ping(self) -> bool:
        return True

    def register_script(self, _script):
        def runner(*_args, **_kwargs):
            raise RedisError("rate limit redis down")

        return runner


class _UnavailableRedis:
    def ping(self) -> bool:
        raise RedisError("startup ping failed")

    def register_script(self, _script):
        return lambda *_args, **_kwargs: 1


def test_search_limit_uses_configured_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS_SEARCH", "1")

    with TestClient(create_app()) as client:
        first = client.get("/api/tickers?query=AA&limit=5&asset_type=stock")
        second = client.get("/api/tickers?query=AA&limit=5&asset_type=stock")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


def test_development_runtime_redis_failure_falls_back_to_in_memory_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REDIS_URL", "redis://cache.example:6379/0")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS_SEARCH", "1")
    monkeypatch.setattr(
        "backend.services.rate_limit.Redis.from_url",
        lambda *_, **__: _HealthyRedis(),
    )

    with TestClient(create_app()) as client:
        first = client.get("/api/tickers?query=AA&limit=5&asset_type=stock")
        second = client.get("/api/tickers?query=AA&limit=5&asset_type=stock")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


def test_development_can_disable_rate_limit_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("RATE_LIMIT_FAIL_OPEN", "false")

    with TestClient(create_app()) as client:
        response = client.get("/api/tickers?query=AA&limit=5&asset_type=stock")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rate_limit_backend_unavailable"


def test_production_startup_requires_reachable_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://cache.example:6379/0")
    monkeypatch.setattr(
        "backend.services.rate_limit.Redis.from_url",
        lambda *_, **__: _UnavailableRedis(),
    )

    app = create_app()
    with pytest.raises(RuntimeError, match="unavailable"):
        with TestClient(app):
            pass


def test_production_runtime_redis_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REDIS_URL", "redis://cache.example:6379/0")
    monkeypatch.setattr(
        "backend.services.rate_limit.Redis.from_url",
        lambda *_, **__: _HealthyRedis(),
    )

    with TestClient(create_app()) as client:
        response = client.get("/api/tickers?query=AA&limit=5&asset_type=stock")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rate_limit_backend_unavailable"


def test_redis_failure_tracker_logs_recovery_and_changed_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tracker = RedisFailureTracker("rate_limit", throttle_seconds=999.0)
    logger = logging.getLogger("tests.redis_health")

    with caplog.at_level(logging.WARNING, logger=logger.name):
        tracker.record_failure(logger, RedisError("first failure"))
        tracker.record_failure(logger, RedisError("first failure"))
        tracker.record_failure(logger, RedisError("second failure"))

    warning_messages = [record.getMessage() for record in caplog.records]
    assert warning_messages == [
        "Redis rate_limit unavailable: first failure",
        "Redis rate_limit unavailable: second failure",
    ]

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=logger.name):
        tracker.record_success(logger)

    assert [record.getMessage() for record in caplog.records] == ["Redis rate_limit recovered."]
