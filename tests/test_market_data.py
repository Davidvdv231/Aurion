from __future__ import annotations

import json
from urllib.error import URLError

import pandas as pd
import pytest

from backend.config import Settings
from backend.errors import ServiceError
from backend.services.cache import CacheBackend, InMemoryTTLCache
from backend.services.market_data import (
    PROVIDER_PROBE_SYMBOL,
    _check_ohlcv_integrity,
    _check_staleness,
    _fetch_coingecko_top,
    _fetch_yahoo_trending,
    candidate_symbols,
    fetch_close_prices,
    infer_currency,
    resolve_top_assets,
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


# ---------------------------------------------------------------------------
# Downloads: parsing, candidate fallback, data quality and caching
# ---------------------------------------------------------------------------


def _today() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)


def _yf_frame(
    ticker: str,
    closes: list[float],
    *,
    end: pd.Timestamp | None = None,
    multiindex: bool = True,
) -> pd.DataFrame:
    """A daily frame shaped like yf.download output (MultiIndex columns since yfinance 0.2.48)."""
    index = pd.bdate_range(end=end if end is not None else _today(), periods=len(closes))
    frame = pd.DataFrame(
        {
            "Close": closes,
            "High": [value + 1 for value in closes],
            "Low": [value - 1 for value in closes],
            "Open": closes,
            "Volume": [1_000_000.0] * len(closes),
        },
        index=index,
        dtype=float,
    )
    if multiindex:
        frame.columns = pd.MultiIndex.from_product(
            [frame.columns, [ticker]], names=["Price", "Ticker"]
        )
    return frame


def _rising(rows: int = 120) -> list[float]:
    return [100.0 + index * 0.5 for index in range(rows)]


def _fake_download(responses: dict[str, object], calls: list[str]):
    """Return each ticker's canned response; an exception instance is raised instead."""

    def fake_download(ticker, *args, **kwargs):
        calls.append(ticker)
        response = responses.get(ticker, pd.DataFrame())
        if isinstance(response, Exception):
            raise response
        return response

    return fake_download


def _fetch(symbol: str, asset_type="stock", cache: CacheBackend | None = None):
    settings = _settings()
    return fetch_close_prices(
        symbol=symbol,
        asset_type=asset_type,
        cache_backend=cache or CacheBackend(settings),
        settings=settings,
    )


@pytest.mark.parametrize("multiindex", [True, False])
def test_fetch_close_prices_parses_a_download_and_serves_the_cached_copy(
    monkeypatch: pytest.MonkeyPatch, multiindex: bool
) -> None:
    calls: list[str] = []
    frame = _yf_frame("AAPL", _rising(), multiindex=multiindex)
    monkeypatch.setattr(
        "backend.services.market_data.yf.download", _fake_download({"AAPL": frame}, calls)
    )
    cache = CacheBackend(_settings())

    fresh = _fetch("AAPL", cache=cache)
    cached = _fetch("AAPL", cache=cache)

    assert fresh.source == "yfinance"
    assert fresh.resolved_symbol == "AAPL"
    assert fresh.currency == "USD"
    assert fresh.data_quality == "clean"
    assert fresh.data_warnings == []
    assert fresh.stale is False
    assert len(fresh.close) == 120
    assert fresh.ohlcv is not None
    assert list(fresh.ohlcv.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert calls == ["AAPL"]
    assert cached.source == "cache:yfinance"
    assert cached.close.tolist() == fresh.close.tolist()
    assert cached.ohlcv is not None
    assert cached.ohlcv["High"].tolist() == fresh.ohlcv["High"].tolist()


def test_fetch_close_prices_falls_back_to_a_market_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.services.market_data.yf.download",
        _fake_download({"ZZZQ.DE": _yf_frame("ZZZQ.DE", _rising())}, calls),
    )

    result = _fetch("ZZZQ")

    assert result.resolved_symbol == "ZZZQ.DE"
    assert result.currency == "EUR"
    assert calls == ["ZZZQ", "ZZZQ.AS", "ZZZQ.BR", "ZZZQ.PA", "ZZZQ.DE"]


