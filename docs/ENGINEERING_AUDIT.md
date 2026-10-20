# Aurion engineering audit and improvements

Date: 2026-09-08. Scope: local source changes and validation; no deployment, production writes, account changes or database migration.

## Port onto main (2026-10-20)

This work stayed uncommitted in a local checkout while 39 commits landed on `main` (web and mobile redesigns, Expo SDK 58, hash-locked Python dependencies, forecast-accuracy changes). It was ported onto `main` on 2026-10-20. Where `main` had redesigned a surface, its design was kept and the behavior fixes in this document were re-applied to it:

- The Expo 54 dependency bumps were dropped in favor of `main`'s Expo SDK 58 lockfile. `ForecastCard.tsx` (removed on `main`) and the duplicate `mobile/src/api/format.ts` are gone; sub-cent price formatting now lives in `mobile/src/utils/format.ts`, and the chart's y-padding no longer has an absolute one-cent floor.
- `main` had started running the 5-fold statistical backtest on the event loop for every request. It now runs through the bounded worker. A timeout serves the forecast without an evaluation, and an ML request then falls back with `ml_engine_timeout`.
- `main`'s new MAE/RMSE fields keep full precision instead of four decimals, and the no-change baseline uses the same unfloored denominator as MAPE. The web backtest panel formats MAE as a price.
- Days without a close (routine provider gaps) mark data `patched`; only non-positive, infinite or duplicate observations mark it `degraded`.
- Web: the redesign's toggle buttons keep `aria-pressed`. Combobox/listbox ARIA, visible data warnings, the update banner, request invalidation, the request timeout and the storage fallbacks were re-applied to the new layout. A forecast without history keeps its table and skips the chart.

Validation after the port, in a fresh Python 3.12 environment installed from `requirements-dev.lock`:

| Check | Result |
| --- | --- |
| Backend suite, excluding browser tests | **195 passed** |
| Backend coverage | **92.45%** (CI gate 70%) |
| PWA browser suite (Chromium) | **24 passed** |
| Expo web export and mobile web smoke | Passed |
| Mobile behavior suite | **12 passed** |
| Ruff, ruff format, mypy, mobile `tsc --noEmit` | Passed |
| pip-audit on both lockfiles | 0 known vulnerabilities |
| Mobile npm audit (Expo 58) | 0 critical, 15 high, 7 moderate |

The September sections below describe the original work, its starting point and its file inventory; they are kept as the record of that review.

## Scope and architecture

The review covered the first-party backend, web and mobile source, API contracts, model pipeline, caching and rate limiting, tests, documentation, dependency manifests, CI, Docker/Compose and Kubernetes templates. Generated artifacts, third-party source and local secret values were excluded from the source review. Dependency advisories were checked separately.

Aurion consists of a FastAPI API serving a vanilla JavaScript PWA, plus an Expo 54 / React Native client. Predictions combine a log-linear statistical model with a k-nearest-neighbor analog model and validation gates. Yahoo supplies price history and FX data; top-asset discovery also uses CoinGecko/catalog fallbacks. Redis supports shared cache and rate-limit state; models, metrics and local caches remain process-local. There is no user database, account authentication or tenant authorization to migrate. The mobile guest/onboarding flag is local UI state, not server authentication.

The working tree already contained changes in 19 tracked files and an untracked observability test. Those changes were retained. A starting hash manifest and source snapshots in `.tmp/audit-baseline/` were used to distinguish this work from the earlier edits. The file inventory below describes changes from that starting state, not the complete Git diff against HEAD.

## Implemented improvements

### API reliability and security

