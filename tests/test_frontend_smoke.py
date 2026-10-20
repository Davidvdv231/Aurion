from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = os.environ.get("PYTHON", sys.executable)
# Optional override for environments whose pre-installed Chromium doesn't match
# the pinned Playwright release (e.g. Claude Code cloud sessions).
CHROMIUM_EXECUTABLE = os.environ.get("AURION_CHROMIUM_EXECUTABLE") or None
BASE_URL = "http://127.0.0.1:8765"

SUCCESS_PREDICTION = {
    "symbol": "AAPL",
    "requested_symbol": "AAPL",
    "asset_type": "stock",
    "currency": "USD",
    "native_currency": "USD",
    "display_currency": "USD",
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
        "no_change_mape": 1.4,
        "beats_no_change": True,
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
            PYTHON_EXE,
            "-m",
            "uvicorn",
            "browser_server:app",
            "--app-dir",
            str(ROOT / "tests"),
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
        # Cold-starting uvicorn in a subprocess can take 15–25s on slow or
        # contended machines (pandas/yfinance import). 60s is the generous
        # ceiling we're willing to wait before declaring a real failure; the
        # previous 30s used to race-lose on Windows.
        deadline = time.time() + 60
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
        browser = playwright.chromium.launch(headless=True, executable_path=CHROMIUM_EXECUTABLE)
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
    assert current_page.locator("[data-testid='eval-beats']").text_content() == "Yes"
    assert current_page.locator("[data-testid='eval-note']").is_hidden()
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


def test_forecast_without_history_keeps_the_forecast_and_skips_the_chart(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({**SUCCESS_PREDICTION, "history": []}),
        ),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("[data-testid='predict-submit']")
    current_page.wait_for_selector("[data-testid='signal-card']:not([hidden])")

    expect(current_page.locator("[data-testid='chart-fallback']")).to_contain_text(
        "No price history"
    )
    assert current_page.locator("#forecast-table-body tr").count() == len(
        SUCCESS_PREDICTION["forecast"]
    )


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


def test_ml_forecast_explanation_has_no_fallback_note(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    ml_prediction = {
        **FALLBACK_EXPLANATION_PREDICTION,
        "engine_used": "ml",
        "model_name": "ML Analog",
        "source": {
            **FALLBACK_EXPLANATION_PREDICTION["source"],
            "forecast": "ml_analog",
        },
        "degraded": False,
        "degradation_code": None,
        "degradation_message": None,
        "degradation_reason": None,
    }
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(ml_prediction)
        ),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("[data-testid='predict-submit']")

    current_page.wait_for_selector("[data-testid='explanation-card']:not([hidden])")
    assert (
        "Forecast source: ML analog."
        in current_page.locator("[data-testid='explanation-source']").text_content()
    )
    assert current_page.locator("[data-testid='explanation-note']").is_hidden()


def test_forecast_that_misses_no_change_is_flagged(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    prediction = {
        **SUCCESS_PREDICTION,
        "evaluation": {
            **SUCCESS_PREDICTION["evaluation"],
            "mape": 3.1,
            "no_change_mape": 2.6,
            "beats_no_change": False,
        },
    }
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(prediction)
        ),
    )

    current_page.goto("/", wait_until="domcontentloaded")
    current_page.click("[data-testid='predict-submit']")

    current_page.wait_for_selector("[data-testid='evaluation-row']:not([hidden])")
    assert current_page.locator("[data-testid='eval-beats']").text_content() == "No"
    assert current_page.locator("#eval-no-change").text_content() == "2.60%"
    assert current_page.locator("[data-testid='eval-note']").is_visible()


def test_offline_shell_is_served_from_service_worker(page) -> None:
    current_page, context = page
    _mock_top_assets(current_page)

    current_page.goto("/", wait_until="load")
    current_page.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
    context.set_offline(True)
    current_page.reload(wait_until="domcontentloaded")

    assert current_page.locator("[data-testid='predict-form']").is_visible()
    assert current_page.locator("[data-testid='predict-submit']").is_visible()


