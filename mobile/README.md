# Life Admin AI Mobile

Shared Expo / React Native app for the existing Life Admin backend and feature set.

## Included screens

- Dashboard with bill stats, Gmail sync, and run-agent action
- Bills list with search and status filters
- Bill detail with mark-paid and re-run-agent actions
- Spending tracker with period filters, AI insights, category breakdown, delete transaction, and daily spend
- Statement analyzer with PDF / CSV upload and full analysis results
- Settings screen for API URL and dev token configuration

## Run locally

1. Install dependencies

   ```bash
   npm install
   ```

2. Start Expo

   ```bash
   npx expo start
   ```

3. Open on:

- Android emulator
- iOS simulator
- Expo Go on a real device
- Web

## Backend connection

The app stores its API URL and bearer token in secure storage and pre-fills them with sensible dev defaults.

- Android emulator usually needs `http://10.0.2.2:8000`
- iOS simulator can usually use `http://localhost:8000`
- Real devices need your laptop's LAN IP, for example `http://192.168.1.15:8000`

Use the in-app **Settings** tab if the app cannot reach your API.

## Verification

- `npx tsc --noEmit`
- `npm run lint`
- `npx expo export --platform web`