1. GET compatibility and POST prediction requests now share symbol/currency validation and the same HTTP 422 error envelope. Control characters and invalid symbol syntax are rejected before provider access, while supported Yahoo symbol punctuation is retained.
2. Validation responses omit raw input values. This avoids reflecting arbitrary submitted bodies and prevents non-finite input from breaking JSON error serialization.
3. Operational endpoints use constant-time token comparison. Metrics, Prometheus and validation-summary access fails closed in production when the metrics token is absent. Kubernetes now injects that token from its Secret.
4. Proxy identity parsing follows the trusted chain from the right and selects the nearest untrusted valid address. Spoofed leftmost values, malformed chains, untrusted direct peers and equivalent IPv6 representations are covered by tests. Application launch commands disable Uvicorn's independent proxy-header rewriting.
5. Both top-assets URLs now consume the search quota before starting provider work. Rate-limited responses include `Retry-After`; CORS exposes that header and the request ID.
6. Synchronous Redis quota checks no longer run on the prediction event loop. Readiness probes have explicit Redis/executor budgets and require a connected Redis backend in production.
7. The development rate limiter uses a monotonic clock, expires inactive clients and caps its client buckets at 10,000. Reaching capacity cannot reset another client's active quota. Redis limiter connections close during shutdown.
8. Security and cache headers also cover oversized-body and unexpected-error responses. Unexpected errors retain request IDs and appropriate CORS headers without exposing internal exception details to callers.
9. Structured JSON logs retain selected environment, executor, quality-gate and FX fields. Arbitrary extra fields are not automatically included.

### Data correctness, model behavior and performance

1. Statistical forecasts, historical cache records, ML responses and FX conversion retain price precision. Small crypto prices no longer become zero through cent-level rounding; display formatting belongs to the clients.
2. Non-positive/non-finite closes and duplicate observations are removed and reported as degraded input. OHLCV cleanup neutralizes invalid supporting fields. Corrupt history caches, invalid dates and misaligned series trigger a provider refetch.
3. FX calls run through the bounded worker runner with an explicit timeout. Failure preserves native-currency prices and emits a visible warning. Non-finite or non-positive FX rates are rejected; Yahoo MultiIndex results are handled explicitly.
4. Currency conversion also converts MAE and RMSE. Percentage errors and directional accuracy retain their original units.
5. Statistical timeouts return a retryable 504, and unusable input returns a controlled 502. A timeout/failure while validating the statistical baseline for ML can now return the already-computed statistical fallback.
6. ML forecast prices and evaluation values reject non-finite results. The quality gate also compares against a zero-error baseline rather than bypassing that comparison.
7. RSI handles monotonically rising, falling and flat prices. Flat Bollinger windows and constant-volume windows use neutral feature values rather than discarding otherwise usable history.
8. MAPE and confidence-band calculations no longer use a one-cent denominator floor that distorted small-price assets.
9. Model-cache identity includes the complete input history and OHLCV values. Earlier provider corrections and volume-only changes invalidate the model, even when the latest close is unchanged.
10. Fresh local cache entries are read before Redis, avoiding unnecessary round trips. Top-assets caching stores up to 25 entries independently of the requested display limit.
11. Provider symbol-candidate lookup shares an overall time budget and stops starting additional lookups after that budget expires. Individual downloads receive the remaining timeout.

These changes reduce known unnecessary work; no production latency or throughput improvement is claimed without load measurements.

### Web/PWA experience

1. Preference and watchlist access tolerates unavailable browser storage and invalid saved JSON. Themes/currencies use allowlists, saved assets are validated, and watchlists are capped. An in-memory fallback keeps the session usable and failed saves remain visible.
2. Changing market, engine, currency, symbol or horizon cancels/invalidates an obsolete forecast. Late responses cannot replace newer state. Autocomplete work is also cancelled or invalidated on new input and dismissal.
3. Invalid successful forecast responses produce a visible error instead of fabricated zero-valued output. Prediction requests have a 90-second client timeout.
4. Source warnings, stale-data warnings and FX fallback warnings are visible. The explanation fallback note appears only for an actual statistical fallback.
5. Segmented controls initialize their keyboard and ARIA state correctly. Watchlist removal is a separate, labelled keyboard-focusable button. Muted text contrast, narrow-layout wrapping and reduced-motion chart behavior were improved.
6. On narrow screens, completed forecasts scroll into view while respecting reduced-motion preferences.
7. Service-worker cleanup is limited to Aurion-owned caches. Only known shell assets are stored, query variations reuse canonical keys, cache writes are tracked for worker lifetime, and storage-quota errors do not break successful network responses. Existing user-controlled update activation remains intact.

