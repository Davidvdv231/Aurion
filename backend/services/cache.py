from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from threading import Lock
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from backend.config import Settings

logger = logging.getLogger("stock_predictor.cache")


class InMemoryTTLCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[datetime, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None

            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None

            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        with self._lock:
            self._items[key] = (expires_at, value)


class CacheBackend:
    def __init__(self, settings: Settings) -> None:
        self._memory = InMemoryTTLCache()
        self._prefix = settings.redis_prefix
        self._redis: Redis | None = None
        self._redis_warning_emitted = False

        if settings.redis_url:
            self._redis = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_socket_timeout_seconds,
                socket_connect_timeout=settings.redis_socket_timeout_seconds,
            )

    def _namespaced(self, key: str) -> str:
        return f"{self._prefix}:cache:{key}"

    def _warn_redis(self, exc: Exception) -> None:
        if self._redis_warning_emitted:
            return
        self._redis_warning_emitted = True
        logger.warning("Redis cache unavailable; falling back to in-memory cache: %s", exc)

    def get_json(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                raw = self._redis.get(self._namespaced(key))
            except RedisError as exc:
                self._warn_redis(exc)
            else:
                if raw:
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Ignoring invalid JSON payload in Redis cache for key=%s", key)

        return self._memory.get(key)

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._memory.set(key, value, ttl_seconds)

        if self._redis is None:
            return

        try:
            serialized = json.dumps(value)
            self._redis.setex(self._namespaced(key), ttl_seconds, serialized)
        except (TypeError, RedisError) as exc:
            self._warn_redis(exc)
