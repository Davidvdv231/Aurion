from __future__ import annotations

from collections import defaultdict, deque
import logging
from threading import Lock
import time
from uuid import uuid4

from fastapi import Request as FastAPIRequest
from redis import Redis
from redis.exceptions import RedisError

from backend.config import Settings
from backend.errors import ServiceError
from backend.models import EngineType

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
        self._redis_warning_emitted = False

        if settings.redis_url:
            self._redis = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_socket_timeout_seconds,
                socket_connect_timeout=settings.redis_socket_timeout_seconds,
            )
            self._redis_script = self._redis.register_script(REDIS_RATE_LIMIT_SCRIPT)

    def _warn_redis(self, exc: Exception) -> None:
        if self._redis_warning_emitted:
            return
        self._redis_warning_emitted = True
        logger.warning("Redis rate limiter unavailable; falling back to in-memory buckets: %s", exc)

    def _client_identifier(self, request: FastAPIRequest) -> str:
        direct_client = request.client.host if request.client else "unknown"

        if not self._settings.use_trusted_proxy_headers:
            return direct_client

        if direct_client not in self._settings.trusted_proxy_ips:
            return direct_client

        forwarded_for = request.headers.get("x-forwarded-for", "")
        if not forwarded_for:
            return direct_client

        first = forwarded_for.split(",", 1)[0].strip()
        return first or direct_client

    def _redis_allow_request(self, key: str, window_seconds: int, limit: int) -> bool:
        if self._redis is None or self._redis_script is None:
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
        except RedisError as exc:
            self._warn_redis(exc)
            return self._memory.allow_request(key=key, window_seconds=window_seconds, limit=limit)

        return bool(allowed)

    def enforce_predict_limit(self, request: FastAPIRequest, engine: EngineType) -> None:
        window_seconds = self._settings.rate_limit_window_seconds
        limit = (
            self._settings.rate_limit_max_requests_ai
            if engine == "ai"
            else self._settings.rate_limit_max_requests_stat
        )

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
        """Rate limit ticker search: 60 requests per window."""
        window_seconds = self._settings.rate_limit_window_seconds
        limit = 60

        client_key = f"search:{self._client_identifier(request)}"
        if self._redis_allow_request(key=client_key, window_seconds=window_seconds, limit=limit):
            return

        raise ServiceError(
            status_code=429,
            code="rate_limited",
            message=f"Too many search requests. Max {limit} per {window_seconds}s.",
            retryable=True,
        )
