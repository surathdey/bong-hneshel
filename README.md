# 🍛 Bong Hneshel

**A production-ready food-delivery platform bringing authentic Bengali home cooking to the Greater Toronto Area (GTA).**

_Home Food, Delivered._

One codebase → **three purpose-built apps** (Customer, Delivery Partner, Admin) → **one FastAPI backend**.

---

## 📱 What's inside — three apps, one repo

| App | Where it lives | Who uses it |
|-----|----------------|-------------|
| 🛒 **Customer App** (iOS + Android + Web) | `frontend/app/(tabs)/`, `frontend/app/menu/`, `frontend/app/catering/`, `frontend/app/order/`, `frontend/app/cart.tsx`, `frontend/app/login.tsx` | Customers ordering weekly meals & catering |
| 🚗 **Delivery Partner App** (iOS + Android) | `frontend/app/delivery-partner.tsx`, `frontend/src/components/RouteMap.tsx` | Drivers running last-mile routes |
| 🖥️ **Admin Web Portal** (Browser only) | `frontend/app/admin/` | Restaurant operators managing everything |
| ⚙️ **Backend API** | `backend/server.py` | Serves all three apps + auth, payments, routing, orders, AI |

### 🧠 Why one codebase and not three?

The frontend is a single **Expo Router** app. The three experiences are switched via the `APP_VARIANT` environment variable + file-based routing:

```
APP_VARIANT=customer   → Customer App (tabs: Home / Menu / Catering / Orders / Profile)
APP_VARIANT=delivery   → Delivery Partner App (delivery-partner.tsx)
Admin Portal           → Served via /admin/* routes on the web build (any variant)
```

This ships all three apps from one codebase, shares the theme, API layer, auth, cart and components, and produces **separate app-store listings** at publish time by re-building with a different `APP_VARIANT`.

---

## 📁 Repo layout

```
bong-hneshel/
├── backend/                      # FastAPI + MongoDB (serves ALL three apps)
│   ├── server.py                 # Main API — ~5850 lines (auth/menu/orders/delivery/admin/payments/AI)
│   ├── menu_ai.py                # AI menu descriptions (GPT) + food photos (Gemini Nano Banana)
│   ├── email_client.py           # Resend email (Emergent-managed)
│   ├── twilio_client.py          # Twilio SMS
│   ├── settings_crypto.py        # Fernet encryption for tenant secrets stored in DB
│   ├── billing_client.py / platform_client.py / drive_client.py
│   ├── build_mg_menu.py / build_weekly.py / seed_bong_products.py   # one-off menu builders
│   ├── scripts/wipe_test_data.py # QA wipe (keeps menu + settings)
│   ├── tests/                    # Pytest suite (backend API + feature tests)
│   ├── web_dist/                 # Pre-built Expo web bundle shipped INSIDE the backend (prod /admin)
│   ├── requirements.txt
│   ├── SCHEMA.md                 # Full MongoDB schema reference
│   └── .env                      # (gitignored) real secrets
│
├── frontend/                     # Expo Router app (Customer + Delivery + Admin)
│   ├── app/                      # File-based routes
│   │   ├── (tabs)/               # 🛒 Customer bottom-tab navigator
│   │   │   ├── index.tsx         #    Home
│   │   │   ├── menu.tsx          #    Weekly menu / à la carte / package
│   │   │   ├── catering.tsx      #    Catering packages
│   │   │   ├── orders.tsx        #    Order history
│   │   │   └── profile.tsx       #    Profile + Delete Account
│   │   ├── admin/                # 🖥️ Admin Web Portal pages (see table below)
│   │   ├── menu/[id].tsx         # Weekly-package picker
│   │   ├── catering/[id].tsx     # Catering customizer
│   │   ├── order/[id].tsx        # Live order tracking
│   │   ├── legal/privacy.tsx     # Privacy policy
│   │   ├── cart.tsx              # Bag / checkout
│   │   ├── delivery-partner.tsx  # 🚗 Entire Delivery Partner App
│   │   ├── login.tsx
│   │   └── _layout.tsx           # Variant-based routing enforcement
│   ├── src/                      # Shared code (auth, cart, theme, api clients, components, utils)
│   ├── assets/                   # brand/, fonts/ (Ionicons.ttf for prod web), images/
│   ├── app.config.js             # Expo config — reads APP_VARIANT to swap name/icon/bundle ID
│   ├── brand.config.js           # Single source of truth for brand identity + colours
│   └── .env                      # (gitignored)
│
├── memory/PRD.md                 # Living product spec (full changelog / waves)
├── test_reports/                 # testing_agent iteration reports (gitignored)
├── TENANT_ONBOARDING_PROMPT.md   # Reusable prompt to spin up a new tenant
└── README.md                     # ← you are here
```

