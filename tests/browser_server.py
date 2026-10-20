"""Local browser-test app: real API/forecasting with deterministic market data."""

from contextlib import asynccontextmanager
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.services.market_data import _serialize_close_series
from backend.ticker_catalog import top_catalog_tickers

with patch("backend.config._load_local_env"):
    from backend.app import create_app

    app = create_app()
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        for symbol, asset_type, scale in [("AAPL", "stock", 100), ("BTC", "crypto", 50_000)]:
            dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=260, freq="D")
            close = pd.Series(scale * np.exp(np.linspace(0, 0.15, 260)), index=dates)
            application.state.cache_backend.set_json(
                f"history:{asset_type}:{symbol}",
                {
                    "provider": "test-fixture",
                    "resolved_symbol": symbol,
                    "currency": "USD",
                    "points": _serialize_close_series(close),
                },
                3600,
            )
        yield


app.router.lifespan_context = lifespan


def top_assets(*, limit, asset_type, **_):
    return top_catalog_tickers(limit=limit, asset_type=asset_type), "catalog_fallback"


# Only this test server substitutes the provider boundary; real routes, validation,
# orchestration, serialization, middleware and browser rendering remain active.
import backend.routes.api as api  # noqa: E402

api.resolve_top_assets = top_assets