def test_fetch_close_prices_skips_candidates_that_fail_or_return_junk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.services.market_data.yf.download",
        _fake_download(
            {
                "ZZZQ": RuntimeError("connection reset"),
                "ZZZQ.AS": None,
                "ZZZQ.BR": pd.DataFrame({"Open": [1.0]}),
                "ZZZQ.PA": _yf_frame("ZZZQ.PA", _rising()),
            },
            calls,
        ),
    )

    result = _fetch("ZZZQ")

    assert result.resolved_symbol == "ZZZQ.PA"
    assert result.currency == "EUR"


def test_fetch_close_prices_reports_provider_unavailable_when_every_download_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def always_raise(ticker, *args, **kwargs):
        calls.append(ticker)
        raise RuntimeError("connection reset")

    monkeypatch.setattr("backend.services.market_data.yf.download", always_raise)

    with pytest.raises(ServiceError) as exc_info:
        _fetch("AAPL")

    assert exc_info.value.code == "provider_unavailable"
    # A raised download already proves the outage; no extra probe request is needed.
    assert PROVIDER_PROBE_SYMBOL not in calls


def test_fetch_close_prices_reports_provider_unavailable_when_the_probe_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.services.market_data.yf.download",
        _fake_download({PROVIDER_PROBE_SYMBOL: RuntimeError("dns failure")}, calls),
    )

    with pytest.raises(ServiceError) as exc_info:
        _fetch("ZZZQ")

    assert exc_info.value.code == "provider_unavailable"
    assert calls[-1] == PROVIDER_PROBE_SYMBOL


def test_fetch_close_prices_rejects_a_series_that_is_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.services.market_data.yf.download",
        _fake_download({"AAPL": _yf_frame("AAPL", _rising(30))}, calls),
    )

    with pytest.raises(ServiceError) as exc_info:
        _fetch("AAPL")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "insufficient_history"
    assert "AAPL" in exc_info.value.message


def test_fetch_close_prices_drops_missing_days_and_flags_the_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = _rising()
    for index in range(50, 58):
        closes[index] = float("nan")
    frame = _yf_frame("AAPL", closes, multiindex=False)
    frame.iloc[10, frame.columns.get_loc("Open")] = float("nan")
    frame.iloc[11, frame.columns.get_loc("Volume")] = float("nan")
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.services.market_data.yf.download", _fake_download({"AAPL": frame}, calls)
    )

    result = _fetch("AAPL")

    assert len(result.close) == 112
    assert result.data_quality == "patched"
    assert any("gap" in warning for warning in result.data_warnings)
    assert result.ohlcv is not None
    assert not result.ohlcv.isna().any().any()
    assert result.ohlcv["Open"].iloc[10] == result.ohlcv["Close"].iloc[10]
    assert result.ohlcv["Volume"].iloc[11] == 0.0


def test_fetch_close_prices_marks_an_extreme_move_as_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = _rising()
    closes[90:] = [value * 1.6 for value in closes[90:]]
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.services.market_data.yf.download",
        _fake_download({"AAPL": _yf_frame("AAPL", closes)}, calls),
    )

    result = _fetch("AAPL")

    assert result.data_quality == "degraded"
    assert any("extreme daily moves" in warning for warning in result.data_warnings)