---

## ✨ Feature catalogue

### 🛒 Customer App
- **Sign-in options:** Google (Emergent-managed OAuth), **email + password** (sign up / sign in), and guest checkout — no account required to order.
- **Email sign-up** collects an **optional mobile number** (unlocks loyalty eligibility) and derives a display name.
- **Forgot / reset password** — emails a single-use **6-digit code** (valid 15 min, max 5 attempts) via Resend; resetting invalidates all existing sessions.
- **Welcome email** — every new customer (email **and** Google) automatically receives a welcome email, which includes the active **first-order coupon** from Admin → Coupons when one is configured.
- **Manage profile** — customers can add or edit their name and mobile number anytime from the Profile screen (`POST /api/me/profile`).
- **Loyalty gate** — logged-in members without a phone number see a gentle checkout nudge to add one and start earning points.
- **Referrals / invite** — every customer gets a unique invite code (Profile → "Invite friends & earn"). Friends get a discount on their first order; the referrer earns loyalty points once the friend's first order is paid. Shared via the native share sheet; reward amounts are set in Admin → Settings.
- **In-app Account Deletion** (Profile → "Delete my account" → `DELETE /api/user/me`) — cascades sessions, push tokens, saved addresses. _(Required for Apple App Store compliance.)_
- **Weekly rotating menu** — order Sun–Thu, delivered Friday. Home hero, chef's featured, this-week grid, upcoming weeks.
- **Two menu modes** per week (admin-toggleable):
  - **À la carte** — pick individual dishes with clear veg / non-veg labels.
  - **Weekly Package** — pick exactly N dishes. Supports **composition pricing** (all-veg $64.99 / mixed $69.99 / all-non-veg $79.99) or flat pricing. Live "estimated savings" chip.
- **Complimentary items** shown when a weekly package is active (e.g. Payesh + Dal of the Week).
- **Always Available** section — order-anytime staples (Roti, Biryani, Rolls…).
- **Catering v2** — packages by guest count with choice groups (min/max), upgrade tiers, per-person premium add-ons, always-included items, and a custom-quote contact form.
- **Bag / Cart** — per-item stepper, coupon input, **loyalty-points redemption**, delivery-slot picker, **Google Places address autocomplete** (Canada-restricted), saved default address (server-side for logged-in, AsyncStorage for guests).
- **Distance-based delivery fee** (Google Distance Matrix): 0–20 km FREE, 20–40 km $5, 40–75 km $10, >75 km $15.
- **Payment methods** (data-driven, only enabled ones render): **Stripe** hosted checkout, **PayPal**, **Cash on Delivery**, **Interac e-Transfer** (with inline email + instructions and a "send exactly $X" confirm modal). **Per-method HST** toggle.
- **Live order tracking** — zoomable Google map (WebView/iframe), driver avatar + call button, "N stops away · ~X–Y min" smart ETA, vertical status timeline, proof-of-delivery photo.
- **Loyalty rewards** — earn points per $1 on paid orders; redeem in increments for $ off.
- **Coupons** — percent / fixed, min-order threshold, first-order-only (e.g. `FIRST10` = 10% off).

### 🚗 Delivery Partner App
- Separate login (JWT). Seeded demo partner "Rahul Das".
- **Route planner** — address-autocomplete start point, one-tap **Google Directions optimization** (`waypoints:optimize`), manual ⬆⬇ stop reorder with instant recalculation, per-leg ETA + distance, tap-to-navigate deep links.
- **Interactive zoomable Google map** with S/A/B/C markers + decoded polyline.
- **START DELIVERY** flips orders to `on_the_way`, streams live ETA to customers, back-fills customer status timeline, tightens location heartbeat to 10 s.
- **Journey persistence** across logout/login. Customer name on every stop.
- **Proof-of-delivery photo** capture (camera → gallery fallback) → marks delivered → notifies owner (email + SMS).

