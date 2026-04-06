from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = ROOT / ".venv" / "Scripts" / "python.exe"
BASE_URL = "http://127.0.0.1:8765"

SUCCESS_PREDICTION = {
    "symbol": "AAPL",
    "requested_symbol": "AAPL",
    "asset_type": "stock",
    "currency": "USD",
    "generated_at": "2026-03-10T12:00:00+00:00",
    "horizon_days": 30,
    "engine_requested": "stat",
    "engine_used": "stat",
    "model_name": "Statistical trend",
    "engine_note": "Log-linear statistical trend model on historical prices.",
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
        {"date": "2026-01-01", "close": 100.25},
        {"date": "2026-01-02", "close": 101.25},
        {"date": "2026-01-05", "close": 102.25},
    ],
    "forecast": [
        {"date": "2026-01-06", "predicted": 103.0, "lower": 100.0, "upper": 106.0},
        {"date": "2026-01-07", "predicted": 104.0, "lower": 101.0, "upper": 107.0},
    ],
    "stats": {"daily_trend_pct": 0.321, "last_close": 102.25},
    "summary": {
        "expected_price": 104.0,
        "expected_return_pct": 1.71,
        "trend": "neutral",
        "confidence_tier": "medium",
        "signal": "Bullish Outlook",
    },
    "evaluation": {
        "mae": 1.23,
        "rmse": 1.78,
        "mape": 0.95,
        "directional_accuracy": 0.67,
        "validation_windows": 5,
    },
    "explanation": None,
    "disclaimer": "This is an estimate and not financial advice.",
}
FALLBACK_EXPLANATION_PREDICTION = {
    **SUCCESS_PREDICTION,
    "engine_requested": "ml",
    "engine_used": "stat_fallback",
    "model_name": "Statistical Fallback",
    "engine_note": "ML directional accuracy was insufficient for production use. Returned the statistical fallback forecast instead.",
    "source": {
        "market_data": "yfinance",
        "forecast": "stat_fallback",
        "analysis": "ml_pattern_difference",
        "data_quality": "clean",
        "data_warnings": [],
        "stale": False,
    },
    "degraded": True,
    "degradation_code": "model_quality_insufficient",
    "degradation_message": "ML directional accuracy was insufficient for production use. Returned the statistical fallback forecast instead.",
    "degradation_reason": "ML directional accuracy was insufficient for production use. Returned the statistical fallback forecast instead.",
    "explanation": {
        "top_features": [
            {
                "feature": "rsi_14",
                "difference_score": 0.8,
                "value": 68.0,
                "relation": "higher",
            }
        ],
        "neighbors_used": 12,
        "avg_neighbor_distance": 0.17,
        "nearest_analog_date": "2024-09-18",
        "narrative": "RSI (14) is currently higher than the nearest analog set. The 12 closest historical patterns averaged a +1.7% move over the forecast horizon.",
    },
}
TOP_ASSETS = {
    "generated_at": "2026-03-10T12:00:00+00:00",
    "asset_type": "stock",
    "source": "catalog_fallback",
    "items": [
        {
            "symbol": "AAPL",
            "name": "Apple",
            "exchange": "NASDAQ",
            "region": "US",
            "popularity": 1000,
            "asset_type": "stock",
            "source": "catalog",
        }
    ],
}


@pytest.fixture(scope="session")
def live_server() -> str:
    env = os.environ.copy()
    env["REDIS_URL"] = ""
    env["APP_ENV"] = "development"
    process = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "-m",
            "uvicorn",
            "backend.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urlopen(f"{BASE_URL}/api/health", timeout=2):
                    break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("live test server did not start")

        yield BASE_URL
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture
def browser() -> object:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser, live_server: str):
    context = browser.new_context(base_url=live_server, service_workers="allow")
    page = context.new_page()
    try:
        yield page, context
    finally:
        context.close()


def _mock_top_assets(page) -> None:
    page.route(
        "**/api/top-assets*",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(TOP_ASSETS)
        ),
    )


def test_submit_success_flow(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION)
        ),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("[data-testid='predict-submit']")

    current_page.wait_for_selector("[data-testid='signal-card']:not([hidden])")
    assert current_page.locator("[data-testid='signal-symbol']").text_content() == "AAPL"
    assert "yfinance / stat" in current_page.locator("[data-testid='source-badge']").text_content()
    assert "Medium" in current_page.locator("[data-testid='confidence-value']").text_content()
    assert current_page.locator("[data-testid='evaluation-row']").is_visible()
    assert current_page.locator("[data-testid='metric-expected']").text_content().strip() != ""
    assert (
        "Probability" not in current_page.locator("[data-testid='confidence-value']").text_content()
    )


def test_submit_failure_clears_stale_results(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    call_count = {"predict": 0}

    def fulfill_predict(route) -> None:
        call_count["predict"] += 1
        if call_count["predict"] == 1:
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION)
            )
            return

        route.fulfill(
            status=502,
            content_type="application/json",
            body=json.dumps(
                {
                    "error": {
                        "code": "provider_unavailable",
                        "message": "Market data provider temporarily unavailable.",
                    }
                }
            ),
        )

    current_page.route("**/api/predict", fulfill_predict)

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("[data-testid='predict-submit']")
    current_page.wait_for_selector("[data-testid='signal-card']:not([hidden])")

    current_page.fill("#symbol", "MSFT")
    current_page.click("[data-testid='predict-submit']")
    current_page.wait_for_function("() => document.getElementById('signal-card').hidden === true")

    assert current_page.locator("[data-testid='signal-card']").is_hidden()
    assert (
        "Market data provider temporarily unavailable."
        in current_page.locator("#status").text_content()
    )


def test_missing_chart_library_shows_friendly_error(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route("**/vendor/chart.umd.min.js", lambda route: route.abort())
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION)
        ),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("[data-testid='predict-submit']")
    current_page.wait_for_selector("[data-testid='chart-fallback']:not([hidden])")

    assert current_page.locator("[data-testid='chart-fallback']").is_visible()
    assert current_page.locator("[data-testid='chart-fallback']").text_content().strip() != ""


def test_fallback_explanation_is_visible_and_honestly_labeled(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(FALLBACK_EXPLANATION_PREDICTION),
        ),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("[data-testid='predict-submit']")

    current_page.wait_for_selector("[data-testid='explanation-card']:not([hidden])")
    assert (
        "Forecast source: Statistical fallback."
        in current_page.locator("[data-testid='explanation-source']").text_content()
    )
    assert (
        "Explanation source: Pattern-difference analysis."
        in current_page.locator("[data-testid='explanation-source']").text_content()
    )
    assert (
        "current market pattern differed"
        in current_page.locator("[data-testid='explanation-note']").text_content()
    )


def test_offline_shell_is_served_from_service_worker(page) -> None:
    current_page, context = page
    _mock_top_assets(current_page)

    current_page.goto("/", wait_until="load")
    current_page.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
    context.set_offline(True)
    current_page.reload(wait_until="domcontentloaded")

    assert current_page.locator("[data-testid='predict-form']").is_visible()
    assert current_page.locator("[data-testid='predict-submit']").is_visible()
