# Aurion

FastAPI forecasting backend (`backend/`) that also serves a no-build PWA (`frontend/`), plus an Expo client (`mobile/`). `README.md` covers architecture and the API; this file covers what to know before changing code.

## Commands

Run everything from the repo root: the code imports the `backend` package. CI and Docker use Python 3.12. In cloud sessions `.claude/hooks/session-start.sh` creates `.venv`, installs all dependencies and puts the venv on `PATH`.

These mirror `.github/workflows/ci.yml`, and all of them must pass:

```bash
python -m ruff check backend tests
python -m ruff format --check backend tests
python -m mypy backend
python -m pytest tests --ignore=tests/test_frontend_smoke.py --ignore=tests/test_mobile_web_smoke.py -q
python -m pytest tests/test_frontend_smoke.py -q    # Playwright, starts its own server
(cd mobile && npm run typecheck)
python -m pip_audit -r backend/requirements.lock --require-hashes --disable-pip
python -m pip_audit -r requirements-dev.lock --require-hashes --disable-pip
```

The mobile smoke test needs a fresh Expo web export of the current code. Without `MOBILE_WEB_EXPORT_DIR` it skips:

```bash
(cd mobile && EXPO_PUBLIC_API_BASE_URL=http://api.aurion.test npx expo export --platform web --output-dir ../build/mobile-web)
MOBILE_WEB_EXPORT_DIR=build/mobile-web python -m pytest tests/test_mobile_web_smoke.py -q
```

Run the app with `uvicorn backend.app:create_app --factory --reload`. It serves the PWA at http://localhost:8000.

## The prediction contract

The backend, the web client and the mobile client share one `/api/predict` response shape. A change to a field, an enum value or a degradation code has to land in all of these in the same change:

- `backend/models.py`: the Pydantic models are the source of truth (`EngineUsed`, `degradation_code`, ...).
- `backend/services/prediction.py`: where engines are chosen and degradation codes are emitted.
- `frontend/app.js`: `normalizePredictResponse()` turns the raw payload into what the UI renders.
- `mobile/src/api/types.ts`: the TypeScript mirror. Demo payloads in `mobile/src/data/demoAssets.ts` use the same shape.
- `README.md`: the degradation table and example responses document the codes publicly.

## Conventions

- Python dependencies are locked with hashes. Edit `backend/requirements.txt` or `requirements-dev.txt`, then run `make lock`; never edit the `.lock` files by hand. CI fails if the lockfiles are stale.
- Tests never touch the network. Patch `backend.services.market_data.yf.download` as `tests/test_market_data.py` does, and keep the suite passing offline.
- New settings: read them in `backend/config.py`, document them in `.env.example`, and add the name to `APP_ENV_VARS` in `tests/conftest.py` so every test starts from a clean environment. `backend/config.py` also loads a repo-root `.env` if one exists.
- When you change a file listed in `ASSETS` in `frontend/sw.js`, bump `CACHE_VERSION` there so installed PWAs refresh. CI's SHA stamp only applies to its own checkout.
- The frontend is plain JavaScript with no build step or `package.json`. Don't add a bundler or framework unless asked.
- Ruff uses line length 100 with rules E, F, I and B. Mypy checks `backend/` only.

## Ask before running

- `scripts/generate_backtest.py` downloads live market data and overwrites `docs/backtest_results.md`, so its output changes with the market. Only regenerate it when the task is about backtests.
- `make smoke-test` needs a running server, and `scripts/docker_smoke.sh` needs Docker.