def test_switching_to_crypto_defaults_to_statistical_engine(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    sent: list[dict] = []

    def fulfill_predict(route) -> None:
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION)
        )

    current_page.route("**/api/predict", fulfill_predict)
    current_page.goto("/", wait_until="domcontentloaded")

    current_page.click("#asset-type-control .seg-btn[data-value='crypto']")
    assert current_page.locator("#engine").input_value() == "stat"
    assert (
        current_page.locator("#engine-control .seg-btn[data-value='stat']").get_attribute(
            "aria-pressed"
        )
        == "true"
    )

    current_page.click("[data-testid='predict-submit']")
    current_page.wait_for_selector("[data-testid='signal-card']:not([hidden])")
    assert sent[-1]["asset_type"] == "crypto"
    assert sent[-1]["engine"] == "stat"

    current_page.click("#asset-type-control .seg-btn[data-value='stock']")
    assert current_page.locator("#engine").input_value() == "ml"


def test_suggestions_stay_closed_after_a_quick_submit(page) -> None:
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route(
        "**/api/tickers*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "query": "AAPL",
                    "asset_type": "stock",
                    "tickers": [
                        {
                            "symbol": "AAPL",
                            "name": "Apple",
                            "exchange": "NASDAQ",
                            "region": "US",
                            "popularity": 900,
                            "asset_type": "stock",
                            "source": "catalog",
                        }
                    ],
                }
            ),
        ),
    )
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(SUCCESS_PREDICTION)
        ),
    )
    # Fake timers, so the suggestion lookup that typing queues fires only after the submit.
    current_page.clock.install()
    current_page.goto("/", wait_until="domcontentloaded")

    current_page.fill("#symbol", "AAPL")
    current_page.click("[data-testid='predict-submit']")
    current_page.wait_for_selector("[data-testid='signal-card']:not([hidden])")
    current_page.clock.run_for(1000)
    current_page.wait_for_timeout(500)

    assert current_page.locator("#ticker-suggestions").is_hidden()


@pytest.mark.parametrize("stored", ["{}", '[null,{"symbol":"AAPL"}]', '"wrong"'])
def test_corrupt_preferences_do_not_break_app(page, stored):
    current_page, _ = page
    _mock_top_assets(current_page)
    errors = []
    current_page.on("pageerror", lambda error: errors.append(str(error)))
    current_page.add_init_script(
        f"localStorage.setItem('aurion-watchlist', {json.dumps(stored)}); localStorage.setItem('aurion-currency', '\"invalid');"
    )
    current_page.goto("/", wait_until="load")
    expect(current_page.locator("#top-assets .chip-btn")).to_have_count(1)
    assert not errors


def test_unavailable_storage_keeps_core_flow_working(page):
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.add_init_script(
        "Storage.prototype.getItem = () => { throw new Error('blocked'); }; Storage.prototype.setItem = () => { throw new Error('quota'); };"
    )
    current_page.route("**/api/predict", lambda route: route.fulfill(json=SUCCESS_PREDICTION))
    current_page.goto("/", wait_until="load")
    current_page.click("#theme-toggle")
    current_page.click("#submit-btn")
    expect(current_page.locator("#signal-symbol")).to_have_text("AAPL")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {
            **SUCCESS_PREDICTION,
            "forecast": [{"date": "2026-01-06", "predicted": None, "lower": 1, "upper": 2}],
        },
    ],
)
def test_invalid_success_payload_is_reported_without_fabricated_forecast(page, payload):
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route(
        "**/api/predict",
        lambda route: route.fulfill(content_type="application/json", body=json.dumps(payload)),
    )
    current_page.goto("/")
    current_page.click("#submit-btn")
    expect(current_page.locator("#status")).to_contain_text("invalid forecast", ignore_case=True)
    expect(current_page.locator("#signal-card")).to_be_hidden()


