"""Lightweight in-memory prediction metrics (resets on restart)."""
from __future__ import annotations

import statistics
import threading
from collections import defaultdict


class PredictionMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.predictions_total = 0
        self.predictions_by_engine: dict[str, int] = defaultdict(int)
        self.fallbacks_total = 0
        self.fallbacks_by_code: dict[str, int] = defaultdict(int)
        self.rate_limit_429_total = 0
        self._latencies: list[float] = []

    def record_prediction(
        self,
        engine_used: str,
        total_ms: float,
        degraded: bool = False,
        degradation_code: str | None = None,
    ) -> None:
        with self._lock:
            self.predictions_total += 1
            self.predictions_by_engine[engine_used] += 1
            if degraded and degradation_code:
                self.fallbacks_total += 1
                self.fallbacks_by_code[degradation_code] += 1
            self._latencies.append(total_ms)
            # Keep last 1000 for percentile computation
            if len(self._latencies) > 1000:
                self._latencies = self._latencies[-1000:]

    def record_rate_limit(self) -> None:
        with self._lock:
            self.rate_limit_429_total += 1

    def snapshot(self) -> dict:
        with self._lock:
            avg_ms = statistics.mean(self._latencies) if self._latencies else 0.0
            p95_ms = (
                sorted(self._latencies)[int(len(self._latencies) * 0.95)]
                if len(self._latencies) >= 2
                else avg_ms
            )
            return {
                "predictions_total": self.predictions_total,
                "predictions_by_engine": dict(self.predictions_by_engine),
                "fallbacks_total": self.fallbacks_total,
                "fallbacks_by_code": dict(self.fallbacks_by_code),
                "rate_limit_429_total": self.rate_limit_429_total,
                "avg_prediction_ms": round(avg_ms, 1),
                "p95_prediction_ms": round(p95_ms, 1),
            }
