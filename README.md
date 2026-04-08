# Aurion

> Market forecasting that tells you when it doesn't know.

[![CI](https://github.com/Davidvdv231/Aurion/actions/workflows/ci.yml/badge.svg)](https://github.com/Davidvdv231/Aurion/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![License: MIT](https://img.shields.io/badge/license-MIT-blue)

Aurion is a multi-engine market forecasting system that combines statistical baselines and ML pattern matching with explicit quality gating and transparent degradation. When a model underperforms its benchmark, the system falls back honestly and tells you why. Built for trust under imperfect conditions, not prediction theater.

### Why this matters

Most forecasting tools either silently serve bad predictions or fail without explanation. Aurion takes a different approach: every prediction passes through a quality gate that checks directional accuracy, error margins, and validation depth. If the ML model can't beat a simple statistical baseline, the system says so explicitly — with a degradation code, a human-readable reason, and a fallback forecast. This makes the output trustworthy by default, not by assumption.

### Highlights

- **Multi-engine forecasting** — statistical baseline and k-NN analog pattern matching, with automatic engine selection
- **Quality gating with transparent fallback** — ML predictions are validated against baselines; failures degrade honestly with specific codes
- **Currency conversion** — server-side forex via yfinance, supporting 7 currencies with 1-hour cache
- **Observability** — structured JSON logging, Prometheus metrics, request tracing, and health/readiness probes

## Screenshots

**Statistical forecast with chart and signal card:**

![Desktop forecast](docs/screenshots/aurion-desktop-forecast.png)

**ML prediction with quality gate fallback and pattern explanation:**

![ML prediction with degradation](docs/screenshots/aurion-ml-prediction.png)

**Responsive mobile layout:**

![Mobile view](docs/screenshots/aurion-mobile-forecast.png)

## Architecture

```mermaid
flowchart TD
    Client["Client (PWA / Mobile)"] --> API["FastAPI Gateway"]
    API --> RL["Rate Limiter (Redis / In-Memory)"]
    RL --> PO["Prediction Orchestrator"]
    PO --> MD["Market Data Service"]
    MD --> Cache["Dual-Layer Cache (Memory + Redis)"]

    PO --> |"engine=stat"| STAT["Statistical Baseline"]
    PO --> |"engine=ml"| ML["ML Analog Forecaster (k-NN)"]

    ML --> QG{"Quality Gate"}
    QG --> |"passes"| RES["Response with engine_used"]
    QG --> |"fails"| FB["Fallback to Statistical"]
    FB --> DEG["Response with degraded=true + degradation_code"]
    STAT --> RES

    style QG fill:#f59e0b,stroke:#d97706,color:#000
    style FB fill:#ef4444,stroke:#dc2626,color:#fff
    style DEG fill:#ef4444,stroke:#dc2626,color:#fff
    style RES fill:#22c55e,stroke:#16a34a,color:#fff
```

## Design Decisions

| Decision | Choice | Trade-off |
|----------|--------|-----------|
| Forecasting approach | Multi-engine with quality gating | More complex orchestration, but honest about prediction quality |
| ML model | k-NN analog pattern matching | Simple and interpretable, but limited expressiveness vs. deep learning |
| Frontend framework | Vanilla JS PWA | Zero build step, instant deployment, but no component reuse |
| Rate limiting | Redis-backed with Lua atomic ops | Fail-closed in production (Redis failure = 503), fail-open in development (no limiting) |
| Caching | Dual-layer (memory + Redis) | Fast reads with persistence, but cache invalidation complexity |
| Currency conversion | Server-side via yfinance forex pairs | Real-time rates with 1-hour cache, supports USD/EUR/GBP/JPY/CHF/CAD/AUD |
| Request tracing | Request-ID middleware with sanitization | Every request gets a traceable ID in logs and response headers |

## Prediction Engine & Degradation

| Condition | Engine Used | Degraded | Code |
|-----------|------------|----------|------|
| Stat engine requested | `stat` | `false` | — |
| ML requested, quality passes | `ml` | `false` | — |
| ML requested, validation windows < 3 | `stat_fallback` | `true` | `model_validation_insufficient` |
| ML requested, directional accuracy < 0.45 | `stat_fallback` | `true` | `model_quality_insufficient` |
| ML requested, MAPE > baseline MAPE | `stat_fallback` | `true` | `model_baseline_underperforming` |
| ML requested, training timeout (>15s) | `stat_fallback` | `true` | `ml_engine_timeout` |
| ML requested, exception during training | `stat_fallback` | `true` | `ml_engine_unavailable` |

## Example API Responses

**Clean ML prediction:**

```json
{
  "symbol": "AAPL",
  "asset_type": "stock",
  "currency": "USD",
  "native_currency": "USD",
  "display_currency": "USD",
  "engine_requested": "ml",
  "engine_used": "ml",
  "model_name": "Aurion Analog Forecaster",
  "degraded": false,
  "degradation_code": null,
  "degradation_message": null,
  "summary": {
    "expected_price": 198.45,
    "expected_return_pct": 2.3,
    "trend": "bullish",
    "confidence_tier": "medium",
    "signal": "Bullish Outlook"
  },
  "evaluation": {
    "mae": 3.21,
    "rmse": 4.15,
    "mape": 1.8,
    "directional_accuracy": 0.62,
    "validation_windows": 5
  },
  "forecast": [
    {"date": "2026-04-07", "predicted": 194.82, "lower": 191.20, "upper": 198.44}
  ]
}
```

**Degraded ML to stat fallback:**

```json
{
  "symbol": "GME",
  "asset_type": "stock",
  "engine_requested": "ml",
  "engine_used": "stat_fallback",
  "degraded": true,
  "degradation_code": "model_quality_insufficient",
  "degradation_message": "ML directional accuracy (0.38) below threshold (0.45); using statistical fallback.",
  "summary": {
    "expected_price": 27.15,
    "expected_return_pct": -1.2,
    "trend": "bearish",
    "confidence_tier": "low",
    "signal": "Bearish Outlook"
  },
  "evaluation": {
    "mae": 1.85,
    "rmse": 2.34,
    "mape": 6.8,
    "directional_accuracy": null,
    "validation_windows": null
  },
  "forecast": [
    {"date": "2026-04-07", "predicted": 27.42, "lower": 25.80, "upper": 29.04}
  ]
}
```

**Clean statistical baseline:**

```json
{
  "symbol": "BTC-USD",
  "asset_type": "crypto",
  "engine_requested": "stat",
  "engine_used": "stat",
  "degraded": false,
  "degradation_code": null,
  "summary": {
    "expected_price": 84250.00,
    "expected_return_pct": 1.8,
    "trend": "bullish",
    "confidence_tier": "medium",
    "signal": "Bullish Outlook"
  },
  "evaluation": null
}
```

## API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Liveness check — status, Redis health, cache size, uptime |
| `/api/health/ready` | GET | Readiness check — returns 503 when required internal dependencies are unavailable and reports runtime import checks |
| `/api/metrics` | GET | Prediction metrics snapshot (protected by `METRICS_TOKEN` when set) |
| `/api/tickers` | GET | Search tickers by query (1-50 results) |
| `/api/top-assets` | GET | Trending assets by type, cached 15 min |
| `/api/metrics/prometheus` | GET | Prometheus exposition format (protected by `METRICS_TOKEN` when set) |
| `/api/validation-summary` | GET | ML quality-gate thresholds and latest evaluation (protected) |
| `/api/predict` | POST | Multi-engine prediction with quality gating and degradation |

## Quick Start

```bash
# Clone and start
git clone https://github.com/Davidvdv231/Aurion.git
cd Aurion

# Run with Docker (includes Redis)
docker-compose -f infra/docker-compose.yml up --build

# Verify
curl http://localhost:8000/api/health

# Get a prediction (prices in USD)
curl -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "asset_type": "stock", "engine": "stat", "horizon": 30}'

# Get a prediction with currency conversion
curl -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "asset_type": "stock", "engine": "ml", "horizon": 30, "display_currency": "EUR"}'
```

For local development without Docker:

```bash
cd backend
pip install -r requirements.txt
uvicorn app:create_app --factory --reload
```

For mobile development outside local Expo/device testing, set `EXPO_PUBLIC_API_BASE_URL` so the app can reach the deployed API. The mobile client only falls back to explicit demo data in development or when the live API is unavailable.

## Testing

```bash
# Run the backend and integration suite
python -m pytest tests -q

# Run with coverage
python -m pytest tests --cov=backend --cov-report=term-missing -q

# Type checking
python -m mypy backend

# Linting
python -m ruff check backend tests

# Formatting
python -m ruff format --check backend tests

# Mobile type checking
cd mobile && npm run typecheck

# Frontend smoke test (requires Playwright browser install once)
python -m playwright install --with-deps chromium
python -m pytest tests/test_frontend_smoke.py -q
```

The test suite covers API contracts, prediction orchestration, ML pipeline behavior, rate limiting, exchange rates, config, smoke integration, and a browser-based frontend smoke path. CI also gates the Expo mobile client with `npm run typecheck`.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI 0.115 / Python 3.12 | Async API with validation |
| ML | NumPy / pandas | k-NN analog pattern forecaster |
| Cache | Redis 7 + in-memory TTL | Dual-layer with configurable TTLs |
| Web | Vanilla JS PWA | Zero-dependency frontend with service worker |
| Mobile | React Native / Expo 54 | Cross-platform mobile client |
| Market Data | yfinance | Historical market data and FX rate retrieval |
| CI/CD | GitHub Actions | Lint, type check, test, audit |
| Deploy | Docker + Docker Compose | Containerized with health checks |

## Known Limitations

- **ML model is k-NN analog** — simple by design, not a deep learning system. Effective for pattern matching, limited for complex market dynamics.
- **Market data via yfinance** — free and functional, but not a production-grade feed. Rate limits and data gaps may occur.
- **No persistent storage** — models and cache reset on container restart. No user database.
- **No user authentication** — stateless API, no multi-tenancy or user sessions. Operational endpoints (`/api/metrics`, `/api/validation-summary`) can be protected via the `METRICS_TOKEN` env var.
- **Mobile charting is lightweight** — the mobile app now renders a native forecast/history chart, but it is still less feature-rich than the web charting experience.
- **Mobile fallback mode is demo-only** — when the live API is unavailable, the app now labels demo data explicitly instead of pretending it is live.
- **Single-process deployment** — no horizontal scaling or distributed training.

## Engineering Trade-offs

- **Vanilla JS PWA over React/Vue** — zero build step means instant deployment and no framework churn, at the cost of no component reuse or state management.
- **k-NN analog over deep learning** — interpretable, fast to train on-demand, and honest about its limitations. Deep learning would need a training pipeline, GPU infra, and would be harder to explain.
- **In-memory metrics with Prometheus export** — lightweight counters with a `/api/metrics/prometheus` endpoint for external scraping. No full Prometheus client dependency.
- **Statistical fallback always available** — guarantees every request gets a response, but the stat forecast is basic (log-linear regression + volatility bands).
- **Fail-closed rate limiting in production** — one Redis failure means 503 for everyone, but prevents abuse. Development mode is fail-open.
- **Thread pool for blocking tasks** — avoids blocking the async event loop, but adds concurrency limits (8 workers default).

## Project Status

Aurion is a solo-built MVP. The prediction orchestration, degradation semantics, currency conversion, and web PWA are production-minded — designed with real deployment patterns (rate limiting, health probes, structured logging, security headers) but scoped as a portfolio-grade MVP, not a scaled production system. The ML model is functional but would still benefit from deeper validation on more volatile assets. The mobile app (React Native/Expo) covers the core prediction flow, watchlist, currency selection, explicit degradation handling, and a native chart view, but it still does not have full feature parity with the web client and there is no offline-first sync.

**Current focus:** hardening cross-stack consistency — keeping backend, web, mobile, CI, and docs aligned around one honest prediction contract.

## License

MIT