def test_market_change_cancels_pending_prediction(page):
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.route("**/api/predict", lambda route: route.fulfill(json=SUCCESS_PREDICTION))
    current_page.goto("/")
    # Delay delivery without relying on server timing or browser request cancellation.
    current_page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (url, init) => {
        const response = await original(url, init);
        if (url === '/api/predict') await new Promise(resolve => { window.releasePrediction = resolve; });
        return response;
      };
    }""")
    current_page.click("#submit-btn")
    current_page.wait_for_function("typeof window.releasePrediction === 'function'")
    current_page.click("#asset-type-control [data-value='crypto']")
    current_page.evaluate("window.releasePrediction()")
    expect(current_page.locator("#submit-btn")).to_be_enabled()
    expect(current_page.locator("#signal-card")).to_be_hidden()
    expect(current_page.locator("#symbol")).to_have_value("BTC")


def test_watchlist_remove_is_keyboard_accessible(page):
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.add_init_script(
        "localStorage.setItem('aurion-watchlist', JSON.stringify([{symbol:'AAPL',asset_type:'stock'}]));"
    )
    current_page.goto("/")
    remove = current_page.get_by_role("button", name="Remove AAPL stock from watchlist", exact=True)
    remove.focus()
    current_page.keyboard.press("Enter")
    expect(current_page.locator("#watchlist-items")).to_contain_text("Nothing saved yet")


def test_data_quality_warnings_are_visible_on_mobile(page):
    current_page, _ = page
    current_page.set_viewport_size({"width": 360, "height": 800})
    _mock_top_assets(current_page)
    prediction = {
        **SUCCESS_PREDICTION,
        "source": {
            **SUCCESS_PREDICTION["source"],
            "stale": True,
            "data_warnings": ["Currency conversion unavailable; prices shown in USD."],
        },
    }
    current_page.route("**/api/predict", lambda route: route.fulfill(json=prediction))
    current_page.goto("/")
    current_page.click("#submit-btn")
    expect(current_page.locator("#data-warnings")).to_contain_text(
        "Currency conversion unavailable"
    )
    expect(current_page.locator("#data-warnings")).to_contain_text("stale")
    assert current_page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("market", ["stock", "crypto"])
def test_real_api_to_browser_forecast(page, market):
    current_page, _ = page
    current_page.goto("/", wait_until="load")
    current_page.click(f"#asset-type-control [data-value='{market}']")
    current_page.click("#engine-control [data-value='stat']")
    current_page.click("#submit-btn")
    expect(current_page.locator("#signal-symbol")).to_have_text(
        "BTC" if market == "crypto" else "AAPL"
    )
    expect(current_page.locator("#source-badge")).to_contain_text("cache:test-fixture / stat")
    expect(current_page.locator("#stock-chart")).to_be_visible()
    assert current_page.locator("#metric-price").text_content() != "$0.00"
    if market == "stock":
        output = ROOT / ".tmp"
        output.mkdir(exist_ok=True)
        current_page.screenshot(path=str(output / "audit-desktop.png"), full_page=True)
        current_page.set_viewport_size({"width": 360, "height": 800})
        # The chart canvas shrinks on its next resize callback, not synchronously.
        current_page.wait_for_function(
            "document.documentElement.scrollWidth <= innerWidth", timeout=5000
        )
        current_page.screenshot(path=str(output / "audit-mobile.png"), full_page=True)


def test_service_worker_preserves_other_app_caches(page):
    current_page, _ = page
    current_page.goto("/", wait_until="load")
    current_page.evaluate(
        "() => navigator.serviceWorker.ready.then(() => caches.open('another-app-v1'))"
    )
    current_page.evaluate("""async () => {
        const registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.map(registration => registration.unregister()));
        await navigator.serviceWorker.register('/sw.js?test-activation');
        await navigator.serviceWorker.ready;
    }""")
    assert current_page.evaluate("() => caches.has('another-app-v1')")


# A first visit (no controller at load) that later finds a waiting update. A fake
# service-worker container lets the test fire controllerchange on demand.
FAKE_FIRST_VISIT_WITH_WAITING_UPDATE = """
(() => {
  const listeners = [];
  const worker = { postMessage: (message) => { window.__swMessages.push(message.type); } };
  window.__swMessages = [];
  window.__fireControllerChange = () => listeners.forEach((listener) => listener());
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      controller: null,
      register: () => Promise.resolve({ waiting: worker, installing: null, addEventListener() {} }),
      addEventListener: (type, listener) => { if (type === "controllerchange") listeners.push(listener); },
    },
  });
})();
"""


def test_update_accepted_during_a_first_visit_reloads_the_page(page):
    current_page, _ = page
    _mock_top_assets(current_page)
    current_page.add_init_script(FAKE_FIRST_VISIT_WITH_WAITING_UPDATE)
    current_page.goto("/", wait_until="load")
    expect(current_page.locator("#sw-update-banner")).to_be_visible()

    # The first install claiming the page is expected and must not reload it.
    current_page.evaluate("window.__stayedOnPage = true; window.__fireControllerChange()")
    current_page.wait_for_timeout(300)
    assert current_page.evaluate("window.__stayedOnPage === true")

    current_page.click("#sw-update-reload")
    assert current_page.evaluate("window.__swMessages") == ["SKIP_WAITING"]
    with current_page.expect_navigation():
        current_page.evaluate("window.__fireControllerChange()")
