# Tenant Onboarding Prompt — Food‑Delivery App (Expo + FastAPI + MongoDB)

Paste the prompt below into a fresh agent session to reproduce, for a NEW tenant,
everything that was set up for "Bong Hneshel". Fill in every value inside `<<...>>`.
Remove any step you don't need. The agent should confirm the plan before running.

---

## 0) Fill‑in variables (edit before running)

```
TENANT_NAME        = <<Bong Hneshel>>
TENANT_SLUG        = <<bonghneshel>>            # used for db name + keys
PRIMARY_COLOR      = <<#3C053C>>                # brand primary (hex)
ACCENT_COLOR       = <<#C0392B>>                # brand accent (hex)
LOGO_SOURCE        = <<url or uploaded file>>   # square logo, PNG
REGION / TIMEZONE  = <<Greater Toronto Area / America/Toronto>>
DELIVERY_DAYS      = <<Friday>>
DELIVERY_WINDOW    = <<6:00 PM – 10:00 PM>>
CURRENCY / TAX     = <<CAD / HST 13%>>
MENU_CSV           = <<url or uploaded CSV: name,price,category,veg_type,description(optional)>>

# Integration keys the USER must provide (ask before implementing):
STRIPE_SECRET_KEY  = <<sk_test_... (USE A TEST KEY for QA — live keys charge real money)>>
GOOGLE_MAPS_KEY    = <<AIza...>>
TWILIO_SID         = <<AC...>>
TWILIO_AUTH_TOKEN  = <<...>>
TWILIO_FROM_NUMBER = <<+1...>>
# Resend email + all LLM/image generation use the Emergent‑managed keys (no user key needed).
```

---

## THE PROMPT (copy everything below)

