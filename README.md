# Stock & Crypto Predictor

Cross-platform PWA (telefoon + pc) met FastAPI backend om 1-maands voorspellingen te tonen voor aandelen en crypto.

## Stack
- Frontend: Vanilla HTML/CSS/JS + lokale Chart.js bundle
- Backend: FastAPI + Pydantic models
- Data: yfinance + lokale catalog + Yahoo trending + CoinGecko top crypto
- Reliability: Redis-backed rate limiting/cache (met in-memory fallback als Redis niet beschikbaar is)
- Forecast:
  - `stat`: lineaire trend op log-prijzen met 80% band
  - `ai`: OpenAI (ingebouwd) of custom endpoint fallback

## Snel starten
1. Maak en activeer een virtuele omgeving:
   - `python -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
2. Installeer runtime dependencies:
   - `pip install -r backend/requirements.txt`
3. Maak een lokale config:
   - `Copy-Item .env.example .env`
4. Vul in `.env` de keys in die je nodig hebt.
5. Start de app:
   - `python backend/main.py`
6. Open:
   - `http://127.0.0.1:8000`

De app leest nu automatisch `.env` uit de project-root. Gewone shell environment variables blijven voorrang houden op `.env`.

## API
- `GET /api/health`
- `GET /api/tickers?query=K&limit=12&asset_type=stock`
- `GET /api/tickers?query=BTC&limit=12&asset_type=crypto`
- `GET /api/top-assets?limit=10&asset_type=stock`
- `GET /api/top-assets?limit=10&asset_type=crypto`
- `POST /api/predict`

Voorbeeld request:
```json
{
  "symbol": "AAPL",
  "horizon": 30,
  "engine": "stat",
  "asset_type": "stock"
}
```

Belangrijke responsevelden:
- `currency`
- `source.market_data`
- `source.forecast`
- `degraded`
- `degradation_reason`

## AI configuratie
### OpenAI (standaard ingebouwd)
- `OPENAI_API_KEY` (vereist voor `engine=ai`)
- `OPENAI_MODEL` (optioneel, default: `gpt-5-mini`)

### Custom AI endpoint (optioneel alternatief)
- `STOCK_LLM_API_URL`
- `STOCK_LLM_API_KEY` (optioneel)

Als `engine=ai` niet beschikbaar is, valt de app automatisch terug op `stat` en zet de response `degraded=true`.

## Security, limits en proxy-config
- `CORS_ALLOW_ORIGINS` (optioneel, comma-separated origins voor productie)
- `RATE_LIMIT_WINDOW_SECONDS` (default `60`)
- `RATE_LIMIT_MAX_REQUESTS_STAT` (default `30` per window)
- `RATE_LIMIT_MAX_REQUESTS_AI` (default `8` per window)
- `REDIS_URL` (aanbevolen voor gedeelde rate limiting/cache)
- `REDIS_PREFIX` (default `stock-predictor`)
- `TRUSTED_PROXY_IPS` (comma-separated proxy IPs; alleen dan wordt `X-Forwarded-For` vertrouwd)

## Tests
1. Installeer dev dependencies:
   - `pip install -r requirements-dev.txt`
2. Run alles:
   - `pytest -q`

## Belangrijke noot
Geen enkel model (ook AI/LLM) kan koersvoorspellingen garanderen. Gebruik dit als indicatie, niet als financieel advies.
