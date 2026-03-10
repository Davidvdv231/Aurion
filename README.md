# Stock Predictor MVP

Cross-platform app (telefoon + pc) als PWA met een Python API die een 1-maands aandelenvoorspelling toont.

## Stack
- Frontend: Vanilla HTML/CSS/JS + Chart.js
- Backend: FastAPI
- Data: yfinance + lokale ticker-catalog + Yahoo trending feed
- Forecast:
  - `stat`: lineaire trend op log-prijzen met 80% band
  - `ai`: optionele backend-hook voor externe stock-AI (niet zichtbaar in UI standaard)

## Snel starten
1. Maak en activeer een virtuele omgeving:
   - `python -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
2. Installeer dependencies:
   - `pip install -r backend/requirements.txt`
3. Start de app:
   - `uvicorn backend.main:app --reload`
4. Open in je browser:
   - `http://127.0.0.1:8000`

## API
- `GET /api/health`
- `GET /api/tickers?query=K&limit=12`
- `GET /api/top-stocks?limit=10`
- `GET /api/predict?symbol=AAPL&horizon=30&engine=stat`
- `GET /api/predict?symbol=INGA&horizon=30&engine=ai`

## AI engine (optioneel, backend-hook)
De UI gebruikt standaard het statistische model. Voor `engine=ai` via API moet je een extern endpoint voorzien dat JSON terugstuurt met een `forecast` lijst.

Environment variabelen:
- `STOCK_LLM_API_URL` (verplicht voor AI mode)
- `STOCK_LLM_API_KEY` (optioneel)

Voorbeeld request dat deze app naar jouw AI endpoint stuurt:
```json
{
  "symbol": "AAPL",
  "horizon_days": 30,
  "history": [
    {"date": "2026-02-01", "close": 187.42}
  ]
}
```

Verwachte response (minimaal):
```json
{
  "provider": "my-provider",
  "model": "my-stock-llm",
  "forecast": [
    {"date": "2026-03-11", "predicted": 190.4, "lower": 183.8, "upper": 197.0}
  ]
}
```

## Belangrijke noot
Geen enkel model (ook AI/LLM niet) kan koersvoorspellingen garanderen. Gebruik dit als indicatie, niet als financieel advies.