### 🖥️ Admin Web Portal (`/admin`)
| Page | What it does |
|------|--------------|
| `dashboard` | Live KPIs / overview |
| `orders` | Manage orders, status changes, one-click driver assignment, proof-of-delivery |
| `master-menu` | Single source of truth — all dishes with AI descriptions + AI food photos |
| `menu` | Weekly-menu builder (À la carte / Weekly Package / Complimentary / Always Available tabs, pricing modes) |
| `catering` | Catering package configurator v2 (choice groups, tiers, premium add-ons) |
| `coupons` | Full CRUD for discount coupons (percent/fixed, first-order-only rule) |
| `customers` | Customer list |
| `delivery` | Delivery-partner onboarding + order assignment (auto-polls) |
| `settings` | Payment methods, per-method HST, tax, loyalty rates, **referral rewards**, Twilio/notification config |
| `billing` | Billing / platform tenant info |
| **New Order** modal | Manually place an order on behalf of a customer (search/inline-add customer, items, delivery, payment, optional driver) |

---

## 🔌 Integrations

| Service | Used for | Key location |
|---|---|---|
| **Emergent Google OAuth** | Customer sign-in (session-token pattern) | Emergent-managed |
| **Emergent LLM** (GPT + Gemini **Nano Banana**) | AI menu descriptions + food photos | `EMERGENT_LLM_KEY` |
| **Resend** (Emergent-managed) | Order / owner notification emails | `EMERGENT_EMAIL_KEY` |
| **Twilio** | Order SMS notifications | credentials in DB `business_settings` |
| **Stripe** | Hosted checkout | `STRIPE_API_KEY` |
| **Google Maps** | Directions, Geocoding, Distance Matrix, Places Autocomplete, Static + JS maps | `GOOGLE_MAPS_API_KEY` / `EXPO_PUBLIC_GOOGLE_MAPS_API_KEY` |
| **Emergent Push** | Push notifications (native builds only) | `EMERGENT_PUSH_KEY` (placeholder until deploy) |

> ⚠️ **The Stripe key in `backend/.env` may be a LIVE key.** Any end-to-end checkout will charge real money. Swap to a test key before QA checkout flows.

---

## 🚀 Quick start (local dev)

### Prerequisites
- Python 3.11+ · Node 20+ · **Yarn 1.22** (see `packageManager` in `package.json`)
- MongoDB on `mongodb://localhost:27017`
- Google Maps API key (Directions + Geocoding + Distance Matrix + Places enabled)

### Backend
```bash
cd backend
pip install -r requirements.txt
# create backend/.env (see Environment variables below)
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```
All routes are prefixed with `/api/*`. Root probes: `GET /health`, `GET /healthz`.

### Frontend (Customer app — default)
```bash
cd frontend
yarn install
# create frontend/.env (see below)
yarn start          # Metro dev server
```

### Switch to the Delivery Partner app
Set `APP_VARIANT=delivery` in `frontend/.env` and restart Metro.
_Shortcut in dev:_ a "Delivery Partner sign-in" link at the bottom of the customer login page opens the delivery flow without restarting.

### Admin Web Portal
Open `/admin` in a browser (web build only — not shipped to app stores). Log in with the seeded admin account.

---

## 🔑 Environment variables

### `backend/.env`
```env
MONGO_URL="mongodb://localhost:27017"
DB_NAME="bonghneshel_db"
JWT_SECRET=...                    # admin/delivery JWT signing (fail-fast if unset)
INTEGRATIONS_FERNET_KEY=...       # encrypts tenant secrets stored in DB
ADMIN_EMAIL=admin@bong-hneshel.ca
ADMIN_PASSWORD=...                # seeds the admin account on startup
REVIEWER_EMAIL=reviewer@bong-hneshel.ca   # optional App Store reviewer account
REVIEWER_PASSWORD=...
STRIPE_API_KEY=sk_...             # ⚠️ may be LIVE
GOOGLE_MAPS_API_KEY=AIza...
EMERGENT_LLM_KEY=...              # AI menu descriptions + photos
EMERGENT_EMAIL_KEY=...            # Resend (Emergent-managed)
EMERGENT_PUSH_KEY=...             # placeholder until deploy
EMAIL_FROM=orders@bong-hneshel.ca
EMAIL_FROM_NAME="Bong Hneshel"
PUBLIC_BASE_URL=...               # used in emails/invoices/tracking links
APP_VARIANT=customer
```

