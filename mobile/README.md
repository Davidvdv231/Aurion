# Stock Pulse AI Mobile

Expo/React Native MVP voor een publieke forecasting app. Dit is de mobiele laag die praat met de bestaande FastAPI-backend via een kleine API-client en fallback demo-data.

## Wat zit erin
- Login/splash flow met demo-auth
- Home met markt-highlights, zoekfunctie en navigatie naar asset detail
- Asset detail met forecast cards, confidence indicator en chart placeholder
- Watchlist met lokale opslag
- Gescheiden API-client, service layer, auth state en storage abstraction
- Production-minded theming en folderstructuur voor later uitbreiden

## Run
1. Ga naar `mobile/`
2. Installeer dependencies met `npm install`
3. Doe een lokale sanity-check met `npm run typecheck`
4. Start de app met `npm run start`
5. Zet optioneel de backend URL via `EXPO_PUBLIC_API_BASE_URL`

Voorbeeld:

```bash
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run start
```

Voor een snelle readiness-check zonder simulator:

```bash
npm run typecheck
```

## Architectuur
- `src/api`: HTTP-client en API-types
- `src/services`: domeinlogica met fallback naar demo-data
- `src/context`: auth- en watchlist-state
- `src/screens`: login, home, detail en watchlist
- `src/components`: herbruikbare UI-blokken
- `src/theme`: kleuren, spacing, typografie en radii
- `src/storage`: lokale opslag-abstrahering

## Opmerking
De app moet niet worden gepresenteerd als financieel advies. Voorspellingen zijn probabilistisch en afhankelijk van data-kwaliteit, netwerk en backend-beschikbaarheid.
