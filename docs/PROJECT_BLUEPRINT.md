# Aurion Project Blueprint

## Current State

Aurion is a portfolio MVP with one production prediction contract shared across the backend, web client, and mobile client. The active system is centered on:

- a FastAPI backend with rate limiting, typed prediction responses, health probes, metrics, and explicit degradation semantics
- a vanilla JS PWA for the full browser experience
- an Expo mobile client for the core forecast and watchlist flow
- honest fallback behavior when the ML path underperforms or live API access is unavailable

The repository does not currently ship a separate `ai` compatibility engine, persisted model registry, or artifact-storage pipeline. Those were earlier ideas and are not part of the live implementation.

## Architecture Reality

### Backend

- `backend/routes/` exposes prediction, search, top-assets, health, readiness, metrics, and validation-summary endpoints.
- `backend/services/prediction.py` orchestrates market data retrieval, statistical forecasts, ML forecasts, quality gates, currency conversion, and response shaping.
- `backend/services/cache.py` and `backend/services/rate_limit.py` provide dual-layer caching and Redis-backed or in-memory rate limiting.
- `backend/services/metrics.py` keeps lightweight in-memory counters with Prometheus exposition.

### Frontend

- `frontend/` is a no-build PWA.
- The browser client normalizes the backend response, renders charts and explanation details, and keeps local theme/watchlist preferences.

### Mobile

- `mobile/` is an Expo TypeScript client.
- The app is API-first and only uses demo data as an explicitly labeled fallback.
- Non-local builds require `EXPO_PUBLIC_API_BASE_URL` to be configured.
- The asset detail view now includes a lightweight native chart for recent history and forecast bands.

## Product Constraints

- Market data is sourced from `yfinance`, which is sufficient for an MVP but not a premium production feed.
- The ML engine is a k-NN analog forecaster with quality gates, not a long-running training platform.
- There is no user authentication, account system, or persistent backend database.

## Near-Term Priorities

1. Deepen mobile and frontend verification beyond type/smoke coverage.
2. Improve model validation depth across more volatile assets and horizons.
3. Add stronger deployment documentation for Docker and Kubernetes environments.
4. Decide whether a persisted model/artifact pipeline is actually required before reintroducing that complexity.
