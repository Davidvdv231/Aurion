"""Click through the Expo web export of the mobile app against a mocked API.

Build the export first (CI does this):
    cd mobile && EXPO_PUBLIC_API_BASE_URL=http://api.aurion.test \
        npx expo export --platform web --output-dir ../build/mobile-web
    MOBILE_WEB_EXPORT_DIR=build/mobile-web python -m pytest tests/test_mobile_web_smoke.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest
from playwright.sync_api import Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
# Same override as tests/test_frontend_smoke.py, for a Chromium that doesn't
# match the pinned Playwright release (e.g. Claude Code cloud sessions).
CHROMIUM_EXECUTABLE = os.environ.get("AURION_CHROMIUM_EXECUTABLE") or None
API_BASE = "http://api.aurion.test"
PORT = 8767
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
}


def _ticker(symbol: str, name: str, asset_type: str) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "exchange": "Crypto" if asset_type == "crypto" else "NASDAQ",
        "region": "GLOBAL" if asset_type == "crypto" else "US",
        "popularity": 900,
        "asset_type": asset_type,
        "source": "catalog",
    }


def _top_assets(asset_type: str) -> dict:
    items = (
        [_ticker("BTC-USD", "Bitcoin", "crypto"), _ticker("ETH-USD", "Ethereum", "crypto")]
        if asset_type == "crypto"
        else [_ticker("NVDA", "NVIDIA", "stock"), _ticker("MSFT", "Microsoft", "stock")]
    )
    return {
        "generated_at": "2026-10-18T12:00:00+00:00",
        "asset_type": asset_type,
        "source": "catalog_fallback",
        "items": items,
    }


PREDICTION = {
    "symbol": "BTC-USD",
    "requested_symbol": "BTC-USD",
    "asset_type": "crypto",
    "currency": "USD",
    "native_currency": "USD",
    "display_currency": "USD",
    "generated_at": "2026-10-18T12:00:00+00:00",
    "horizon_days": 7,
    "engine_requested": "stat",
    "engine_used": "stat",
    "model_name": "Statistical Trend",
    "engine_note": "Damped log-linear trend from the last close, with volatility-based ranges.",
    "source": {
        "market_data": "yfinance",
        "forecast": "stat",
        "analysis": None,
        "data_quality": "clean",
        "data_warnings": [],
        "stale": False,
    },
    "degraded": False,
    "degradation_code": None,
    "degradation_message": None,
    "degradation_reason": None,
    "history": [
        {"date": f"2026-10-{day:02d}", "close": 80000.0 + day * 150.0} for day in range(1, 18)
    ],
    "forecast": [
        {
            "date": f"2026-10-{day:02d}",
            "predicted": 82600.0 + (day - 18) * 60.0,
            "lower": 81000.0 - (day - 18) * 400.0,
            "upper": 84200.0 + (day - 18) * 400.0,
        }
        for day in range(18, 25)
    ],
    "stats": {"daily_trend_pct": 0.07, "last_close": 82550.0},
    "summary": {
        "expected_price": 82960.0,
        "expected_return_pct": 0.5,
        "trend": "neutral",
        "confidence_tier": "medium",
        "signal": "Neutral",
    },
    "evaluation": {
        "mae": 1650.0,
        "rmse": 2100.0,
        "mape": 2.2,
        "directional_accuracy": 0.5,
        "validation_windows": 5,
        "no_change_mape": 2.0,
        "beats_no_change": False,
    },
    "explanation": None,
    "disclaimer": "This is an estimate, not financial advice.",
}


@pytest.fixture(scope="module")
def mobile_web_url():
    export_dir = os.environ.get("MOBILE_WEB_EXPORT_DIR")
    if not export_dir:
        if os.environ.get("CI"):
            pytest.fail("MOBILE_WEB_EXPORT_DIR must point at the Expo web export in CI")
        pytest.skip("Set MOBILE_WEB_EXPORT_DIR to an Expo web export (see module docstring)")

    directory = Path(export_dir)
    if not directory.is_absolute():
        directory = ROOT / directory
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
        cwd=directory,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{PORT}/"
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with urlopen(url, timeout=2):
                    break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("static server for the mobile export did not start")
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_guest_opens_crypto_forecast_from_live_api(mobile_web_url: str) -> None:
    predict_bodies: list[dict] = []
    page_errors: list[str] = []

    def handle_api(route: Route) -> None:
        request = route.request
        if request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
            return
        parsed = urlparse(request.url)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/top-assets":
            body: dict = _top_assets(query.get("asset_type", ["stock"])[0])
        elif parsed.path == "/api/tickers":
            body = {"query": query.get("query", [""])[0], "asset_type": "stock", "tickers": []}
        elif parsed.path == "/api/predict":
            predict_bodies.append(json.loads(request.post_data or "{}"))
            body = PREDICTION
        else:
            route.fulfill(status=404, headers=CORS, content_type="application/json", body="{}")
            return
        route.fulfill(
            status=200, headers=CORS, content_type="application/json", body=json.dumps(body)
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROMIUM_EXECUTABLE)
        try:
            page = browser.new_page(viewport={"width": 420, "height": 860})
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.route(f"{API_BASE}/**", handle_api)

            page.goto(mobile_web_url, wait_until="networkidle")
            page.get_by_text("Continue as guest").click()

            page.get_by_text("NVIDIA").wait_for()
            assert page.get_by_text("demo highlights", exact=False).count() == 0

            page.get_by_text("Crypto", exact=True).click()
            page.get_by_text("Bitcoin").click()
            page.get_by_text("Expected price in 7 days").wait_for()
            page.wait_for_function(
                "() => document.body.innerText.includes('82,960') || "
                "document.body.innerText.includes('82960')"
            )

            assert predict_bodies, "the detail screen never called /api/predict"
            assert predict_bodies[-1]["symbol"] == "BTC-USD"
            assert predict_bodies[-1]["asset_type"] == "crypto"
            assert predict_bodies[-1]["engine"] == "stat"
            assert page.get_by_text("Demo data", exact=False).count() == 0
            page.get_by_text("Beats a no-change guess").wait_for()
            assert page.get_by_text("missed by more than simply assuming", exact=False).is_visible()
        finally:
            browser.close()

    assert page_errors == []
