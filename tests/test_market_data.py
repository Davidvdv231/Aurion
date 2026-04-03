from __future__ import annotations

import pandas as pd

from backend.config import Settings
from backend.services.cache import CacheBackend
from backend.services.market_data import (
    _serialize_close_series,
    candidate_symbols,
    fetch_close_prices,
    infer_currency,
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


def _test_settings() -> Settings:
    return Settings(
        app_title="test",
        version="test",
        cors_allow_origins=(),
        top_cache_ttl_seconds=300,
        history_cache_ttl_seconds=300,
        rate_limit_window_seconds=60,
        rate_limit_max_requests_stat=30,
        rate_limit_max_requests_ai=8,
        openai_chat_completions_url="",
        openai_model="",
        openai_api_key="",
        stock_llm_api_url="",
        stock_llm_api_key="",
        redis_url="",
        redis_prefix="test",
        redis_socket_timeout_seconds=1.0,
        trusted_proxy_ips=(),
    )


def test_cached_market_data_preserves_quality_metadata(monkeypatch) -> None:
    """Degraded quality metadata must survive a cache round-trip."""
    settings = _test_settings()
    cache = CacheBackend(settings)

    # Seed the cache with a payload that has degraded quality + warnings + stale
    close = pd.Series(range(100, 200), index=pd.bdate_range("2025-01-02", periods=100), dtype=float)
    cache.set_json(
        "history:stock:TEST",
        {
            "provider": "yfinance",
            "resolved_symbol": "TEST",
            "currency": "EUR",
            "points": _serialize_close_series(close),
            "data_quality": "degraded",
            "data_warnings": ["High NaN ratio (6.0%, 6 points) — forward-filled."],
            "stale": True,
        },
        ttl_seconds=300,
    )

    # Patch candidate_symbols so fetch_close_prices hits our cache key
    monkeypatch.setattr(
        "backend.services.market_data.candidate_symbols",
        lambda symbol, asset_type: [symbol],
    )

    result = fetch_close_prices("TEST", "stock", cache, settings)

    assert result.data_quality == "degraded"
    assert len(result.data_warnings) == 1
    assert "NaN" in result.data_warnings[0]
    assert result.stale is True
    assert result.source == "cache:yfinance"


def test_cached_market_data_defaults_cleanly_for_legacy_payloads(monkeypatch) -> None:
    """Cache entries written before the quality fix should still load with safe defaults."""
    settings = _test_settings()
    cache = CacheBackend(settings)

    close = pd.Series(range(100, 200), index=pd.bdate_range("2025-01-02", periods=100), dtype=float)
    cache.set_json(
        "history:stock:LEGACY",
        {
            "provider": "yfinance",
            "resolved_symbol": "LEGACY",
            "currency": "USD",
            "points": _serialize_close_series(close),
            # No data_quality, data_warnings, stale fields — old cache entry
        },
        ttl_seconds=300,
    )

    monkeypatch.setattr(
        "backend.services.market_data.candidate_symbols",
        lambda symbol, asset_type: [symbol],
    )

    result = fetch_close_prices("LEGACY", "stock", cache, settings)

    assert result.data_quality == "clean"
    assert result.data_warnings == []
    assert result.stale is False
