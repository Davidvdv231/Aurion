from __future__ import annotations

import ipaddress
import logging
import time
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

from fastapi import Request as FastAPIRequest
from redis import Redis
from redis.exceptions import RedisError

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import EngineType
from backend.services.redis_health import RedisFailureTracker

logger = logging.getLogger("stock_predictor.rate_limit")

REDIS_RATE_LIMIT_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1])
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[2]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow_request(self, key: str, window_seconds: int, limit: int) -> bool:
        now_ts = time.time()
        window_start = now_ts - window_seconds

        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < window_start:
                bucket.popleft()

            if len(bucket) >= limit:
                return False

            bucket.append(now_ts)
            return True


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._memory = InMemoryRateLimiter()
        self._redis: Redis | None = None
        self._redis_script = None
        self._redis_tracker = RedisFailureTracker("rate_limit")

        if settings.is_production and not settings.redis_url:
            raise RuntimeError("Production requires REDIS_URL for Redis-backed rate limiting.")

        if settings.redis_url:
            self._redis = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_socket_timeout_seconds,
                socket_connect_timeout=settings.redis_socket_timeout_seconds,
            )
            self._redis_script = self._redis.register_script(REDIS_RATE_LIMIT_SCRIPT)
            if settings.is_production:
                try:
                    self._redis.ping()
                    self._redis_tracker.record_success(logger)
                except RedisError as exc:
                    self._redis_tracker.record_failure(logger, exc)
                    raise RuntimeError("Production Redis rate limiting is unavailable.") from exc

    def _should_fail_open(self) -> bool:
        return self._settings.rate_limit_fail_open and not self._settings.is_production

    def _is_trusted_proxy(self, client_host: str) -> bool:
        try:
            client_ip = ipaddress.ip_address(client_host)
        except ValueError:
            return client_host in self._settings.trusted_proxy_ips

        for raw_entry in self._settings.trusted_proxy_ips:
            entry = raw_entry.strip()
            if not entry:
                continue
            try:
                if "/" in entry:
                    if client_ip in ipaddress.ip_network(entry, strict=False):
                        return True
                    continue
                if client_ip == ipaddress.ip_address(entry):
                    return True
            except ValueError:
                if client_host == entry:
                    return True
        return False

    def _client_identifier(self, request: FastAPIRequest) -> str:
        direct_client = request.client.host if request.client else "unknown"

        if not self._settings.use_trusted_proxy_headers:
            return direct_client

        if not self._is_trusted_proxy(direct_client):
            return direct_client

        forwarded_for = request.headers.get("x-forwarded-for", "")
        if not forwarded_for:
            return direct_client

        first = forwarded_for.split(",", 1)[0].strip()
        return first or direct_client

    def _rate_limit_backend_unavailable(self) -> ServiceError:
        return ServiceError(
            status_code=503,
            code="rate_limit_backend_unavailable",
            message="Rate limit backend unavailable.",
            retryable=True,
        )

    def _redis_allow_request(self, key: str, window_seconds: int, limit: int) -> bool:
        if self._redis is None or self._redis_script is None:
            if not self._should_fail_open():
                raise self._rate_limit_backend_unavailable()
            return self._memory.allow_request(key=key, window_seconds=window_seconds, limit=limit)

        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - (window_seconds * 1000)
        member = f"{now_ms}:{uuid4().hex}"
        redis_key = f"{self._settings.redis_prefix}:rate-limit:{key}"

        try:
            allowed = self._redis_script(
                keys=[redis_key],
                args=[window_start_ms, limit, now_ms, member, window_seconds],
            )
            self._redis_tracker.record_success(logger)
        except RedisError as exc:
            self._redis_tracker.record_failure(logger, exc)
            if not self._should_fail_open():
                raise self._rate_limit_backend_unavailable() from exc
            return self._memory.allow_request(key=key, window_seconds=window_seconds, limit=limit)

        return bool(allowed)

    def enforce_predict_limit(self, request: FastAPIRequest, engine: EngineType) -> None:
        window_seconds = self._settings.rate_limit_window_seconds
        limit = self._settings.rate_limit_max_requests_stat

        if limit <= 0:
            return

        client_key = f"{engine}:{self._client_identifier(request)}"
        if self._redis_allow_request(key=client_key, window_seconds=window_seconds, limit=limit):
            return

        raise ServiceError(
            status_code=429,
            code="rate_limited",
            message=f"Too many requests. Max {limit} requests per {window_seconds}s for engine={engine}.",
            retryable=True,
        )

    def enforce_search_limit(self, request: FastAPIRequest) -> None:
        window_seconds = self._settings.rate_limit_window_seconds
        limit = self._settings.rate_limit_max_requests_search
        if limit <= 0:
            return

        client_key = f"search:{self._client_identifier(request)}"
        if self._redis_allow_request(key=client_key, window_seconds=window_seconds, limit=limit):
            return

        raise ServiceError(
            status_code=429,
            code="rate_limited",
            message=f"Too many search requests. Max {limit} per {window_seconds}s.",
            retryable=True,
        )