def test_fetch_close_prices_flags_a_stale_series(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    old_frame = _yf_frame("AAPL", _rising(), end=_today() - pd.Timedelta(days=20))
    monkeypatch.setattr(
        "backend.services.market_data.yf.download", _fake_download({"AAPL": old_frame}, calls)
    )

    result = _fetch("AAPL")

    assert result.stale is True
    assert "Data may be stale (last point >3 trading days old)." in result.data_warnings


def test_staleness_threshold_is_shorter_for_crypto() -> None:
    four_days_ago = pd.Series([1.0], index=[_today() - pd.Timedelta(days=4)], dtype=float)

    assert _check_staleness(four_days_ago, "crypto") is True
    assert _check_staleness(four_days_ago, "stock") is False
    assert _check_staleness(pd.Series([], dtype=float), "stock") is True


def test_integrity_check_forward_fills_nans_and_grades_by_ratio() -> None:
    index = pd.bdate_range("2026-01-05", periods=100)
    few = pd.Series(_rising(100), index=index, dtype=float)
    few.iloc[40] = float("nan")
    many = pd.Series(_rising(100), index=index, dtype=float)
    many.iloc[40:50] = float("nan")

    patched, patched_quality, patched_warnings = _check_ohlcv_integrity(few, "AAPL")
    degraded, degraded_quality, degraded_warnings = _check_ohlcv_integrity(many, "AAPL")

    assert patched_quality == "patched"
    assert patched_warnings == ["1 NaN values forward-filled."]
    assert patched.iloc[40] == patched.iloc[39]
    assert degraded_quality == "degraded"
    assert "High NaN ratio" in degraded_warnings[0]
    assert not degraded.isna().any()


# ---------------------------------------------------------------------------
# Symbol candidates and listing currency
# ---------------------------------------------------------------------------


def test_candidate_symbols_normalizes_crypto_pairs() -> None:
    assert "SOL-USD" in candidate_symbols("SOLUSD", "crypto")
    assert "SOL-USD" in candidate_symbols("SOLUSDT", "crypto")
    assert candidate_symbols("ETH-USD", "crypto") == ["ETH-USD"]


def test_candidate_symbols_tries_amsterdam_for_a_trailing_a() -> None:
    assert "ABCD.AS" in candidate_symbols("ABCDA", "stock")


@pytest.mark.parametrize(
    ("symbol", "currency"),
    [
        ("ASML", "USD"),  # the NASDAQ listing; Yahoo prices it in dollars
        ("ASML.AS", "EUR"),
        ("VOD.L", "GBP"),
        ("NESN.SW", "CHF"),
        ("SHOP.TO", "CAD"),
        ("NVDA", "USD"),
    ],
)
def test_infer_currency_follows_the_listing(symbol: str, currency: str) -> None:
    assert infer_currency(symbol, "stock") == currency


# ---------------------------------------------------------------------------
# Top assets: live feeds, catalog fallback and caching
# ---------------------------------------------------------------------------


def test_top_stocks_merge_live_trending_with_the_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_regions: list[str] = []

    def fake_trending(region: str = "US", count: int = 20) -> list[str]:
        requested_regions.append(region)
        return ["NVDA", "ZZZQ"] if region == "US" else ["NVDA"]

    monkeypatch.setattr("backend.services.market_data._fetch_yahoo_trending", fake_trending)
    settings = _settings()
    cache = CacheBackend(settings)

    items, source = resolve_top_assets(5, "stock", cache, settings)
    cached_items, cached_source = resolve_top_assets(5, "stock", cache, settings)

    assert source == "live_yahoo"
    assert [item["symbol"] for item in items[:2]] == ["NVDA", "ZZZQ"]
    assert items[0]["name"] == "NVIDIA"
    assert items[0]["source"] == "live_yahoo"
    assert items[1] == {
        "symbol": "ZZZQ",
        "name": "ZZZQ",
        "exchange": "Yahoo",
        "region": "GLOBAL",
        "popularity": 0,
        "asset_type": "stock",
        "source": "live_yahoo",
    }
    assert {item["source"] for item in items[2:]} == {"catalog"}
    assert len(items) == 5
    assert requested_regions == ["US", "NL", "BE"]
    assert cached_source == "cache:live_yahoo"
    assert cached_items == items


def test_top_stocks_fall_back_to_the_catalog_when_trending_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.services.market_data._fetch_yahoo_trending", lambda region="US", count=20: []
    )
    settings = _settings()

    items, source = resolve_top_assets(4, "stock", CacheBackend(settings), settings)

    assert source == "catalog_fallback"
    assert len(items) == 4
    assert {item["source"] for item in items} == {"catalog"}


