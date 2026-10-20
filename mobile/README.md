# Aurion Mobile

Expo/React Native client for Aurion. The mobile app talks to the FastAPI backend through a small typed API client and falls back to clearly labeled demo data when the live API is unavailable.

## Included
- Guest flow without fake authentication
- Home screen with API-first highlights, symbol search, and asset navigation
- Asset detail view with the expected price, a facts list, an SVG price chart (touch to read a day) with a table view, the backtest, the analog explanation, and a clearly marked demo fallback note
- Local watchlist persistence
- Light and dark themes that follow the system setting
- Separated API client, service layer, auth state, and storage abstraction

## Design
The app uses the same look as the web app in `frontend/`: warm grays, hairline rules instead of cards, IBM Plex Sans and Mono, and one orange accent kept for the forecast. Colors live in `src/theme/theme.ts` and mirror the tokens in `frontend/styles.css`, so change both together. Components get themed styles through `makeStyles`, which builds one `StyleSheet` per color scheme.

## Run
1. `cd mobile`
2. `npm ci`
3. `npm run typecheck`
4. `npm run start`

Run `npm test` for request handling, cancellation, demo consistency, watchlist validation and ordered writes. `npx expo export --platform web` checks the compiled client; native Android/iOS builds need their platform toolchains.

Use `EXPO_PUBLIC_API_BASE_URL` for any non-local build. In local development, the app falls back to `http://127.0.0.1:8000`.

On a physical phone, use the development machine's reachable LAN address. For an Android emulator, use `http://10.0.2.2:8000`. The API must bind to an interface reachable from that device. Expo web also needs its origin in backend `CORS_ALLOW_ORIGINS`.

```bash
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run start
```

## Structure
- `src/api`: HTTP client and API contract types
- `src/services`: API-first data loading with explicit demo fallback handling
- `src/context`: onboarding and watchlist state
- `src/screens`: welcome, home, detail, splash, and watchlist views
- `src/components`: reusable mobile UI blocks
- `src/theme`: light and dark color tokens, fonts, spacing, and the `useTheme`/`makeStyles` hooks
- `src/utils`: price, percent, and date formatting shared by the screens
- `src/storage`: local storage abstraction

## Notes
- Demo data is a fallback path, not a production data source.
- Loading hides previous/demo price cards until the current request completes. Changing forecast settings aborts the previous request. Predictions allow up to 90 seconds across backend stages; list requests allow 15 seconds. Both budgets include reading the response body.
- Demo responses preserve the requested symbol and horizon and explicitly keep USD when live FX is unavailable.
- Watchlists use symbol plus market as identity, cap at 100 entries, validate saved data and serialize writes. Storage failures leave session state usable and display a message.
- Dependency updates remain within the existing Expo 54 stack. See [the audit](../docs/ENGINEERING_AUDIT.md) for unresolved upstream advisories.
- Predictions are probabilistic estimates and not financial advice.
