from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from backend.config import Settings
from backend.services.redis_health import RedisFailureTracker

logger = logging.getLogger("stock_predictor.cache")


class InMemoryTTLCache:
    def __init__(self, *, max_items: int, sweep_every_sets: int) -> None:
        self._items: OrderedDict[str, tuple[datetime, Any]] = OrderedDict()
        self._lock = Lock()
        self._max_items = max_items
        self._sweep_every_sets = max(1, sweep_every_sets)
        self._set_operations = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def _sweep_expired_locked(self, now: datetime) -> None:
        expired = [key for key, (expires_at, _) in self._items.items() if expires_at <= now]
        for key in expired:
            self._items.pop(key, None)

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

            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        with self._lock:
            self._items[key] = (expires_at, value)
            self._items.move_to_end(key)
            self._set_operations += 1
            if self._set_operations >= self._sweep_every_sets:
                self._sweep_expired_locked(datetime.now(timezone.utc))
                self._set_operations = 0
            elif len(self._items) > self._max_items:
                # Drop expired entries before evicting live keys to enforce the bound.
                self._sweep_expired_locked(datetime.now(timezone.utc))
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)


class CacheBackend:
    def __init__(self, settings: Settings) -> None:
        self._memory = InMemoryTTLCache(
            max_items=settings.memory_cache_max_items,
            sweep_every_sets=settings.memory_cache_sweep_batch_size,
        )
        self._prefix = settings.redis_prefix
        self._redis: Redis | None = None
        self._redis_tracker = RedisFailureTracker("cache")

        if settings.redis_url:
            self._redis = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_socket_timeout_seconds,
                socket_connect_timeout=settings.redis_socket_timeout_seconds,
            )

    @property
    def memory_size(self) -> int:
        return len(self._memory)

    def redis_ping(self) -> str:
        """Check Redis connectivity. Returns 'connected', 'unavailable', or 'not_configured'."""
        if self._redis is None:
            return "not_configured"
        try:
            self._redis.ping()
            return "connected"
        except Exception:
            return "unavailable"

    def _namespaced(self, key: str) -> str:
        return f"{self._prefix}:cache:{key}"

    def get_json(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                raw = self._redis.get(self._namespaced(key))
                self._redis_tracker.record_success(logger)
            except RedisError as exc:
                self._redis_tracker.record_failure(logger, exc)
            else:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if isinstance(raw, str) and raw:
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Ignoring invalid JSON payload in Redis cache for key=%s", key
                        )

        return self._memory.get(key)

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._memory.set(key, value, ttl_seconds)

        if self._redis is None:
            return

        try:
            serialized = json.dumps(value)
            self._redis.setex(self._namespaced(key), ttl_seconds, serialized)
            self._redis_tracker.record_success(logger)
        except (TypeError, RedisError) as exc:
            self._redis_tracker.record_failure(logger, exc)

    async def close(self) -> None:
        """Close the Redis connection pool (if any) for graceful shutdown."""
        if self._redis is not None:
            try:
                if hasattr(self._redis, "close"):
                    self._redis.close()
                logger.info("Redis connection closed")
            except Exception as exc:
                logger.warning("Error closing Redis connection: %s", exc)
