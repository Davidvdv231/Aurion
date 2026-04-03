# AI Stock & Crypto Forecasting Platform

Een production-minded MVP voor een schaalbare forecasting app voor aandelen en crypto. De huidige codebasis bevat:

- een `FastAPI` backend met zoek-, top-assets- en predict-endpoints
- een modulaire ML-pipeline op historische OHLCV-data
- probabilistic forecasts with confidence bands, tiered confidence labels and backtest metrics
- een bestaande web/PWA-shell
- een nieuwe Expo/React Native mobiele MVP in `mobile/`
- Docker- en artifact-structuur als basis voor verdere productie-uitrol

## Korte samenvatting

De hoofdengine is niet langer een simpele lineaire voorspeller. De MVP gebruikt een niet-lineaire analog forecaster die vergelijkbare historische marktpatronen zoekt op basis van technische indicatoren en daaruit een dagelijkse forecast path afleidt. De statistische trendlijn blijft bestaan als benchmark en fallback.

De applicatie claimt geen marktzekerheid. Elke forecast is probabilistisch, bevat onzekerheidsbanden en wordt gekoppeld aan evaluatiemetrics.

## Aanbevolen architectuur

### Backend

- `FastAPI` als API-laag
- servicegrenzen voor market data, caching, rate limiting en forecasting
- compatibiliteit met bestaande webclient

### Data-opslag

- MVP: lokale `artifacts/` voor modelversies en ruwe snapshots
- cache: Redis when available, otherwise in-memory fallback
- rate limiting: Redis-backed in production, in-memory fallback only in non-production
- productierichting: PostgreSQL of TimescaleDB voor metadata, gebruikersdata en prediction snapshots

### ML-pipeline

- ingestie van OHLCV via `yfinance`
- feature engineering voor returns, volatility, RSI, MACD, moving averages en Bollinger Bands
- supervised dataset construction voor horizon-based forecasting
- walk-forward validation en rolling backtesting
- model registry met versiebeheer per artifact

### API

- `GET /api/health`
- `GET /api/tickers`
- `GET /api/top-assets`
- `POST /api/predict`

### Mobiele app

- Expo + React Native TypeScript
- splash/guest flow
- home/dashboard
- asset detail met forecast cards en confidence indicator
- watchlist met lokale opslag

### Deployment

- `backend/Dockerfile`
- `infra/docker-compose.yml` met API, Redis en PostgreSQL
- duidelijke scheiding tussen training, validatie en online inference

## Tech stack

### Geïmplementeerd in deze MVP

- Python
- FastAPI
- Pandas / NumPy
- yfinance
- Redis fallback cache/rate limiting
- Expo / React Native TypeScript
- Docker

### Productieroadmap

- PostgreSQL / TimescaleDB
- object storage voor model artifacts
- scheduled retraining worker
- XGBoost/LightGBM adapters
- GRU/LSTM/TFT experimenttracking

## Modelaanpak

### Huidige hoofdmodel

- `Analog Pattern Forecaster`
- niet-lineair
- werkt op genormaliseerde feature-windows
- kiest vergelijkbare historische marktsituaties
- maakt dagelijkse padvoorspellingen met lower/upper bands via gewogen kwantielen

### Benchmark / fallback

- `stat` engine: log-lineaire trendbenchmark
- gebruikt voor vergelijking en degraded fallback wanneer ML niet bruikbaar is

### Metrics

- MAE
- RMSE
- MAPE
- directional accuracy
- rolling walk-forward folds

## Projectstructuur

```text
backend/
  app.py
  main.py
  config.py
  models.py
  routes/
  services/
  ml/
    features.py
    dataset.py
    model.py
    registry.py
    service.py
frontend/
  index.html
  app.js
  styles.css
mobile/
  App.tsx
  src/
  README.md
infra/
  docker-compose.yml
docs/
  PROJECT_BLUEPRINT.md
artifacts/
  data/
  models/
tests/
```

## Belangrijkste output van `/api/predict`

- `forecast`: dagelijkse voorspelde prijzen met `lower` en `upper`
- `stats`: laatste koers en dagelijkse trend
- `summary`:
  - expected price
  - expected return %
  - bullish / bearish / neutral
  - confidence tier
  - buy / hold / sell als model-output, niet als advies
- `evaluation`:
  - MAE
  - RMSE
  - MAPE
  - directional accuracy
  - validation windows
- `model_version`

## Lokale start

### Backend

1. Maak een venv:
   - `python -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
2. Installeer dependencies:
   - `pip install -r backend/requirements.txt`
3. Maak config:
   - `Copy-Item .env.example .env`
4. Start de API:
   - `python backend/main.py`

### Mobiele app

Zie `mobile/README.md`.

## Tests

- Gerichte backendtests:
  - `.\.venv\Scripts\python.exe -m pytest tests\test_api.py tests\test_config.py tests\test_forecast.py tests\test_market_data.py tests\test_ml_pipeline.py -q`
- Volledige suite:
  - `.\.venv\Scripts\python.exe -m pytest -q`

## Configuratie

Belangrijke `.env` keys:

- `REDIS_URL`
- `ARTIFACTS_ROOT`
- `ML_NEIGHBOR_COUNT`
- `ML_BACKTEST_WINDOWS`
- `ML_MIN_HISTORY_ROWS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_MAX_REQUESTS_STAT`
- `RATE_LIMIT_MAX_REQUESTS_AI`
- `RATE_LIMIT_MAX_REQUESTS_SEARCH`
- `RATE_LIMIT_FAIL_OPEN` (`true` by default in development for local fallback; production stays fail-closed when Redis is unavailable)
- `APP_ENV`

## Beperkingen van de MVP

- Databron is nog `yfinance`; voor publieke release is een productiefeed aanbevolen.
- Model is per-asset en on-demand trainbaar; scheduled retraining en central artifact promotion zijn logische volgende stappen.
- De mobiele app is scaffolded maar niet in deze workspace geïnstalleerd of lokaal gestart.

## Volgende uitbreidingen

1. Voeg geplande retraining en modelpromotie toe.
2. Introduceer meerdere modeladapters en model selection per asset/horizon.
3. Verplaats metadata en gebruikersdata naar PostgreSQL.
4. Voeg echte auth, pushnotificaties en portfolio/watchlist sync toe in de mobiele app.
5. Bereid store release pipelines voor via Expo EAS of native CI/CD.
