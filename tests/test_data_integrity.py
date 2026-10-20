from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.config import get_settings
from backend.ml.features import compute_features
from backend.services.cache import CacheBackend
from backend.services.market_data import fetch_close_prices, resolve_top_assets


@pytest.mark.parametrize("kind, rsi", [("rising", 100), ("falling", 0), ("flat", 50)])
def test_indicators_keep_monotonic_and_flat_market_history(kind, rsi):
    values = np.arange(1, 201, dtype=float)
    if kind == "falling":
        values = values[::-1]
    elif kind == "flat":
        values[:] = 100
    frame = pd.DataFrame(
        {"Close": values, "Volume": 1000.0}, index=pd.bdate_range("2025-01-01", periods=200)
    )
    features = compute_features(frame)
    assert len(features) == 150
    assert np.isfinite(features.to_numpy()).all()
    assert features["rsi_14"].iloc[-1] == rsi


def test_invalid_source_prices_are_removed_before_forecasting(monkeypatch):
    close = np.linspace(10, 20, 100)
    close[:4] = [np.nan, np.inf, -1, 0]
    frame = pd.DataFrame({"Close": close}, index=pd.bdate_range("2026-01-01", periods=100))
    monkeypatch.setattr("backend.services.market_data.yf.download", lambda *_, **__: frame)
    result = fetch_close_prices("AAPL", "stock", CacheBackend(get_settings()), get_settings())
    assert len(result.close) == 96
    assert np.isfinite(result.close).all() and (result.close > 0).all()
    assert result.data_quality != "clean"
    assert result.data_warnings


def test_corrupt_cached_history_is_refetched(monkeypatch):
    cache = CacheBackend(get_settings())
    cache.set_json(
        "history:stock:AAPL",
        {"resolved_symbol": "AAPL", "currency": "USD", "points": [{"date": "bad", "close": 10}]},
        300,
    )
    frame = pd.DataFrame(
        {"Close": np.linspace(10, 20, 100)}, index=pd.bdate_range("2026-01-01", periods=100)
    )
    monkeypatch.setattr("backend.services.market_data.yf.download", lambda *_, **__: frame)
    assert fetch_close_prices("AAPL", "stock", cache, get_settings()).source == "yfinance"


def test_top_assets_cache_serves_larger_limits_without_refetch(monkeypatch):
    calls = []

    def trending(**kwargs):
        calls.append(kwargs)
        return ["AAPL"]

    monkeypatch.setattr("backend.services.market_data._fetch_yahoo_trending", trending)
    cache = CacheBackend(get_settings())
    first, _ = resolve_top_assets(5, "stock", cache, get_settings())
    second, source = resolve_top_assets(25, "stock", cache, get_settings())
    assert len(first) == 5 and len(second) == 25
    assert source.startswith("cache:") and len(calls) == 3


def test_memory_cache_hit_avoids_redis_roundtrip():
    class Redis:
        def get(self, _):
            pytest.fail("A fresh local hit should not contact Redis")

    cache = CacheBackend(get_settings())
    cache.set_json("test", {"value": 1}, 300)
    cache._redis = Redis()
    assert cache.get_json("test") == {"value": 1}


def test_market_provider_stops_candidate_search_after_timeout(monkeypatch):
    from backend.errors import ServiceError

    clock = [0.0]
    calls = []
    monkeypatch.setattr("backend.services.market_data.time.monotonic", lambda: clock[0])

    def download(*args, **kwargs):
        calls.append(kwargs)
        clock[0] = 20.0
        return pd.DataFrame()

    monkeypatch.setattr("backend.services.market_data.yf.download", download)
    with pytest.raises(ServiceError) as error:
        fetch_close_prices("UNKNOWN", "stock", CacheBackend(get_settings()), get_settings())
    assert error.value.status_code == 504
    assert len(calls) == 1