### Mobile experience and maintainability

1. The API client merges JSON and Accept headers correctly, keeps timeouts active through response-body reading, rejects malformed JSON, forwards cancellation and allows a longer forecast budget than list requests.
2. Runtime checks reject invalid prices, forecast bands, source metadata, evaluation/explanation fields and ticker lists before they enter rendered state. Complete responses remain covered by a positive regression test.
3. Detail screens wait for the saved currency, cancel obsolete requests and hide stale/demo prices during a new load. Request cancellation does not silently create a new demo result.
4. Demo fallback uses the requested symbol and horizon, matches its last history point to the summary, and reports USD honestly when no live conversion exists.
5. Watchlist parsing validates, deduplicates and bounds stored entries. Writes execute in order, rapid changes use the latest state, and a failed write does not break later writes. Load/save failures are visible; watchlist controls wait for hydration.
6. Currency/engine and horizon controls gained accessibility labels/state. Clearing a search resets its loading and fallback state. Onboarding storage failures no longer prevent guest use.
7. A shared price formatter and scale-relative chart bounds preserve the visibility of tiny crypto prices.
8. Compatible dependency updates were applied without forcing an Expo major migration. Dependency ranges remain on Expo 54.
9. Node-based tests exercise real TypeScript request/storage/demo logic using the project's existing TypeScript compiler. No additional test framework dependency was introduced.

### Delivery and documentation

1. Docker now uses UID/GID 1000 to match Kubernetes and provides the expected writable home-cache location. Local agent configuration and coverage artifacts are excluded from the build context.
2. The development command imports the backend from the repository root. Environment examples describe the canonical prediction quota and operational-token requirements. The Kubernetes `stringData` example explains plain-string values correctly.
3. CI now includes mobile behavior tests and a critical-vulnerability gate alongside the existing backend/browser/type/format/security checks.
4. Test setup suppresses local `.env` loading during initial app import and isolates configuration per test. Browser tests use a dedicated deterministic provider boundary while retaining actual routing, orchestration, middleware and rendering.
5. Root/mobile setup instructions and [operations documentation](OPERATIONS.md) describe current behavior, failure contracts, deployment requirements and verification limits.

## Validation results

| Check | Result |
| --- | --- |
| Starting backend suite | 102 passed |
| Final backend suite, excluding browser tests | **144 passed** |
| Backend coverage | **87.83%**, above the 70% CI requirement |
| Starting browser suite | 5 passed |
| Final Chromium browser suite | **18 passed** |
| Mobile behavior suite | **10 passed** |
| Ruff lint and formatting | Passed; 40 Python files formatted correctly |
| mypy | Passed; 25 backend source files |
| Mobile TypeScript | `tsc --noEmit` passed |
| Web JavaScript syntax | `node --check` passed for app and service worker |
| Expo web export after final client changes | Passed; 489 modules, approximately 811 kB JavaScript bundle |
| Compiled Expo browser smoke | Guest entry, explicit offline demo, save and horizon change passed; no page errors |
| YAML parsing | 10 CI/Compose/Kubernetes files parsed successfully |
| Git whitespace check | Passed |
| Backend dependency audit | 0 reported vulnerabilities across 41 resolved packages |

The backend and browser suites include error/status/header contracts, proxy spoofing, rate-limit bounds, corrupt data/cache handling, timeout fallbacks, FX units, ML features/cache invalidation, storage failures, obsolete requests, keyboard controls, PWA offline/cache behavior and stock/crypto forecasts through the real API. New behavior regressions were reproduced with failing tests before their fixes. Desktop and narrow-screen results were visually inspected.

