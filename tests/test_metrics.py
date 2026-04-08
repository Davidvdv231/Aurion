from __future__ import annotations

from backend.services.metrics import PredictionMetrics


def test_snapshot_tracks_requested_and_used_engines() -> None:
    metrics = PredictionMetrics()

    metrics.record_prediction(
        engine_requested="ml",
        engine_used="stat_fallback",
        total_ms=120.0,
        degraded=True,
        degradation_code="model_quality_insufficient",
    )
    metrics.record_prediction(
        engine_requested="stat",
        engine_used="stat",
        total_ms=80.0,
        degraded=False,
    )

    snapshot = metrics.snapshot()

    assert snapshot["predictions_total"] == 2
    assert snapshot["predictions_by_engine"] == {"stat_fallback": 1, "stat": 1}
    assert snapshot["predictions_by_requested_engine"] == {"ml": 1, "stat": 1}
    assert snapshot["fallbacks_total"] == 1
    assert snapshot["fallbacks_by_code"] == {"model_quality_insufficient": 1}


def test_prometheus_exposition_preserves_requested_engine_label() -> None:
    metrics = PredictionMetrics()

    metrics.record_prediction(
        engine_requested="ml",
        engine_used="stat_fallback",
        total_ms=120.0,
        degraded=True,
        degradation_code="model_quality_insufficient",
    )

    body = metrics.prometheus_exposition(uptime_seconds=42, cache_size=7)

    assert (
        'aurion_predictions_total{engine_requested="ml",engine_used="stat_fallback",degraded="true"} 1'
        in body
    )
    assert 'aurion_fallbacks_total{degradation_code="model_quality_insufficient"} 1' in body