def test_top_crypto_uses_live_metadata_for_coins_outside_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = [
        {
            "symbol": "BTC-USD",
            "name": "Bitcoin",
            "exchange": "Crypto",
            "region": "GLOBAL",
            "popularity": 1000,
            "asset_type": "crypto",
        },
        {
            "symbol": "NEWCOIN-USD",
            "name": "New Coin",
            "exchange": "Crypto",
            "region": "GLOBAL",
            "popularity": 980,
            "asset_type": "crypto",
        },
    ]
    monkeypatch.setattr("backend.services.market_data._fetch_coingecko_top", lambda count=20: live)
    settings = _settings()

    items, source = resolve_top_assets(3, "crypto", CacheBackend(settings), settings)

    assert source == "live_coingecko"
    assert [item["symbol"] for item in items[:2]] == ["BTC-USD", "NEWCOIN-USD"]
    assert items[1]["name"] == "New Coin"
    assert items[1]["source"] == "live_coingecko"
    assert items[2]["source"] == "catalog"


def test_top_assets_refetch_when_the_cache_holds_too_few(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_coingecko(count: int = 20) -> list[dict]:
        calls.append(count)
        return []

    monkeypatch.setattr("backend.services.market_data._fetch_coingecko_top", fake_coingecko)
    settings = _settings()
    cache = CacheBackend(settings)
    cache.set_json(
        "top-assets:crypto",
        {"source": "live_coingecko", "items": [{"symbol": "BTC-USD"}]},
        300,
    )

    items, source = resolve_top_assets(3, "crypto", cache, settings)

    assert calls == [20]
    assert source == "catalog_fallback"
    assert len(items) == 3


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _fake_urlopen(payload: object):
    def fake_urlopen(request, timeout=None):
        if isinstance(payload, Exception):
            raise payload
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return _FakeResponse(body)

    return fake_urlopen


def test_yahoo_trending_parser_keeps_only_valid_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "finance": {
            "result": [
                {"quotes": [{"symbol": " nvda "}, {"symbol": ""}, {"name": "no symbol"}, "junk"]}
            ]
        }
    }
    monkeypatch.setattr("backend.services.market_data.urlopen", _fake_urlopen(payload))

    assert _fetch_yahoo_trending("US") == ["NVDA"]


@pytest.mark.parametrize(
    "payload",
    [
        URLError("offline"),
        b"not json",
        ["unexpected", "list"],
        {"finance": None},
        {"finance": {"result": []}},
        {"finance": {"result": [{"quotes": "not a list"}]}},
    ],
)
def test_yahoo_trending_parser_returns_nothing_for_bad_responses(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    monkeypatch.setattr("backend.services.market_data.urlopen", _fake_urlopen(payload))

    assert _fetch_yahoo_trending("US") == []


def test_coingecko_parser_builds_usd_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {"symbol": "btc", "name": "Bitcoin"},
        {"symbol": "eth", "name": "  "},
        {"symbol": "", "name": "Nameless"},
        "junk",
    ]
    monkeypatch.setattr("backend.services.market_data.urlopen", _fake_urlopen(payload))

    items = _fetch_coingecko_top(count=4)

    assert [(item["symbol"], item["name"], item["popularity"]) for item in items] == [
        ("BTC-USD", "Bitcoin", 1000),
        ("ETH-USD", "ETH", 980),
    ]
    assert {item["asset_type"] for item in items} == {"crypto"}


@pytest.mark.parametrize("payload", [URLError("offline"), b"not json", {"error": "rate limited"}])
def test_coingecko_parser_returns_nothing_for_bad_responses(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    monkeypatch.setattr("backend.services.market_data.urlopen", _fake_urlopen(payload))

    assert _fetch_coingecko_top() == []
