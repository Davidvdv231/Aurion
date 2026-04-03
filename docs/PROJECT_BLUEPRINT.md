# AI Forecasting App Blueprint

## Current Status

- Phase 1 credibility fixes are complete.
- P1 is complete: prediction orchestration is extracted from the FastAPI route, the web client has a small response-normalization boundary, and mobile rendering semantics align with the backend contract.
- P1.5 is complete: prediction execution now emits structured start/completion/fallback logs, and service-level branching/fallback tests cover `stat`, `ml`, and compatibility `ai` paths.
- P2 Sprint 1 is complete:
  - OHLCV integrity checks: NaN ratio, gap detection, extreme outlier detection. Series is forward-filled and quality is flagged as `clean`, `patched`, or `degraded` in `PredictionSource`.
  - Feature NaN guard: `compute_features()` now drops the 50-row warm-up window instead of forward-filling undefined indicators, then trims any remaining NaN rows with logging.
  - Staleness detection: if the latest data point is >3 trading days old, `MarketSeries.stale=True` and a warning is included in the response.
  - Timing instrumentation: `market_data_ms`, `model_ms`, and `total_ms` are logged in `prediction.completed`.
  - JSON structured logging: all logs are now emitted as single-line JSON objects for aggregation.
  - Deep health check: `/api/health` now reports Redis status, in-memory cache size, and process uptime.
  - Mobile stabilized: dependencies installed, `@types/react-native` removed (RN 0.74 ships own types), `ConfidenceMeter` `DimensionValue` type fixed. `npm run typecheck` passes clean.
  - Full Python test suite passes: 25/25.
- P2 Sprint 2 is complete:
  - Pattern-difference analysis: analog forecaster now computes top-5 feature differences versus the nearest analog set, plus average neighbor distance and nearest analog date.
  - `PredictionExplanation` model added to response: `top_features`, `neighbors_used`, `avg_neighbor_distance`, `nearest_analog_date`, `narrative`, where each feature exposes `difference_score` and `relation`.
  - Plain-English narrative generator is framed as historical-pattern context, not causal forecast drivers.
  - Web: collapsible "Pattern differences" card with colored horizontal feature bars, narrative text, and nearest analog date. `data-testid="explanation-card"`.
  - Web: Chart.js tooltips enhanced with confidence band range display. Confidence meter now shows only the confidence tier, not a pseudo-probability.
  - Web: skeleton shimmer loader on signal card while prediction is in-flight.
  - Web: `normalizePredictResponse` updated to pass through `source.data_quality`, `source.data_warnings`, `source.stale`, and `explanation`.
  - `/api/metrics` endpoint: returns `predictions_total`, `predictions_by_engine`, `fallbacks_total`, `fallbacks_by_code`, `rate_limit_429_total`, `avg_prediction_ms`, `p95_prediction_ms`.
  - `PredictionMetrics` in-memory counter with thread-safe recording, integrated into prediction service.
  - Full Python test suite passes: 25/25. Mobile typecheck: 0 errors.

## Solution Summary

This project evolves the current stock and crypto predictor into a modular forecasting platform with:

- historical OHLCV ingestion
- technical indicator feature engineering
- ML forecasting with backtesting and honest confidence tiers
- FastAPI prediction serving
- an Expo-based mobile MVP
- Docker-first deployment preparation

The MVP focuses on realistic uncertainty-aware forecasts and trend detection. It does not claim certainty and keeps benchmark and production paths explicitly separated.

## Recommended Architecture

### Backend and Data

- `FastAPI` serves prediction, search, top assets, and health endpoints.
- `yfinance` powers MVP historical OHLCV retrieval.
- `Redis` is used for shared caching and rate limiting when available.
- Local `artifacts/` storage keeps trained model artifacts and raw feature snapshots for development.
- Production target: move metadata to PostgreSQL/Timescale and artifacts to object storage.

### ML Pipeline

- Ingestion normalizes OHLCV time series per asset.
- Feature engineering computes returns, volatility, RSI, MACD, moving averages, Bollinger Bands, and volume features.
- A probabilistic analog/similarity forecaster acts as the default non-linear MVP model.
- Statistical trend remains available only as benchmark and fallback.
- Walk-forward backtesting produces MAE, RMSE, MAPE, and directional accuracy.
- Model artifacts are versioned per asset type, symbol, and horizon.

### API Layer

- `/api/predict` supports `ml`, `stat`, and compatibility `ai` engines.
- Responses include path forecasts plus summary fields such as expected return, trend, confidence, and signal.
- Backtest metrics are exposed so clients can present limitations and model quality.

### Mobile App

- Expo + React Native TypeScript MVP
- splash and guest entry shell
- home dashboard with search and featured assets
- asset detail page with chart and forecast cards
- watchlist with local persistence

### Deployment Path

- Dockerized backend
- Redis for cache and rate limits
- PostgreSQL for metadata and watchlists in production
- scheduled retraining worker
- mobile builds through Expo/EAS for App Store and Google Play

## MVP Priorities

1. Replace the default linear forecast path with a probabilistic ML engine.
2. Preserve the existing FastAPI contract while extending it for confidence and evaluation.
3. Add a mobile MVP without coupling it to the web frontend.
4. Keep the training and inference pipeline modular so stronger models such as XGBoost, GRU, or TFT can be slotted in later.

## Model Strategy

### MVP Default

- Similarity-based probabilistic forecaster on engineered time-series features.
- Reason: no extra heavy dependencies, explainable fallback behavior, fast per-asset training, natural uncertainty bands from neighbor paths.

### Benchmarks and Roadmap

- `stat`: retained as benchmark and degraded fallback only.
- `random_forest` / `xgboost`: recommended next tree-based adapters for tabular time-series features.
- `gru` / `lstm`: useful when sequence modeling infrastructure is ready.
- `temporal_fusion_transformer`: production candidate once a richer feature store and GPU training path are available.
- `prophet`: benchmark only, not the main production forecaster.

## Folder Strategy

- `backend/`: API, services, configuration, forecasting pipeline
- `backend/ml/`: ingestion, features, models, training, evaluation, registry
- `mobile/`: Expo React Native app
- `infra/`: Docker and orchestration assets
- `docs/`: architecture and operating notes
- `artifacts/`: local model and raw data storage for development
