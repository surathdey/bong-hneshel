# 🍛 Curry & Co.

**A production-ready food-delivery platform for Bengali & Indian cloud-kitchen meals across the Greater Toronto Area.**

One codebase. Three purpose-built apps. One backend to rule them all.

---

## 📱 What's inside — three apps, one repo

| App | Where it lives | Who uses it |
|-----|----------------|-------------|
| 🛒 **Customer App** (iOS + Android + Web) | `frontend/app/(tabs)/`, `frontend/app/menu/`, `frontend/app/catering/`, `frontend/app/order/`, `frontend/app/login.tsx` | End customers ordering weekly meals & catering |
| 🚗 **Delivery Partner App** (iOS + Android) | `frontend/app/delivery-partner.tsx`, `frontend/src/components/RouteMap.tsx`, `frontend/src/deliveryApi.ts` | Drivers running last-mile routes |
| 🖥️ **Admin Web Portal** (Browser) | `frontend/app/admin/` | Restaurant operators managing everything |
| ⚙️ **Backend API** | `backend/server.py` | Serves all three apps + does auth, payments, routing, orders |

### 🧠 Why is it one codebase and not four?

The frontend is a single **Expo Router** monorepo. The three mobile/web experiences are switched via the `APP_VARIANT` environment variable + file-based routing:

```
APP_VARIANT=customer   → Customer App loads (tabs: Home / Menu / Catering / Bag / Profile)
APP_VARIANT=delivery   → Delivery Partner App loads (delivery-partner.tsx)
Admin Portal           → Served via /admin/* routes on the web build
```

This lets us **ship all three apps from one codebase**, share ~60% of the code (theme, API layer, auth, cart, components, utils), and produce **separate app-store listings** at publish time by re-building with a different `APP_VARIANT`.

> Want to physically split into 4 folders (each its own project)? See the *"Splitting into 4 projects"* section at the bottom — it's a ~1-2 day refactor.

---

## 📁 Repo layout

```
Curry-Co/
├── backend/                    # FastAPI + MongoDB backend (serves ALL three apps)
│   ├── server.py               # Main API — ~2900 lines, auth/menu/orders/delivery/admin
│   ├── requirements.txt        # Python deps
│   ├── .env.example            # Sample env file (real .env is gitignored)
│   └── tests/
│
├── frontend/                   # Expo Router monorepo (Customer + Delivery + Admin)
│   ├── app/                    # File-based routes
│   │   ├── (tabs)/             # 🛒 Customer bottom-tab navigator
│   │   ├── admin/              # 🖥️ Admin Web Portal pages
│   │   ├── menu/               # Customer weekly-package picker
│   │   ├── catering/           # Customer catering customizer
│   │   ├── order/              # Customer live order tracking
│   │   ├── delivery-partner.tsx  # 🚗 Entire Delivery Partner App
│   │   ├── login.tsx
│   │   └── _layout.tsx         # Variant-based routing enforcement
│   ├── src/                    # Shared code (imported by all 3 apps)
│   │   ├── api.ts, adminApi.ts, deliveryApi.ts
│   │   ├── auth.tsx, cart.tsx, theme.ts
│   │   ├── components/         # Shared UI (incl. RouteMap.tsx)
│   │   └── utils/
│   ├── app.config.js           # Expo config — reads APP_VARIANT to swap name/icon/bundle ID
│   ├── package.json
│   └── .env.example
│
├── exports/                    # Sales pitch deck (HTML + PDF)
├── memory/                     # PRD.md — living product spec
├── scripts/                    # e.g. switch-variant.sh — flip APP_VARIANT quickly
├── tests/                      # High-level integration tests
└── README.md                   # ← you are here
```

---

## 🚀 Quick start (local dev)

### 1. Prerequisites
- Python 3.11+
- Node 20+ and Yarn
- MongoDB running locally on `mongodb://localhost:27017`
- Google Maps API key (Directions + Geocoding enabled)
- (Optional) Stripe test key

### 2. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill in the real keys
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Backend serves on `http://localhost:8001` — all routes prefixed with `/api/*`.

### 3. Frontend (Customer app — default)

```bash
cd frontend
yarn install
cp .env.example .env       # fill in EXPO_BACKEND_URL + EXPO_PUBLIC_GOOGLE_MAPS_API_KEY
yarn start                 # or: yarn web
```

Metro serves on `http://localhost:3000`.

### 4. Switch to the Delivery Partner app

Edit `frontend/.env`:

```env
APP_VARIANT=delivery
```

Restart Metro → same URL now loads the Delivery Partner UI, with a different app name & bundle ID at publish time.

> **Shortcut in dev**: there's a "Delivery Partner sign-in" link at the bottom of the Customer login page so you can access the delivery flow without restarting Metro.

