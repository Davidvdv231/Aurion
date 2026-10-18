from __future__ import annotations

import pandas as pd
import pytest

from backend.config import Settings
from backend.errors import ServiceError
from backend.services.cache import CacheBackend, InMemoryTTLCache
from backend.services.market_data import (
    PROVIDER_PROBE_SYMBOL,
    candidate_symbols,
    fetch_close_prices,
    infer_currency,
)


def _settings() -> Settings:
    return Settings(
        app_env="development",
        app_title="Aurion test",
        version="test",
        cors_allow_origins=(),
        top_cache_ttl_seconds=300,
        history_cache_ttl_seconds=300,
        blocking_task_timeout_seconds=15.0,
        top_assets_timeout_seconds=8.0,
        executor_max_workers=4,
        memory_cache_max_items=2,
        memory_cache_sweep_batch_size=1,
        rate_limit_window_seconds=60,
        rate_limit_max_requests_stat=30,
        rate_limit_max_requests_search=60,
        rate_limit_fail_open=True,
        redis_url="",
        redis_prefix="test",
        redis_socket_timeout_seconds=1.0,
        trusted_proxy_ips=(),
        ml_min_validation_windows=3,
        ml_min_directional_accuracy=0.45,
        ml_max_mape_vs_baseline=1.0,
        metrics_token="",
    )


def test_candidate_symbols_prioritizes_stock_aliases() -> None:
    candidates = candidate_symbols("KBC", "stock")

    assert candidates[0] == "KBC.BR"
    assert "KBC" in candidates


def test_candidate_symbols_expands_crypto_inputs() -> None:
    candidates = candidate_symbols("BTC", "crypto")

    assert candidates[0] == "BTC-USD"
    assert "BTC-USD" in candidates


def test_infer_currency_uses_market_suffix() -> None:
    assert infer_currency("KBC.BR", "stock") == "EUR"
    assert infer_currency("AAPL", "stock") == "USD"
    assert infer_currency("BTC-USD", "crypto") == "USD"


def test_fetch_close_prices_preserves_cached_quality_metadata() -> None:
    settings = _settings()
    cache = CacheBackend(settings)
    close = pd.Series(
        [100.0, 101.0, 102.0],
        index=pd.to_datetime(["2026-03-24", "2026-03-25", "2026-03-26"]),
        dtype=float,
    )
    cache.set_json(
        "history:stock:AAPL",
        {
            "provider": "yfinance",
            "resolved_symbol": "AAPL",
            "currency": "USD",
            "data_quality": "degraded",
            "data_warnings": ["Gap detected in source data."],
            "points": [
                {"date": idx.date().isoformat(), "close": float(value)}
                for idx, value in close.items()
            ],
            "ohlcv": [
                {
                    "date": idx.date().isoformat(),
                    "open": float(value - 1),
                    "high": float(value + 1),
                    "low": float(value - 2),
                    "close": float(value),
                    "volume": 1000.0,
                }
                for idx, value in close.items()
            ],
        },
        settings.history_cache_ttl_seconds,
    )

    result = fetch_close_prices(
        symbol="AAPL",
        asset_type="stock",
        cache_backend=cache,
        settings=settings,
    )

    assert result.source == "cache:yfinance"
    assert result.data_quality == "degraded"
    assert "Gap detected in source data." in result.data_warnings
    assert result.ohlcv is not None
    assert list(result.ohlcv.columns) == ["Open", "High", "Low", "Close", "Volume"]


def _download_returning_empty_except_probe(probe_frame: pd.DataFrame, calls: list[str]):
    def fake_download(ticker, *args, **kwargs):
        calls.append(ticker)
        return probe_frame if ticker == PROVIDER_PROBE_SYMBOL else pd.DataFrame()

    return fake_download


def test_fetch_close_prices_reports_not_found_when_provider_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    calls: list[str] = []
    probe_frame = pd.DataFrame({"Close": [500.0]}, index=pd.to_datetime(["2026-10-16"]))
    monkeypatch.setattr(
        "backend.services.market_data.yf.download",
        _download_returning_empty_except_probe(probe_frame, calls),
    )

    with pytest.raises(ServiceError) as exc_info:
        fetch_close_prices(
            symbol="ZZZZQ",
            asset_type="stock",
            cache_backend=CacheBackend(settings),
            settings=settings,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"
    assert calls[-1] == PROVIDER_PROBE_SYMBOL


def test_fetch_close_prices_reports_provider_unavailable_when_yahoo_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.services.market_data.yf.download",
        _download_returning_empty_except_probe(pd.DataFrame(), calls),
    )

    with pytest.raises(ServiceError) as exc_info:
        fetch_close_prices(
            symbol="AAPL",
            asset_type="stock",
            cache_backend=CacheBackend(settings),
            settings=settings,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "provider_unavailable"
    assert exc_info.value.retryable is True


def test_in_memory_ttl_cache_evicts_oldest_entries() -> None:
    cache = InMemoryTTLCache(max_items=2, sweep_every_sets=1)
    cache.set("one", 1, 60)
    cache.set("two", 2, 60)
    cache.set("three", 3, 60)

    assert cache.get("one") is None
    assert cache.get("two") == 2
    assert cache.get("three") == 3


def test_in_memory_ttl_cache_discards_expired_entries_before_live_eviction() -> None:
    cache = InMemoryTTLCache(max_items=2, sweep_every_sets=99)
    cache.set("keep", 1, 60)
    cache.set("expired", 2, 0)
    cache.set("new", 3, 60)

    assert cache.get("keep") == 1
    assert cache.get("expired") is None
    assert cache.get("new") == 3
