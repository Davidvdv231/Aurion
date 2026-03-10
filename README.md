# Stock Predictor MVP

Cross-platform app (telefoon + pc) als PWA met een Python API die een 1-maands aandelenvoorspelling toont.

## Stack
- Frontend: Vanilla HTML/CSS/JS + Chart.js
- Backend: FastAPI
- Data: yfinance
- Forecast: lineaire trend op log-prijzen met 80% band

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
- `GET /api/predict?symbol=AAPL&horizon=30`

## Belangrijke noot
Deze voorspelling is indicatief en geen financieel advies.