### 5. Admin Web Portal

Open `http://localhost:3000/admin` in a browser (web build only — admin isn't shipped to app stores). Log in with the seeded admin account below.

---

## 🔑 Environment variables

### `backend/.env`
```env
MONGO_URL="mongodb://localhost:27017"
DB_NAME="curry_co_db"
GOOGLE_MAPS_API_KEY=AIza...             # Directions + Geocoding
STRIPE_SECRET_KEY=sk_test_...           # optional in dev
EMERGENT_LLM_KEY=...                    # optional, for AI features
ADMIN_EMAIL=admin@curryandco.local
ADMIN_PASSWORD=curry@admin2026
```

### `frontend/.env`
```env
EXPO_BACKEND_URL=http://localhost:8001
EXPO_PUBLIC_GOOGLE_MAPS_API_KEY=AIza... # same key, used by delivery-partner's RouteMap
APP_VARIANT=customer                     # or "delivery"
```

Do **not** commit real `.env` files — they're gitignored.

---

## 👤 Default seeded accounts (dev only)

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@curryandco.local` | `curry@admin2026` |
| Delivery Partner | `rahul.delivery@curryandco.local` | `curry@delivery2026` |
| Customer | Guest checkout OR Google sign-in |

Rotate these before going to production.

---

## 🧩 Feature highlights (short version)

**Customer app** — Dynamic weekly menus (Sun–Thu order, Fri–Sat delivery), à la carte + "Pick 4 for $59" package mode, catering with per-person tiers and mandatory/optional add-ons, unified Bag tab, guest checkout, Stripe + COD, live order tracking with driver ETA.

**Delivery Partner app** — Interactive zoomable Google Map, one-tap route optimization via Google Directions, address-based start point (geocoding), manual ⬆⬇ stop reorder with instant recalculation, tap-to-navigate deep links, customer name on every stop, **START DELIVERY** button that flips orders to `on_the_way` and streams live ETA to customers, journey persistence across logout/login, 10 s location heartbeat during active journey.

**Admin Portal** — Live dashboard, master menu (single source of truth), weekly-menu builder (with À la carte ↔ Package combo toggle), catering package configurator v2 (choice groups + upcharges), orders management with one-click driver assignment, delivery-partner onboarding, tax/settings toggles.

Full feature list → see the [sales pitch deck](exports/CurryCo_Sales_Pitch.pdf) and [`memory/PRD.md`](memory/PRD.md).

---

## 🛠️ Tech stack

| Layer | Tech |
|---|---|
| Mobile & Web frontend | React Native + Expo Router (~SDK 53), TypeScript, Reanimated, react-native-webview |
| Backend | FastAPI, Motor (async MongoDB), Pydantic v2 |
| Database | MongoDB |
| Auth | Google OAuth (Emergent-managed), JWT for delivery partners, bcrypt admin |
| Payments | Stripe Checkout Sessions + Cash on Delivery |
| Maps | Google Directions API (`waypoints:optimize`), Google Geocoding, Google Maps JS API (embedded via WebView/iframe) |
| Notifications | Emergent push + email (production only) |

---

## 🚢 Deployment

The whole stack ships via Emergent's one-click **Publish** flow:

1. **Publish once with `APP_VARIANT=customer`** → generates *Curry & Co.* iOS + Android + Web builds.
2. **Publish again with `APP_VARIANT=delivery`** → generates a separate *Curry & Co. Delivery* iOS + Android build with its own bundle ID.
3. The Admin Web Portal ships alongside the customer web build under `/admin/*`.

Backend + MongoDB are deployed together as a single container behind the same domain.

---

## 🧪 Testing

- Integration test reports live in `test_reports/iteration_*.json` (gitignored).
- Manual smoke tests live in `test_result.md`.
- All screens have `testID` props for Playwright/Detox automation.

---

## ✂️ Splitting into 4 projects (advanced — not recommended today)

If you truly need Customer / Delivery / Admin as three independent Expo projects, plan for:

1. `yarn create expo customer-app`, `delivery-app`, `admin-portal` — three fresh projects.
2. Extract `frontend/src/*` into a shared workspace (Yarn workspaces or npm workspaces) — e.g. `packages/shared` with theme, API clients, auth, utils, components.
3. Move each set of routes from `frontend/app/*` into its respective project's `app/` folder.
4. Duplicate `metro.config.js`, `app.json`, `package.json`, `.env` — one per project.
5. Set up 3 separate CI pipelines (or one monorepo pipeline via Turbo/Nx).

**Effort: 1-2 days of refactor.** Ask if you'd like this broken out into a proper migration plan.

---

## 📄 License & contact

Private / commercial. Contact **admin@curryandco.local** or open an issue.

Made with 🌶️ in the GTA.