The two Python warnings are upstream deprecations in the Starlette test client (`httpx` and the AnyIO `BlockingPortal` alias). Expo also emitted an environment color-setting warning. These did not fail tests or builds.

The existing `.venv` referenced an unavailable Python installation. Validation used a separate Python 3.12 environment in `.tmp/audit-venv`; it did not overwrite the old environment. Local evidence is retained under `.tmp/`: `audit-backend-tests.txt`, `audit-browser-tests.txt`, `audit-coverage.json`, dependency audit JSON and desktop/mobile/Expo screenshots. These are ignored working artifacts, not committed build outputs.

### Mobile dependency audit

| npm severity | Before | After compatible fixes |
| --- | ---: | ---: |
| Critical | 2 | **0** |
| High | 16 | **10** |
| Moderate | 14 | **14** |
| Low | 1 | **0** |
| Total | 33 | **24** |

After the port onto `main`'s Expo SDK 58 lockfile (2026-10-20): 0 critical, 15 high, 7 moderate, 0 low, 22 total.

These are npm's vulnerable-package counts, including transitive/advisory propagation, not a count of proven exploitable application paths. Remaining findings involve the Expo/Metro toolchain and navigation dependencies, including image-size, PostCSS, UUID, xcode, ws and decode-uri-component paths. Some remediation suggestions require a major Expo migration; others depend on upstream releases. No forced major upgrade or incompatible transitive override was applied. The new CI gate blocks critical findings; it deliberately does not claim the remaining high/moderate findings are fixed.

## Remaining risks and three best next steps

1. **Resolve the remaining mobile advisories through a supported SDK/dependency migration.** Upgrade Expo/React Native and associated native modules together, address upstream-only dependency paths, and add Android/iOS build and device smoke checks. Native Android/iOS builds were not executed in this Windows session; the successful web export does not substitute for them.
2. **Validate deployment and resource limits in staging.** Build/run the image with a working Docker engine, exercise Redis failure/recovery and concurrent requests, and verify ingress proxy trust, CORS, real secrets, health probes and writable volumes. The Docker daemon was unavailable locally; Kubernetes was not deployed. The sample Redis configuration mixes disposable caches with quota state: `allkeys-lru` can evict active quota keys under memory pressure. Separate quota state from evictable cache data for an exposed scaled deployment. Metrics/model caches remain process-local. A timed-out Python thread can continue until the provider returns; cancellation is not process isolation.
3. **Validate market units and model quality against representative live data.** Replace suffix-based currency inference with explicit provider quote-unit metadata, including GBp versus GBP. Add exchange-specific trading calendars and rerun the dated backtests after the feature/precision changes. Deterministic tests establish software behavior, not forecast accuracy, calibration or live-provider availability. The existing backtest report must not be treated as fresh evidence for the modified model.

No account authentication or cross-device watchlist synchronization was added: those require a product/data-ownership choice and a persistent user-data design. Local secret values and Git secret history were not audited; no assertion is made that historical credentials never existed. This review is not a penetration test or a production capacity certification.

