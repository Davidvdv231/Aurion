from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = ROOT / ".venv" / "Scripts" / "python.exe"
EDGE_EXE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
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
    "engine_note": "Statistische trend op historische koersdata.",
    "source": {"market_data": "yfinance", "forecast": "stat"},
    "degraded": False,
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
    "disclaimer": "Dit is een statistische/AI schatting en geen financieel advies.",
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
    process = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8765"],
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
        browser = playwright.chromium.launch(executable_path=str(EDGE_EXE), headless=True)
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
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(TOP_ASSETS)),
    )


def test_submit_success_flow(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION)),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("#submit-btn")

    current_page.wait_for_selector("#stats-card:not([hidden])")
    last_close = current_page.locator("#last-close").text_content()
    assert "102,25" in last_close
    assert "US$" in last_close
    assert "yfinance / stat" in current_page.locator("#source-badge").text_content()


def test_submit_failure_clears_stale_results(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    call_count = {"predict": 0}

    def fulfill_predict(route) -> None:
        call_count["predict"] += 1
        if call_count["predict"] == 1:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION))
            return

        route.fulfill(
            status=502,
            content_type="application/json",
            body=json.dumps({"error": {"code": "provider_unavailable", "message": "Marktdataprovider tijdelijk niet bereikbaar."}}),
        )

    current_page.route("**/api/predict", fulfill_predict)

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("#submit-btn")
    current_page.wait_for_selector("#stats-card:not([hidden])")

    current_page.fill("#symbol", "MSFT")
    current_page.click("#submit-btn")
    current_page.wait_for_timeout(300)

    assert current_page.locator("#stats-card").is_hidden()
    assert "Marktdataprovider tijdelijk niet bereikbaar." in current_page.locator("#status").text_content()


def test_missing_chart_library_shows_friendly_error(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route("**/vendor/chart.umd.min.js", lambda route: route.abort())
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION)),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("#submit-btn")
    current_page.wait_for_timeout(300)

    assert current_page.locator("#chart-fallback").is_visible()
    assert "Grafiekbibliotheek" in current_page.locator("#chart-fallback").text_content()


def test_offline_shell_is_served_from_service_worker(page) -> None:
    current_page, context = page
    _mock_top_assets(current_page)

    current_page.goto("/", wait_until="load")
    current_page.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
    context.set_offline(True)
    current_page.reload(wait_until="domcontentloaded")

    assert current_page.locator("h1").text_content() == "Stock & Crypto Predictor"