### `frontend/.env`
```env
APP_VARIANT=customer                       # or "delivery"
EXPO_PUBLIC_GOOGLE_MAPS_API_KEY=AIza...     # used by RouteMap + tracking
# EXPO_PACKAGER_PROXY_URL / EXPO_PACKAGER_HOSTNAME / EXPO_PUBLIC_BACKEND_URL
# are managed by the environment — do NOT edit.
```

> Never commit real `.env` files — they're gitignored.

---

## 👤 Seeded accounts

| Role | Email | How it's created |
|------|-------|------------------|
| **Admin** | `admin@bong-hneshel.ca` | Seeded on startup from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (portal `/admin`) |
| **Reviewer** | `reviewer@bong-hneshel.ca` | Seeded on startup from `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` (App Store review) |
| **Delivery Partner** | `delivery@bong-hneshel.ca` | Seeded by `POST /api/dev/seed` (admin-gated) — "Rahul Das" |
| **Customer** | — | Guest checkout **or** Google sign-in (no password) |

Actual dev passwords live in `memory/test_credentials.md` (kept out of the public repo). **Rotate all secrets before production.**

---

## 🛠️ Tech stack

| Layer | Tech |
|---|---|
| Mobile & Web frontend | React Native **0.86.3** + Expo Router (**SDK 57**), React **19.2.3**, TypeScript, Reanimated 4, react-native-webview |
| Icons | `@react-native-vector-icons/ionicons` (Ionicons.ttf bundled in `assets/fonts/` for prod web) |
| Backend | FastAPI, Motor (async MongoDB), Pydantic v2 |
| Database | MongoDB (`DB_NAME=bonghneshel_db`) |
| Auth | Customer: Google OAuth (Emergent) + email/password + guest, all issuing one opaque session token; JWT for admin + delivery; bcrypt password hashing; 6-digit email password reset |
| Payments | Stripe Checkout · PayPal · Cash on Delivery · Interac e-Transfer |
| Maps | Google Directions / Geocoding / Distance Matrix / Places / Maps JS (WebView + iframe) |
| AI | Emergent LLM — GPT (descriptions) + Gemini Nano Banana (food photos) |
| Notifications | Resend email + Twilio SMS + Emergent push |

---

## 🚢 Deployment

Ships via Emergent's one-click **Publish** flow:

1. **Publish with `APP_VARIANT=customer`** → *Bong Hneshel* iOS + Android + Web builds.
2. **Publish again with `APP_VARIANT=delivery`** → separate *Bong Hneshel Delivery* iOS + Android build (own bundle ID).
3. **Admin Web Portal** ships alongside the web build under `/admin/*`.

**Production web note:** `node_modules` is stripped in the mobile-build pipeline, so the Expo web bundle is pre-built into **`backend/web_dist/`** and served by the backend (SPA catch-all). Diagnostic: `GET /api/health/web-bundle`.

Backend + MongoDB deploy together as a single container.

---

## 🧪 Testing

- **Backend API suite:** `cd backend && python -m pytest tests/api` (or `./run_api_tests.sh`). Feature suites live in `backend/tests/` (payments, journey backfill, weekly enhancements, manual order, etc.).
- **Integration reports:** `test_reports/iteration_*.json` (gitignored).
- **Manual smoke notes:** `test_result.md`.
- All screens expose `testID` props for Playwright/Detox automation.

---

## 🔁 Rebranding to a new tenant

This app is multi-tenant-friendly. To spin up a new brand, edit **`brand.json`** + **`frontend/brand.config.js`** (identity, colours, contact, region, native bundle IDs) — never hand-edit hardcoded strings. See **`TENANT_ONBOARDING_PROMPT.md`** for a step-by-step reusable prompt.

---

## 📄 License & contact

Private / commercial. Contact **support@bong-hneshel.ca**.

Made with 🌶️ in the GTA.