> You are setting up a multi‑tenant food‑delivery app (Expo Router frontend, FastAPI
> backend, MongoDB) for a new tenant. Respond in English. Before writing code, restate
> the plan and ask me to confirm. Use the Emergent integration playbook expert for EVERY
> third‑party integration and for any auth work — never hand‑roll integrations. Ask me
> for the integration keys listed above BEFORE implementing those steps.
>
> Do the following, in order, testing each phase:
>
> **1. Boot & rebrand**
> - Clone/boot the base repo and get frontend + backend running.
> - Rebrand to `TENANT_NAME`: update `frontend/brand.config.js`, `frontend/brand.json`,
>   the app title in `app.config.js`, and `frontend/src/theme.ts` colors to
>   `PRIMARY_COLOR` / `ACCENT_COLOR`. Replace the logo with `LOGO_SOURCE`.
> - Derive the admin logo monogram from the brand name's first letter (do NOT hardcode a
>   letter). Sweep the codebase for any leftover previous‑tenant strings.
> - Point MongoDB at a fresh db `TENANT_SLUG_db` (via `DB_NAME` in `backend/.env`, do not
>   change `MONGO_URL`). Generate fresh tenant secrets (JWT, Fernet).
>
> **2. Third‑party integrations** (each via the integration playbook expert)
> - Stripe hosted checkout using `STRIPE_SECRET_KEY`. NOTE: a global container env var can
>   shadow the `.env` value — if Stripe fails to read the key, read `STRIPE_API_KEY`
>   directly from the parsed `.env` dict in `backend/server.py`.
> - Twilio SMS (store credentials encrypted with Fernet in `business_settings`).
> - Emergent‑managed Resend for transactional email.
> - Google Maps with `GOOGLE_MAPS_KEY`.
>
> **3. Menu import + AI enrichment**
> - Import `MENU_CSV` into a `master_menu` collection (fields: name, price_cents,
>   category, veg_type, description, image_url).
> - For rows missing a description, generate one with the Emergent LLM (GPT).
> - For every item, generate a product image with Gemini Nano Banana and store it in
>   Emergent Object Storage (never base64 in Mongo). Save the returned URL to `image_url`.
> - Surface Veg/Non‑Veg indicators on Home and Menu screens.
>
> **4. Ordering config**
> - Set delivery days = `DELIVERY_DAYS` and the delivery time window = `DELIVERY_WINDOW`
>   (single backend constant `DELIVERY_TIME_WINDOW`, also used as the cart display).
>   Ensure the selected delivery‑slot chip uses high‑contrast (white) text.
> - Tax = `CURRENCY / TAX`; make the HST label/rate adjustable and disabled by default
>   for Stripe.
> - Payment methods: Stripe, Cash on Delivery, Interac.
>
> **5. Loyalty points**
> - Backend earn/redeem logic + admin toggles in `business_settings`
>   (`loyalty_enabled`, `loyalty_earn_points_per_dollar`, `loyalty_redeem_points_per_dollar`).
> - Customer UI in Cart (redeem) and Profile (balance). Recompute all order totals
>   server‑side; never trust client prices; never let points/coupons drive a total below 0.
>
> **6. Coupons + first‑time offer**
> - `coupons` collection: code, discount_type (percent|fixed), value, active,
>   min_order_cents, description, first_time_only.
> - Seed a first‑time coupon (e.g. `FIRST10`, 10% off), logged‑in users only,
>   auto‑applied in cart, with a global promo banner across tabs.
> - Admin **Coupons** screen (`/admin/coupons`) with list + create/edit/delete/deactivate.
>   Enforce only ONE active first‑time coupon at a time (reject a 2nd with a clear 400).
>
> **7. Admin portal** (web‑only) — dashboard, master menu, weekly menu, catering, orders,
>   coupons, customers, delivery, billing, settings. Admin endpoints under `/api/admin/*`
>   MUST require the admin auth dependency.
>
> **8. Security hardening (apply these — they are real fixes)**
> - Require admin auth on `POST /api/menu/upsert`, `POST /api/orders/{id}/status`, and
>   `POST /api/dev/seed` (all are unauthenticated by default in the base repo).
> - HTML‑escape every customer‑supplied field rendered in the server‑side invoice
>   (`/api/invoice/{id}`) and tracking (`/api/track/{id}`) pages (use `html.escape`) to
>   prevent stored XSS.
> - Use a Stripe TEST key for QA; keep secrets in `.env` only.
>
> **9. Web icon‑font deploy fix (CRITICAL — do not skip)**
> - `@react-native-vector-icons` ships its `.ttf` under `node_modules`. Production deploys
>   strip `node_modules`, so the font 404s and every icon shows as an empty box (works in
>   preview, breaks in production). Fix by copying the font into the app's own assets:
>   `cp node_modules/@react-native-vector-icons/ionicons/fonts/Ionicons.ttf
>   frontend/assets/fonts/Ionicons.ttf` and load it in `src/hooks/use-icon-fonts.ts` via
>   `require("../../assets/fonts/Ionicons.ttf")` (keyed as `Ionicons`). Rebuild the web
>   bundle; verify the font exports to a top‑level `assets/assets/fonts/...` path (NOT
>   under `node_modules`).
>
> **10. Clean slate for QA (optional)**
> - Provide a script to wipe customers/orders/payments/loyalty/drivers/delivery/catering
>   requests/coupons while KEEPING menu, business settings, and admin — and keep any named
>   reviewer test account.
>
> **Finish:** run the testing agent on backend + the admin web flows, save admin/reviewer
> credentials to `/app/memory/test_credentials.md`, and tell me to click Publish → Deploy,
> then hard‑refresh, to see the deployed changes.

---

## Notes / gotchas learned during the Bong Hneshel build
- **Admin portal is web‑only** (`/admin`); the deployed admin is served from the FastAPI
  backend's `web_dist/` bundle — rebuild `web_dist` (via `npx expo export --platform web`)
  and re‑publish whenever admin UI changes.
- **Preview vs Production:** preview serves from the Metro dev server (live source);
  production serves the pre‑built `web_dist`. A change only appears in production after
  Publish → Deploy.
- **LIVE Stripe keys charge real money** — always QA with a test key or COD/Interac.
- **Push notifications** require a native build (won't work in Expo Go / preview).
