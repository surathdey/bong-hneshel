# Import Notes — mastard_garden (Curry & Co.)

Imported from https://github.com/surathdey/mastard_garden as the project starting point.
No restructuring or refactoring performed — code brought in as-is.

## What was done
- Downloaded repo tarball and copied full tree into `/app` (frontend + backend + docs/scripts/memory/etc.).
- Preserved platform-protected files: `frontend/.env` (packager/proxy/backend URLs), `backend/.env` (MONGO_URL), `.git`, `.emergent`, `frontend/metro.config.js`.
- Removed template leftover `frontend/app.json` (repo uses dynamic `app.config.js` + `brand.config.js`) and a stray `backend/=0.24.0` file.

## Env additions (dev-only)
- `backend/.env`: added `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, empty `STRIPE_API_KEY`/`GOOGLE_MAPS_API_KEY`/`EMERGENT_LLM_KEY`. Kept existing `MONGO_URL`, `DB_NAME`.
- `frontend/.env`: added `APP_VARIANT=customer`, empty `EXPO_PUBLIC_GOOGLE_MAPS_API_KEY`.

## Deps
- Backend: most already present; installed missing `twilio`, `openpyxl` (google-api libs already present).
- Frontend: `yarn install` completed (Expo SDK 54). Non-blocking warnings: minor expo/expo-constants patch-version mismatch.

## Boot status
- Backend: healthy — `GET /api/` => `{service: curry-co-api, ok: true}`, `/api/brand` => 200, admin seeded.
- Frontend: Metro bundles; login screen renders in web preview.
- Not tested yet (per instruction).

## Default seeded accounts (dev)
- Admin: admin@curryandco.local / curry@admin2026
