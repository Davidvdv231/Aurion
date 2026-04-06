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
        self.predictions_degraded: dict[str, int] = defaultdict(int)
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
            if degraded:
                self.predictions_degraded[engine_used] = (
                    self.predictions_degraded.get(engine_used, 0) + 1
                )
                if degradation_code:
                    self.fallbacks_total += 1
                    self.fallbacks_by_code[degradation_code] += 1
            self._latencies.append(total_ms)
            # Keep last 1000 for percentile computation
            if len(self._latencies) > 1000:
                self._latencies = self._latencies[-1000:]

    def record_rate_limit(self) -> None:
        with self._lock:
            self.rate_limit_429_total += 1

    def _percentile(self, q: float) -> float:
        """Return the *q*-th percentile (0-1) of recorded latencies in **seconds**."""
        if not self._latencies:
            return 0.0
        sorted_lat = sorted(self._latencies)
        idx = int(len(sorted_lat) * q)
        idx = min(idx, len(sorted_lat) - 1)
        return round(sorted_lat[idx] / 1000.0, 6)  # ms -> seconds

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

    def prometheus_exposition(self, *, uptime_seconds: int = 0, cache_size: int = 0) -> str:
        """Return metrics in Prometheus text exposition format."""
        with self._lock:
            lines: list[str] = []

            # --- predictions total (per engine) ---
            lines.append("# HELP aurion_predictions_total Total predictions served")
            lines.append("# TYPE aurion_predictions_total counter")
            if self.predictions_by_engine:
                for engine, count in self.predictions_by_engine.items():
                    degraded = "true" if engine in self.predictions_degraded else "false"
                    lines.append(
                        f'aurion_predictions_total{{engine_requested="{engine}",'
                        f'engine_used="{engine}",degraded="{degraded}"}} {count}'
                    )
            else:
                lines.append(
                    'aurion_predictions_total{engine_requested="none",'
                    'engine_used="none",degraded="false"} 0'
                )

            # --- fallbacks total (per degradation code) ---
            lines.append("")
            lines.append("# HELP aurion_fallbacks_total Total fallback events")
            lines.append("# TYPE aurion_fallbacks_total counter")
            if self.fallbacks_by_code:
                for code, count in self.fallbacks_by_code.items():
                    lines.append(f'aurion_fallbacks_total{{degradation_code="{code}"}} {count}')
            else:
                lines.append('aurion_fallbacks_total{degradation_code="none"} 0')

            # --- prediction duration (summary with quantiles) ---
            lines.append("")
            lines.append("# HELP aurion_prediction_duration_seconds Prediction request duration")
            lines.append("# TYPE aurion_prediction_duration_seconds summary")
            p50 = self._percentile(0.50)
            p95 = self._percentile(0.95)
            p99 = self._percentile(0.99)
            lines.append(f'aurion_prediction_duration_seconds{{quantile="0.5"}} {p50}')
            lines.append(f'aurion_prediction_duration_seconds{{quantile="0.95"}} {p95}')
            lines.append(f'aurion_prediction_duration_seconds{{quantile="0.99"}} {p99}')

            # --- cache size gauge ---
            lines.append("")
            lines.append("# HELP aurion_cache_size Current cache size")
            lines.append("# TYPE aurion_cache_size gauge")
            lines.append(f'aurion_cache_size{{layer="memory"}} {cache_size}')

            # --- uptime gauge ---
            lines.append("")
            lines.append("# HELP aurion_uptime_seconds Process uptime")
            lines.append("# TYPE aurion_uptime_seconds gauge")
            lines.append(f"aurion_uptime_seconds {uptime_seconds}")

            # --- rate-limit 429s ---
            lines.append("")
            lines.append("# HELP aurion_rate_limit_429_total Total 429 rate-limit responses")
            lines.append("# TYPE aurion_rate_limit_429_total counter")
            lines.append(f"aurion_rate_limit_429_total {self.rate_limit_429_total}")

            lines.append("")
            return "\n".join(lines)