Primary references used for the proxy and middleware decisions: [MDN X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For), [Uvicorn settings](https://www.uvicorn.org/settings/), [Starlette middleware](https://starlette.dev/middleware/). Dependency counts come from the actual pip-audit and npm audit outputs captured for this workspace.

## Changed files

45 existing files were changed relative to the starting workspace, and 10 files were added. `tests/test_observability.py` already existed as an untracked user file and is counted among the modified existing files. Earlier changes in `backend/config.py`, `backend/runtime.py` and `tests/test_market_data.py` remain intact and are not counted as edits from this audit.

### Backend (14 modified)

- [backend/Dockerfile](../backend/Dockerfile)
- [backend/app.py](../backend/app.py)
- [backend/main.py](../backend/main.py)
- [backend/models.py](../backend/models.py)
- [backend/routes/api.py](../backend/routes/api.py)
- [backend/ml/features.py](../backend/ml/features.py)
- [backend/ml/model.py](../backend/ml/model.py)
- [backend/ml/service.py](../backend/ml/service.py)
- [backend/services/cache.py](../backend/services/cache.py)
- [backend/services/exchange_rates.py](../backend/services/exchange_rates.py)
- [backend/services/forecast.py](../backend/services/forecast.py)
- [backend/services/market_data.py](../backend/services/market_data.py)
- [backend/services/prediction.py](../backend/services/prediction.py)
- [backend/services/rate_limit.py](../backend/services/rate_limit.py)

### Web (4 modified)

- [frontend/app.js](../frontend/app.js)
- [frontend/index.html](../frontend/index.html)
- [frontend/styles.css](../frontend/styles.css)
- [frontend/sw.js](../frontend/sw.js)

### Mobile (13 modified, 5 added)

- [mobile/README.md](../mobile/README.md)
- [mobile/package.json](../mobile/package.json)
- [mobile/package-lock.json](../mobile/package-lock.json)
- [mobile/src/api/client.ts](../mobile/src/api/client.ts)
- [mobile/src/api/format.ts](../mobile/src/api/format.ts) — added
- [mobile/src/components/ForecastCard.tsx](../mobile/src/components/ForecastCard.tsx)
- [mobile/src/components/ForecastChart.tsx](../mobile/src/components/ForecastChart.tsx)
- [mobile/src/context/AuthContext.tsx](../mobile/src/context/AuthContext.tsx)
- [mobile/src/context/WatchlistContext.tsx](../mobile/src/context/WatchlistContext.tsx)
- [mobile/src/data/demoAssets.ts](../mobile/src/data/demoAssets.ts)
- [mobile/src/screens/AssetDetailScreen.tsx](../mobile/src/screens/AssetDetailScreen.tsx)
- [mobile/src/screens/HomeScreen.tsx](../mobile/src/screens/HomeScreen.tsx)
- [mobile/src/screens/WatchlistScreen.tsx](../mobile/src/screens/WatchlistScreen.tsx)
- [mobile/src/services/marketService.ts](../mobile/src/services/marketService.ts)
- [mobile/src/storage/watchlist.ts](../mobile/src/storage/watchlist.ts) — added
- [mobile/tests/client.test.cjs](../mobile/tests/client.test.cjs) — added
- [mobile/tests/runtime.cjs](../mobile/tests/runtime.cjs) — added
- [mobile/tests/watchlist.test.cjs](../mobile/tests/watchlist.test.cjs) — added

### Tests (7 modified, 3 added)

- [tests/conftest.py](../tests/conftest.py)
- [tests/browser_server.py](../tests/browser_server.py) — added
- [tests/test_api_hardening.py](../tests/test_api_hardening.py) — added
- [tests/test_data_integrity.py](../tests/test_data_integrity.py) — added
- [tests/test_exchange_rates.py](../tests/test_exchange_rates.py)
- [tests/test_frontend_smoke.py](../tests/test_frontend_smoke.py)
- [tests/test_ml_pipeline.py](../tests/test_ml_pipeline.py)
- [tests/test_observability.py](../tests/test_observability.py)
- [tests/test_prediction_service.py](../tests/test_prediction_service.py)
- [tests/test_rate_limit.py](../tests/test_rate_limit.py)

### Delivery and root documentation (7 modified, 2 added)

- [.dockerignore](../.dockerignore)
- [.env.example](../.env.example)
- [.github/workflows/ci.yml](../.github/workflows/ci.yml)
- [Makefile](../Makefile)
- [README.md](../README.md)
- [infra/k8s/deployment.yaml](../infra/k8s/deployment.yaml)
- [infra/k8s/secret.yaml](../infra/k8s/secret.yaml)
- [docs/OPERATIONS.md](OPERATIONS.md) — added
- [docs/ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md) — added
