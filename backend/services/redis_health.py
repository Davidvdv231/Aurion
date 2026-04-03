from __future__ import annotations

import logging
import time


class RedisFailureTracker:
    def __init__(self, component: str, throttle_seconds: float = 60.0) -> None:
        self._component = component
        self._throttle_seconds = throttle_seconds
        self._degraded = False
        self._last_signature: tuple[str, str] | None = None
        self._last_logged_at = 0.0

    def record_success(self, logger: logging.Logger) -> None:
        if not self._degraded:
            return
        self._degraded = False
        self._last_signature = None
        self._last_logged_at = time.monotonic()
        logger.info("Redis %s recovered.", self._component)

    def record_failure(self, logger: logging.Logger, exc: Exception) -> None:
        now = time.monotonic()
        signature = (type(exc).__name__, str(exc))
        should_log = (
            not self._degraded
            or signature != self._last_signature
            or (now - self._last_logged_at) >= self._throttle_seconds
        )
        self._degraded = True
        self._last_signature = signature
        if not should_log:
            return
        self._last_logged_at = now
        logger.warning("Redis %s unavailable: %s", self._component, exc)
