# Development and operations

Run all Python commands from the repository root. Use Python 3.12 and install the hash-locked `requirements-dev.lock` (`python -m pip install --require-hashes -r requirements-dev.lock`) for local testing. A virtual environment moved from another machine or Python installation must be recreated; do not repair it by editing its interpreter path. Copy `.env.example` to `.env` for Compose; keep real credentials out of Git.

## Request and data contracts

- GET compatibility and POST prediction requests share symbol/currency validation. Invalid input returns the `invalid_request` envelope with HTTP 422. Error details omit raw body values.
- Prediction quotas apply per engine and client. `RATE_LIMIT_MAX_REQUESTS_PREDICT` takes precedence over legacy `RATE_LIMIT_MAX_REQUESTS_STAT`. Ticker search and both top-assets aliases share the search quota. 429 responses include a conservative `Retry-After` equal to the configured window.
- Market data and forecast stages use `BLOCKING_TASK_TIMEOUT_SECONDS`. Provider candidate lookup stops when that budget is spent. Already-running provider code cannot be forcibly killed by Python thread cancellation; provider timeouts remain necessary.
- ML validation/training failure returns the statistical fallback. Statistical calculation timeout returns 504. The statistical backtest also runs off the event loop; if it times out, the statistical forecast is served without an `evaluation`, and an ML request falls back with `ml_engine_timeout` because it cannot be quality-gated. FX failure keeps all prices in the native currency and adds a visible warning. Absolute evaluation errors (MAE/RMSE) are converted with prices; MAPE and directional accuracy are dimensionless.
- API prices retain floating-point precision; clients format for display. Non-positive, infinite and duplicate market observations are removed and mark the data `degraded`; days without a close are dropped and mark it at least `patched`. Both are reported in `data_warnings`. Malformed history caches trigger a provider refetch.
- The local TTL cache is read first. Redis is used for misses and shared writes; cache reads do not extend the original TTL. Top-asset responses cache up to 25 entries independently of the requested list size. ML cache identity includes the complete training input, including OHLCV corrections.

## Production configuration

1. Set `APP_ENV=production`, a reachable `REDIS_URL`, real `CORS_ALLOW_ORIGINS`, and a random `METRICS_TOKEN`. Placeholder domains and tokens fail startup. The Kubernetes Secret uses `stringData`: plain strings, not manually base64-encoded values. Inject secrets outside source control.
2. Route `/api/metrics`, `/api/metrics/prometheus` and `/api/validation-summary` with `Authorization: Bearer <token>`. Wrong/missing credentials return 403; an unconfigured production token yields 503. Health probes remain accessible.
3. Configure `TRUSTED_PROXY_IPS` to the exact ingress addresses or narrow CIDRs for your deployment. The sample `10.0.0.0/8` is a placeholder to review, not a universal safe choice. Proxies must append/sanitize `X-Forwarded-For`. The app walks right-to-left to the nearest untrusted valid address.
4. Launch Uvicorn with `--no-proxy-headers`, as the Dockerfile and `make dev` do. Aurion then owns client-IP validation; Uvicorn must not rewrite the peer address using a separate trust configuration. HTTPS still terminates at the ingress. Configure TLS hosts and replace the sample image/domain before applying manifests.
5. The image uses UID/GID 1000, matching Kubernetes. Its home cache is `/home/appuser/.cache`, backed by a writable volume alongside `/tmp`. The remainder of the pod filesystem stays read-only. `METRICS_TOKEN` is explicitly wired from the Secret.

## Health and scaling

`/api/health` is a liveness/status endpoint. `/api/health/ready` checks Redis and the bounded executor, each with a two-second probe budget. The pod's readiness timeout is five seconds. Redis is mandatory in production; in development `not_configured` is acceptable. A saturated executor or unavailable required dependency yields 503 readiness.

Replicas share Redis quotas; models, memory caches, latest evaluation and metrics remain process-local. Scrape each replica. Redis is shared by caching and quotas in the example; its `allkeys-lru` eviction policy can evict rate-limit keys under pressure. Separate durable quota state from disposable cache state before an exposed, scaled deployment.

## Verification limits

Automated tests use deterministic market data and do not establish live feed availability or forecast accuracy. The backtest report regenerated on 2026-10-18 predates the indicator/precision fixes ported afterwards and must be regenerated before making model-quality claims. Stock forecast dates skip weekends but do not incorporate exchange-specific holidays. Currency inference still uses ticker suffix/catalog metadata; quote units such as GBp vs GBP need provider metadata before relying on London-market conversions.

Local validation covers backend, PWA browsers and an Expo web bundle. Docker requires a running engine; Kubernetes and native Android/iOS runtime validation remain separate environment checks. No production changes are performed by these test commands.

Primary references for the proxy/header review: [MDN X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For), [Uvicorn proxy settings](https://www.uvicorn.org/settings/), [Starlette middleware ordering](https://starlette.dev/middleware/).
