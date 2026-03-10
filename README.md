# Stock & Crypto Predictor

Cross-platform PWA (telefoon + pc) met FastAPI backend om 1-maands voorspellingen te tonen voor aandelen en crypto.

## Stack
- Frontend: Vanilla HTML/CSS/JS + Chart.js
- Backend: FastAPI
- Data: yfinance + lokale catalog + Yahoo trending + CoinGecko top crypto
- Forecast:
  - `stat`: lineaire trend op log-prijzen met 80% band
  - `ai`: OpenAI (ingebouwd) of custom endpoint fallback

## Snel starten
1. Maak en activeer een virtuele omgeving:
   - `python -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
2. Installeer dependencies:
   - `pip install -r backend/requirements.txt`
3. Start de app:
   - `python backend/main.py`
4. Open:
   - `http://127.0.0.1:8000`

## API
- `GET /api/health`
- `GET /api/tickers?query=K&limit=12&asset_type=stock`
- `GET /api/tickers?query=BTC&limit=12&asset_type=crypto`
- `GET /api/top-stocks?limit=10&asset_type=stock`
- `GET /api/top-stocks?limit=10&asset_type=crypto`
- `GET /api/predict?symbol=AAPL&horizon=30&asset_type=stock&engine=stat`
- `GET /api/predict?symbol=BTC&horizon=30&asset_type=crypto&engine=ai`

## AI configuratie
### OpenAI (standaard ingebouwd)
- `OPENAI_API_KEY` (vereist voor `engine=ai`)
- `OPENAI_MODEL` (optioneel, default: `gpt-5-mini`)

### Custom AI endpoint (optioneel alternatief)
- `STOCK_LLM_API_URL`
- `STOCK_LLM_API_KEY` (optioneel)

Als `engine=ai` niet beschikbaar is, valt de app automatisch terug op `stat`.

## Belangrijke noot
Geen enkel model (ook AI/LLM) kan koersvoorspellingen garanderen. Gebruik dit als indicatie, niet als financieel advies.
## Security & limits
- `CORS_ALLOW_ORIGINS` (optioneel, comma-separated origins voor productie)
- `RATE_LIMIT_WINDOW_SECONDS` (default `60`)
- `RATE_LIMIT_MAX_REQUESTS_STAT` (default `30` per window)
- `RATE_LIMIT_MAX_REQUESTS_AI` (default `8` per window)

