# Curry & Co. — Product Requirements (MVP)

## Overview
Curry & Co. is a Bengali/Indian cloud-kitchen food delivery mobile app serving the Greater Toronto Area (GTA). MVP scope: **Customer Mobile App + Backend APIs**. Admin portal and Delivery Partner apps are stubbed / represented via signup form.

## Business Rules
- **Weekly menu rotation:** A new weekly menu becomes active every Sunday.
- **Ordering window:** Sunday to Thursday.
- **Delivery windows:** Friday evening (6–9 PM) and Saturday morning (9 AM–12 PM).
- **Admin future-week uploads:** menus can be seeded/uploaded for future weeks via `POST /api/menu/upsert` with `week_start` (Sunday ISO date).

## Features Delivered
1. Google Sign-In via Emergent-managed OAuth.
2. Home with current week hero, chef's featured, this-week bento grid, catering teaser, upcoming weeks.
3. À-la-carte menu with category chips (all/rice/curry/veg/starter/dessert).
4. Catering packages by guest count (10, 20, 50) with detailed inclusions.
5. Cart with per-item stepper, coupon input, loyalty-point redemption, delivery slot picker.
6. Delivery address form with map placeholder.
7. Order creation via authenticated API, Stripe hosted checkout in WebBrowser.
8. Order status polling & rich order tracking (map placeholder + vertical timeline).
9. Loyalty rewards: earn 1 pt per $1 subtotal on paid orders; redeem 100 pts = $1 off (in 100-pt increments).
10. Coupons (percent/fixed) with min-order threshold.
11. Delivery partner application form (unauthenticated intake).
12. Push notification enable-flow with Emergent-managed relay.
13. Email notifications (MOCKED — logged only, ready to swap with SendGrid/Resend).
14. Order status admin simulator endpoint (`POST /api/orders/{id}/status`) sends push updates.

## Data Model (MongoDB)
- `users` — user profile + loyalty_points
- `user_sessions` — TTL-indexed session tokens
- `weekly_menus` — one per Sunday (week_start unique), embedded menu items
- `catering_packages` — global packages by guest count
- `coupons` — code, discount_type (percent/fixed), value
- `orders` — user_id, items_snapshot, address, slot, totals, status, tracking_events
- `payment_transactions` — Stripe session tracking
- `delivery_applications` — partner applications

## APIs (see /api prefix)
Auth: `/auth/session`, `/auth/me`, `/auth/logout`
Menu: `/menu/current`, `/menu/upcoming`, `/menu/history`, `/menu/upsert`, `/catering`
Coupons: `/coupons/{code}`
Orders: `/orders/quote`, `/orders`, `/orders/{id}`, `/orders/{id}/status`
Checkout: `/checkout/session`, `/checkout/status/{sid}`, `/checkout/webhook`
Delivery Partner: `/delivery-partner/apply`
Push: `/register-push`
Dev: `/dev/seed`

## Integrations
- **Emergent Google OAuth** — session-token pattern.
- **Stripe (via emergentintegrations)** — hosted checkout session, opened via `expo-web-browser`. Uses `STRIPE_API_KEY` (pre-provisioned).
- **Emergent Push (SuprSend relay)** — `EMERGENT_PUSH_KEY` (placeholder; replaced at deploy).
- **Google Maps** — placeholder; live tiles pending API key from user.
- **Email** — MOCKED via log lines. Ready to plug SendGrid/Resend.

## Deferred (future)
- Admin web portal (RBAC, analytics dashboard, coupon CRUD, menu upload UI, reporting).
- Delivery partner mobile app (accept/reject, live location).
- Real-time order tracking via WebSockets + live map.
- Email provider integration (SendGrid/Resend).
- Guest checkout (currently requires Google Sign-In).

## Non-blocking notes
- Payments: uses Stripe test key `sk_test_emergent`. Real card test flow requires webhook or status polling — implemented.
- Push works only in dev/prod builds (not Expo Go). Backend endpoints are wired regardless.

## Wave 2 — Catering v2 (June 2026)
- CateringPackage schema (server.py) now supports: `choice_groups[]`, `upgrade_tiers[]` (with `group_overrides`), `premium_items[]` (per-person upcharge), `included_master_ids[]`, `is_custom_quote`, `contact_email/phone`. All choice options are Master Menu references (item_id).
- New endpoints: `GET /api/catering/{id}` (package + resolved master item map), `POST /api/catering/quote-request` (Shonar Bangla contact form).
- `POST /orders/quote` and `POST /orders` accept `catering_selections: {tier_id, group_selections, premium_selections}` and compute `line_total = (tier_price + premium_upcharge) × guests`. Validates min guests, group Min/Max, blocks orders for custom-quote packages.
- Customer app: `/catering/[id]` — hero, guest count stepper, tier picker (radio), choice groups (grid of master-menu items with images + veg dots), premium add-ons, always-included list, sticky footer total, Add-to-Bag. Login required for regular packages (guest → alert → /login).
- Custom Quote UI: contact form (name, email, phone, guest count, event date, notes) → `/api/catering/quote-request` → success alert.
- Admin app: `/admin/catering` — full v2 editor. Sections: Basic info (emoji, tagline, perfect_for, custom-quote toggle), What's inside (free-text), Choice groups (+add / +Master picker), Upgrade tiers (price + per-group Min/Max overrides + default toggle), Always included (Master picker), Premium add-ons (Master picker + upcharge input).
- Master Menu extras seeded (30+ items): snacks, beverages, additional veg/non-veg mains, rice/bread, desserts, accompaniments.

## Wave 3 — Weekly Menu Modes: À la carte + Package (June 2026)
- Backend: `WeeklyMenu` now has `alacarte_enabled`, `package_enabled`, and an optional `package: {name, description, price_cents, pick_count, eligible_master_ids[], image_url}`.
- New endpoint: `POST /api/admin/menus/{week_start}/settings` — updates toggles + package (enforces "at least one mode must remain enabled").
- New order kind `weekly_package` in `_resolve_items`: validates picks are in eligible pool and count == pick_count. `line_total = package.price_cents × qty`.
- Seed idempotency: preserves admin-set toggles, package, and `menu_id` across re-seeds.
- Customer Home tab: dark "WEEKLY COMBO" hero card when package enabled — routes to `/menu/package/{menu_id}`.
- Customer Menu tab: segmented control ("À la carte" / "Weekly Package") when both modes enabled; hidden and mode forced otherwise. Package view shows the hero with "Save ~$X" estimated savings chip.
- New screen `/menu/package/[id]`: pick X items with progress chip, live savings vs à la carte, sticky footer total, Add to Bag.
- Admin Weekly Menu: "Customer view mode" panel with two toggles + package editor modal (name, X, price, image, eligible items segment: all/specific). Save enforces validation.

## Wave 4 — Delivery Partner App + Live Tracking (June 2026)
- New `DeliveryPartner` model + demo partner (`delivery@curryandco.local` / `curry@delivery2026`, Rahul Das).
- Backend Google Maps integration: `_google_geocode()`, `_google_directions_optimize()` with `waypoints=optimize:true`, Static Maps API for map previews.
- New Order fields: `delivery_partner_id`, `delivery_status` (unassigned → assigned → picked_up → on_the_way → arrived → delivered), `delivery_partner_name/phone`, `delivery_partner_lat/lng/updated_at`, `delivery_eta_seconds`, `delivery_route_order`.
- Admin endpoints: partner CRUD (`/api/admin/delivery-partners`), order assign (`POST /api/admin/orders/{id}/assign`), plus `statuses=` filter on `/api/admin/orders`.
- Partner endpoints (separate JWT): `/api/delivery/login|me|orders|location|orders/{id}/status|route`.
- Customer tracking endpoint: `GET /api/orders/{id}/tracking` (partner name+phone, live lat/lng, ETA, tracking events, destination).
- Admin `/admin/delivery` page: Partners tab (create/edit/pause/delete) + Assign Orders tab (unassigned + assigned lists, assign modal). Auto-polls every 15s.
- Delivery Partner App at `/delivery-partner`: standalone login → dashboard with "My orders" + "Route planner" tabs. Order cards show next-action button flowing through statuses; call/navigate quick actions. Route planner: origin lat/lng or "Use my location" → Optimize → Google-optimized ordered stops with per-stop ETA + Static Maps preview.
- Customer `/order/[id]`: new "Live tracking" card (red pulse + driver avatar + ETA chip + call button + Static Map with D/H markers) — polls every 15s while `out_for_delivery`.
- Env: `GOOGLE_MAPS_API_KEY` set in backend/.env, `EXPO_PUBLIC_GOOGLE_MAPS_API_KEY` in frontend/.env.
- Push notifications on assignment/status changes remain MOCKED (log-only).

## Wave 4b — Multi-App Build Variants (June 2026)
- One Expo codebase now produces THREE surfaces:
  1. **Customer App** (iOS + Android) — `APP_VARIANT=customer` (default). Bundle `com.emergent.curryecosystem.nes404`, name "Curry & Co.".
  2. **Delivery App** (iOS + Android) — `APP_VARIANT=delivery`. Bundle `com.emergent.curryecosystem.delivery`, name "Curry & Co. Delivery".
  3. **Admin Portal** (Web only) — served at `/admin` on the web bundle (either variant).
- Migration: `app.json` → `app.config.js` reads `process.env.APP_VARIANT` and swaps name/slug/bundleId/icon/scheme/permissions. Variant exposed to JS via `Constants.expoConfig.extra.appVariant`.
- Runtime routing enforcement in `/app/frontend/app/_layout.tsx`:
  * Delivery-variant native build → any non-`/delivery-partner` path is redirected to `/delivery-partner`.
  * Customer-variant native build → admin/`/delivery-partner` paths redirect to `/` (only on native — web preview leaves everything reachable for QA).
- `delivery-partner.tsx` hides customer back-button and adjusts padding when running standalone (`APP_VARIANT==="delivery"`).
- `.env`: added `APP_VARIANT=customer` for dev preview default. Set to `delivery` before running the Delivery build.
- Delivery-variant Android permissions expanded (ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, ACCESS_BACKGROUND_LOCATION); iOS Info.plist has NSLocationWhenInUse + NSLocationAlwaysAndWhenInUse strings tailored for delivery use case.
- Publishing workflow: run Emergent Publish TWICE — once with `APP_VARIANT=customer` (Customer app), once with `APP_VARIANT=delivery` (Delivery app). Each generates its own iOS/Android build with a distinct bundle ID. Web admin portal ships alongside the customer web preview (or a full-stack web deploy).

## Wave 4d — Journey Persistence + Customer Name on Stops (June 2026)
- **Persistent journey on the delivery partner doc**: `POST /api/delivery/journey/start` now saves the full route snapshot (`journey_stops`, `journey_polyline`, `journey_origin_lat/lng/address`, `journey_total_duration_sec`, `journey_optimized`, `journey_order_ids`) so if the driver logs out and back in, the exact same plan is restored.
- **New endpoint**: `GET /api/delivery/journey/current` returns `{active, journey}` — the delivery app calls this on mount and if `active` restores origin, stops, polyline, banner state (started_at → elapsed minutes).
- **journey/end** now `$unset`s all persisted route fields so the next journey starts clean.
- **Customer name enrichment**: `GET /api/delivery/orders` batch-resolves linked `User.name` (priority: `address.name` → `user.name` → "Guest") and returns a `customer_name` field on each order.
- **Stop tile UI**: each stop card now shows a person-icon + customer name (primary-colored) between the "Stop N · ETA" header and the address line.
- **My Orders tab** also uses the resolved `customer_name` on order cards.
- Added a lightweight "Restoring your route…" splash inside the Route Planner while the initial journey fetch is in flight.

## Wave 4e — Bag Screen: Google Address Autocomplete + Saved Address (June 2026)
- **Google Places Autocomplete** — new `src/components/AddressAutocomplete.tsx` component provides live address suggestions as the customer types (min 3 chars, 260ms debounce, session-token cost optimization). Country-restricted to Canada. Backend proxies keep the API key server-side: `GET /api/places/autocomplete?q=…` and `GET /api/places/details?place_id=…`.
- **Auto-fill structured fields on pick** — selecting a suggestion parses Google's `address_components` and auto-populates `line1`, `city`, `postal_code`, `province` on the Bag screen (with lat/lng captured for potential future use). User can still hand-edit any field.
- **Persisted default address**:
  - **Logged-in customers** — `POST /api/orders` now auto-saves the delivery address as `default_address` on the User doc; served back via `/api/auth/me`; Bag screen pre-fills it on mount. New manual endpoints `POST /api/me/address` and `DELETE /api/me/address` are available for future "Manage addresses" UI.
  - **Guest customers** — Bag screen persists the address to AsyncStorage (`curryco.guest_address.v1`) on order placement; re-hydrated on next mount.
- **UX polish** — "Using your saved address — edit anytime" bookmark hint appears below the input when the field matches the saved copy.

## Wave 4f — Customer Name Everywhere Alongside Order ID (June 2026)
- **Best practice, applied globally**: everywhere an order ID appears in the Admin Portal, the customer name is now shown right beside it (with a person-icon accent).
  - Admin `/admin/delivery` — "Assign orders" list + "Assign to a partner" modal subtitle now lead with the customer name.
  - Admin `/admin/orders` — the top pill row shows `👤 Customer Name · #ORDID · STATUS · METHOD`.
  - Delivery Partner app — already ships the resolved `customer_name` on stop tiles + My Orders card (Wave 4d).
- **Backend**: `GET /api/admin/orders` now batch-resolves linked users and returns a `customer_name` field on every order (priority: `address.name` → `user.name` → "Guest") — same pattern as `/api/delivery/orders`.

## Wave 4g — Delivery App: Address Autocomplete on Start Location (June 2026)
- Replaced the plain `TextInput` on the Delivery Partner's Route Planner "Start location" with the same **`AddressAutocomplete`** component used in the customer Bag screen.
- Optimization: because `GET /api/places/details` returns lat/lng, picking a suggestion **skips the `/delivery/geocode` round-trip entirely** — start location is set instantly.
- Same UX: 260 ms debounce, Canada-restricted, session-token cost optimization, "powered by Google" attribution.

## Wave 4h — Per-leg ETA & Deep-Link (June 2026)
- **Stop tiles now show leg-by-leg ETA**: Stop 1 = `Start → A · X min`, Stop 2 = `A → B · Y min`, Stop 3 = `B → C · Z min`, … (uses the backend's already-returned `duration_sec` per stop). Cumulative "Total X min from start" kept on the meta line for context.
- **Deep link "Open in Google Maps" respects the previous stop as origin**: tapping Stop 3 opens driving directions from B → C (not Start → C). Uses `route.stops[i-1]` as origin for i ≥ 1.
- Distance shown per tile (`X.X km`) is already the leg-only distance (no change needed on that field).


## Wave 4i — Customer Live Tracking: "N stops away" + smart ETA (June 2026)
- **Backend**: `GET /api/orders/{id}/tracking` now computes `stops_away` by counting how many other on-route orders (`assigned/picked_up/on_the_way/arrived`) on the same delivery partner have `delivery_route_order` less than this order. Also returns `leg_duration_sec` (time for the immediate previous → this stop) alongside the cumulative `eta_seconds`.
- **Persistence**: `POST /api/delivery/route` now stamps `delivery_leg_duration_sec` and `delivery_leg_distance_m` on each order so per-leg time is available to tracking without another Directions call.
- **Frontend UX** (`/order/[id]` → Live tracking chip):
  - `stops_away === 0` (driver is heading directly to you) → **green chip**: `Arriving in ~12 min` (uses `leg_duration_sec` if present, falls back to cumulative eta).
  - `stops_away > 0` → **dark chip**: `N stops away · ~X-Y min`. Window is `perStop × (away + 1)` rounded to the nearest 5-min bucket ±30%. Keeps the customer honest without over-committing.
  - `delivered` → chip hidden.



## Wave 4j — Bug fixes: zoomable customer map + status auto-tick + green delivered tile (June 2026)
- **Customer live-tracking map is now interactive/zoomable** — swapped the static `staticMapUrl()` Image on `/order/[id]` for the same `RouteMap` component used in the delivery app. Added optional `originLabel` / `originTitle` props to `RouteMap` (defaults `S`/`Start`) so it can be reused with a **`D` (Driver)** marker + **`H` (Home)** stop. Pinch/scroll/zoom-controls all work.
- **Timeline auto-tick on START DELIVERY** — `POST /api/delivery/journey/start` now iterates each flipped order and **back-fills the customer's status timeline** (`preparing → packed → out_for_delivery`). Only missing steps are appended (idempotent — subsequent calls do not duplicate). Verified with new pytest suite `/app/backend/tests/test_journey_backfill.py`.
- **Delivered stop tile turns green in delivery app** — new `stopCardDelivered` (light green background + green border) + `stopIndexDelivered` (green circle) styles; letter A/B/C is swapped for a white ✓ once done. Also fixed the detection: an order that has been filtered out of `/delivery/orders?status=active` (because it just flipped to `delivered`) is now correctly treated as delivered by the tile.


## Wave 5 — Production deployment: Admin webapp bundled inside backend (August 2026)
- **Root cause of `/admin` 404 in production**: Emergent's mobile-build pipeline only ships `/app/backend/` — not `/app/frontend/`. So neither postinstall hooks nor startup builds could produce the Expo web bundle in the production container.
- **Fix**: pre-built Expo web bundle is now stored at **`/app/backend/web_dist/`** (6 MB, includes `index.html`, `_expo/static/js/web/entry-*.js`, `assets/`, `favicon.ico`). This ships INSIDE the backend image.
- Backend now resolves the dist location at import time with fallback priority: `/app/backend/web_dist/` (production) → `/app/frontend/dist/` (preview).
- Startup helper `_try_build_web_bundle()` in `/app/backend/server.py`: if neither location has `index.html`, attempts `npx expo export --platform web --output-dir dist` (with `yarn install` if node_modules missing) and mirrors preview → prod dir. Times out gracefully at 240s.
- New root-level endpoints: `GET /health`, `GET /healthz`, `GET /` — required for K8s liveness/readiness probes.
- New diagnostic endpoint: `GET /api/health/web-bundle` returns `{present, source, dist_size_bytes, prod_dir_exists, preview_dir_exists, frontend_source_shipped, npx_available, yarn_available}` for zero-shell production debugging.
- SPA catch-all mounted after `include_router(api)`: serves `index.html` for `/admin/*`, `/customer/*`, `/order/[id]`, etc. Static mounts for `/_expo/*`, `/assets/*`, `/favicon.ico`. Reserved prefixes (`api/`, `_expo/`, `assets/`, `docs`, `openapi.json`, `redoc`, `health`, `healthz`) explicitly excluded from SPA fallback.
- Tests (iteration 17): 9/9 pass including production simulation (moved `/app/frontend` away, verified backend still serves `/admin` HTML from `/app/backend/web_dist`).
- Env: `EXPO_PUBLIC_BACKEND_URL` unchanged per Emergent Support directive; `JWT_SECRET` / `ADMIN_PASSWORD` fail-fast if unset; `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` control App Store reviewer account seeding.



- **Zoomable Google Map**: replaced Static Maps `<Image>` with a live Google Maps JS map via `react-native-webview` on native and an `<iframe srcDoc>` on web (`/app/frontend/src/components/RouteMap.tsx`). Supports gesture zoom/pan, greedy gesture handling, custom S/A/B/C markers, decoded polyline. Uses `libraries=geometry` for polyline decoding.

## Wave 4k — Payment Methods · per-HST · Interac (June 2026)
- **Backend**: new `PaymentMethodConfig` model + `payment_methods` on `BusinessSettings` (defaults for stripe/paypal/cod/interac). Helper `_tax_enabled_for_method(settings, method)` powers per-method HST in `POST /orders/quote` + `POST /orders`. New `interac` payment path — order is confirmed on placement (like COD) with `payment_status="interac_pending"`. Public `GET /api/settings` filters secrets (never returns `secret_key`/`client_secret`).
- **Admin `/admin/settings`**: new "Payment Methods" section, 4 cards (Stripe / PayPal / COD / Interac). Each card has:
  - Enable toggle
  - Charge HST toggle
  - Method-specific inputs (Stripe pk/sk, PayPal client_id/secret, Interac email + free-text instructions)
- **Customer `/cart`**: fully data-driven — only enabled methods render. Interac selected → inline yellow banner shows the Interac email + instructions. Placing an Interac order pops a full-screen modal with `SEND EXACTLY $X`, the Interac email, and the message-to-attach (`Order <order_id>`); "I've sent the transfer" routes to the order page. `fetchQuote()` sends `payment_method` so tax updates in real time when the user switches.
- **Order page `/order/[id]`**: Interac orders now use the same confirmed timeline as COD (no more misleading "Payment pending" banner). Card/Stripe remains the only prepaid flow.
- Tests: 11/11 pytest cases in `/app/backend/tests/test_payment_methods.py` pass (secrets filtered, per-method tax, interac creation).

- **Clickable stops**: tapping a stop card deep-links to Google Maps with driving directions from the resolved origin to the stop's lat/lng (`https://www.google.com/maps/dir/?api=1&origin=…&destination=…`).
- **Reorderable stops**: `⬆⬇` chevron buttons on each stop card. On tap, list swaps optimistically, then backend `/api/delivery/route` is called again with `optimize: false` — Google Directions is queried with the manual waypoint order so ETA & polyline reflect the chosen sequence.
- **Backend**: `DeliveryRouteReq` now accepts `optimize: bool = True`; `_google_directions_optimize()` conditionally strips `optimize:true` from waypoints; endpoint sorts resolved orders by `req.order_ids` order when optimize is False.
- **START DELIVERY button**: new endpoint `POST /api/delivery/journey/start` accepts `order_ids` + origin. Bulk-flips all matching orders from `assigned/picked_up` → `on_the_way` (also flips outer `status` to `out_for_delivery`), records `journey_started_at`, stamps `delivery_partner_lat/lng` so the customer `/api/orders/{id}/tracking` endpoint returns fresh ETA immediately. `POST /api/delivery/journey/end` clears the journey state.
- **Live journey UX**: after START DELIVERY the location heartbeat interval tightens from 30s → 10s; UI switches to "Journey in progress" banner with elapsed minutes; stop reordering is locked; auto-end when every stop is delivered.
- **New dependency**: `expo-location@19.0.8` (installed for future switch to expo-location, currently the delivery app uses navigator.geolocation which is enough on web + Expo Go).





## Wave 6 — Admin "New Order" module + null-email fix (August 2026)
- **Feature (Admin Portal)**: New Order modal (`/app/frontend/src/components/NewOrderModal.tsx`) lets admins manually place orders on behalf of customers. Single sheet, 4 sections: Customer (search existing or inline-add with name+phone), Items (à la carte / weekly combo / catering), Delivery (slot chip picker + address), Payment (COD/Interac/Card + mark-paid toggle + optional driver assignment which auto-flips status to `packed`).
- **New endpoints**:
  - `GET /api/admin/order-builder` — one-shot bundle (`delivery_slots`, `master_menu`, `weeks`, `catering`, `delivery_partners`, `settings`).
  - `POST /api/admin/customers` — inline customer create (name+phone required, email optional; dedupes on phone/email).
  - `POST /api/admin/orders/create` — manual order create; supports existing `user_id` or `new_customer`; totals reconcile per method-tax config; auto-`packed` when driver_partner_id supplied.
- **Bug fix — null-email regression**: legacy `users.email_1` was a plain unique index that E11000'd on the 2nd phone-only customer. Fix: (1) startup migration `db.users.update_many({email:null},{$unset:{email:1}})`, (2) drop + recreate as **partial-unique** `partialFilterExpression:{email:{$type:'string'}}`, (3) both admin_create_customer + admin_create_manual_order now omit `email` from the insert doc when None.
- **Tests**: 29/29 backend cases green — `test_manual_new_order_iteration20.py` (26) + `test_iteration21_null_email_verify.py` (3). Preserves email-uniqueness for real emails while allowing unlimited phone-only customers.


---
## Rebrand → Mustard Garden (2026-09-03)
- Tenant: **Mustard Garden** — "Exotic Flavors of India", Milton, ON (+1 437-499-9453).
- Assets added to `frontend/assets/brand/`: logo.png, logo-square.png, splash.png, adaptive-icon.png, notification-icon.png (phone/address band cropped off source).
- Palette auto-derived from logo-square.png: primary #FBB03B, primaryDark #C98D2F, secondary #5D1114, accent #2F4F4F.
- Edited only `brand.json` + `frontend/brand.config.js` (identity, colors, contact, region CA/CAD/Toronto, native bundle IDs com.mustardgarden.*, copy). Platform tenant_id/api_key left empty (not registered).
- Regenerated `backend/.env` JWT_SECRET + INTEGRATIONS_FERNET_KEY. Stripe/Maps/Email/Twilio left blank per request.
- KNOWN template hardcodes (NOT edited, out of scope): login/admin avatar letter "C" (should be BRAND.name[0]); login hero copy still says "Bengali cloud kitchen / Kolkata classics"; native launcher icon+splash still read from assets/images/* in app.config.js.


---
## Master Menu built from 5 weekly posters (2026-09-03)
- 55 unique dishes (deduped) inserted into `master_menu` from the Jul27/Aug3/Aug10/Aug17/Aug24 posters.
- Categories: 24 main-veg, 22 main-non-veg, 3 side, 2 rice, 2 bread, 1 dessert, 1 starter (incl. complimentary items + add-ons Roti/Mughlai Paratha/Kolkata Rolls/Biryani).
- Each item: AI description (GPT) + AI food photo (Gemini Nano Banana) saved to /api/uploads/menu/, veg/non-veg from poster grouping, price 1599 cents ($15.99) placeholder (owner to tune).
- Set EMERGENT_LLM_KEY in backend/.env; menu_ai.py brand persona now uses BRAND_NAME.
- One-off build scripts: backend/build_mg_menu.py, fix_mg_images.py, fix_mg_text.py (sequential due to 1-concurrency key limit).


---
## Weekly Meal Plan — composition pricing (2026-09-03)
- New: WeeklyMenuPackage.pricing_mode="composition" with veg_price_cents/mixed_price_cents/nonveg_price_cents + complimentary_master_ids; MasterMenuItem.always_available.
- Rule: pick exactly 5 dishes -> all-veg $64.99 / any mix $69.99 / all-non-veg $79.99 (egg=non-veg). Backend _resolve_items computes it; unit + API tested (13/13 backend green).
- Complimentary (display-only, non-selectable): Gur er Payesh + Dal of the Week. Shown on builder + Menu-tab preview line.
- Order Anytime (always_available): Roti, Mughlai Paratha, Chicken/Mutton Biryani, Egg/Chicken/Mutton Roll (price = master default $15.99). New GET /api/menu/anytime + Menu-tab section.
- Published 24-Aug weekly menu for week_start=2026-08-30 (10 dishes). alacarte off, package on.
- Admin weekly-menu editor: Pricing-mode toggle (Flat / By veg-non-veg mix) + 3 price inputs, persists via /admin/menus/{week}/settings.
- Fixes after test: home hero composition price (index.tsx), guest Add-to-Bag now routes to /cart (was bouncing to login), admin login placeholder -> admin@mustardgarden.ca.
- One-off scripts: backend/build_weekly.py.


---
## Bug fixes (2026-09-03)
- Images not showing in Expo Go: backend returns relative /api/uploads paths (no origin on native). Added mediaUrl() in src/utils/backendUrl.ts (EXPO_PUBLIC_BACKEND_URL on native, window.origin on web) and wrapped every customer <Image> uri (index, menu, package/[id], cart, orders, order/[id], catering, catering/[id]). Verified: all rendered img src absolute, 0 relative /api srcs.
- Order Anytime added to Home page below Weekly Meal Plan hero (index.tsx fetches /menu/anytime, horizontal cards + add-to-cart). Verified via testing_agent iteration_15 (both fixed, no regressions).


---
## Delivery Policy feature (2026-09-03)
- Distance-based delivery fee from Milton (Google Distance Matrix): 0-20km FREE, 20-40km $5, 40-75km $10, >75km $15. compute_delivery_fee() in server.py; used by /orders/quote + /orders (falls back to flat if Maps down). Quote now returns delivery_distance_km, delivery_fee_tier, delivery_time_window (6AM-8PM), delivery_condo_policy.
- Delivery proof photo: POST /api/delivery/orders/{id}/proof (multipart) -> uploads/delivery/, sets order.delivery_proof_photo_url. Delivery app OrderCard "Photo & complete" captures via expo-image-picker (camera->gallery fallback, web blob-safe) then marks delivered.
- Owner notification on delivered: _notify_owner_delivered() -> Email (Emergent Resend) + SMS (Twilio from admin settings), best-effort (never blocks). notify to ADMIN_EMAIL + NOTIFY_PHONE_DEFAULT +14374999453.
- Admin Orders shows PROOF OF DELIVERY image; customer order screen shows order-proof-card; cart shows tiered fee (FREE label) + delivery policy box.
- Test delivery partner: rider@mustardgarden.ca / rider@2026. Verified: backend 4/4 (iteration_17), delivery UI + admin proof confirmed.
- Schedule (Monday GTA/Peel) deferred per user; time window + fee shipped now.

## Expo SDK 57 Upgrade (this session)
- Upgraded Expo SDK 54.0.36 -> 57.0.19 (React 19.2.3, React Native 0.86.3) via `expo install expo@latest` + `expo install --fix`.
- Removed deprecated `newArchEnabled` and `edgeToEdgeEnabled` keys from app.config.js (defaults in SDK 55+). Added recommended config plugins: expo-font, expo-image, expo-secure-store, expo-web-browser, @react-native-vector-icons/ionicons.
- Migrated icon library `@expo/vector-icons` -> `@react-native-vector-icons/ionicons@13.1.3` across 30 files (only Ionicons was used). Rewrote src/hooks/use-icon-fonts.ts to preload the bundled Ionicons.ttf via expo-font (removed old CDN font hack; the new lib supports Expo dynamic font loading).
- Aligned dev deps: typescript ~6.0.3, eslint-config-expo ~57.0.2, @types/react ~19.2.4. expo-doctor 20/20 pass, eslint clean.
- Verified by testing_agent (iteration_18): backend 5/5 APIs OK, all Ionicons render as real glyphs across login/home/menu/cart/admin, core customer+admin flows working. No regressions.

## Weekly Menu Enhancements (this session)
- Admin Weekly Menu split into 4 section tabs: À la carte · Weekly Package · Complimentary This Week · Always Available.
- New Week form: pick-a-Sunday date chips + manual field, optional name (default "Week of {date}"), checkbox "Copy all active Master items to À la carte" (copied lines are HIDDEN by default).
- À la carte: search + alphabetical + per-dish visibility toggle (customers see only visible dishes). Backend: WeeklyMenuLine.is_visible; _hydrate_menu filters hidden lines.
- Complimentary This Week: pick from Master Menu (WeeklyMenu.complimentary_master_ids); shown to customers ONLY when Weekly Package enabled. Home Weekly Combo tile shows up to 3 complimentary dishes (hidden when none).
- Always Available: ONE global list (BusinessSettings.always_available_master_ids), pick from Master, editable anytime; /menu/anytime uses it (fallback to legacy always_available master flag when empty). Customer "Order Anytime" renamed to "Always Available" on home + menu.
- Weekly Package "Pick specific dishes" now lists ALL master dishes alphabetically + searchable.
- Customer home + menu auto-live via 15s polling so admin changes reflect without manual refresh.
- New endpoints: POST /admin/menus/create, POST /admin/menus/{w}/complimentary, POST /admin/menus/{w}/lines/{id}/visibility, GET+POST /admin/always-available.
- Verified: testing_agent iteration_19 (backend 10/10 + full admin & customer UI). Tests: tests/test_weekly_enh_quick.py, tests/test_weekly_enh_iter19.py.

---
## Rebrand — Bong Hneshel (2026-09-15)
Tenant rebrand applied via config only (no UI-string hand-edits):
- `brand.json` + `frontend/brand.config.js`: identity, contact (bong-hneshel.ca), region (CA/CAD/America-Toronto), native bundle IDs (com.bonghneshel.*), copy, tagline "Home Food, Delivered".
- Palette auto-derived from logo (deep-purple monochrome): primary #3C053C, primaryDark #300430, secondary #1AA34A (180° emerald complement; raw algo fallback #11D311 toned for contrast), accent #2F4F4F.
- Assets regenerated in `frontend/assets/brand/`: Bong-Hneshel-Logo.jpg, logo-square.png, adaptive-icon.png, splash.png, notification-icon.png, plus mascot.png & login-bg.png refreshed.
- Backend secrets rotated: new JWT_SECRET + INTEGRATIONS_FERNET_KEY. Stripe/Maps/Email/Twilio left blank per request. Platform tenant_id/api_key cleared (poller short-circuits).

---
## Admin Coupons Management (2026-09-15)
New admin section to manage discount coupons (previously seed-only).
- New screen `frontend/app/admin/coupons.tsx` + sidebar nav "Coupons" (AdminShell) + route registered in admin/_layout.tsx.
- Backend CRUD in server.py after `/admin/settings`: `GET /admin/coupons` (list), `POST /admin/coupons` (create), `PUT /admin/coupons/{code}` (update/rename), `DELETE /admin/coupons/{code}` — all guarded by `_current_admin`.
- Coupon fields: code (uppercased), discount_type percent|fixed, value (percent 1-100 OR cents), active, min_order_cents, description, first_time_only.
- Rules enforced: unique code, percent 1-100, fixed >=1c, and ONLY ONE active first_time_only coupon at a time (2nd active first-time create/update -> 400 with helpful message). Reuses existing `_apply_coupon` so checkout math is unchanged.
- UI: list cards w/ badges (Active/Inactive, First order only, Min $), inline active toggle, edit/delete; modal editor with percent/fixed type chips, dollar inputs, active + first-order-only toggles. Web delete uses window.confirm.
- Also fixed stale old-brand placeholder email (mustardgarden -> bong-hneshel) on admin login.
- Verified: testing_agent (iteration_7 admin coupons) — backend 10/10 pytest + full admin UI e2e all PASS.

---
## Security Hardening (2026-09-15)
Fixed 4 findings from the security audit (all verified):
- SEC-001: `POST /api/menu/upsert` now requires `_current_admin` (was unauthenticated → price tampering). Not used by frontend (admin uses /admin/menus/*).
- SEC-002: `POST /api/orders/{id}/status` now requires `_current_admin` (was unauthenticated order-status tampering). Redundant with authed /admin/orders/{id}/status & /delivery/orders/{id}/status.
- SEC-003: `POST /api/dev/seed` now requires `_current_admin` (was unauthenticated destructive seed).
- SEC-004: XSS — `/api/invoice/{id}` and `/api/track/{id}` now HTML-escape all customer-supplied fields (name, address, phone, item names, coupon, slot) via `html.escape`. Verified: injected <script> renders as &lt;script&gt;.
- Refactor: moved `_current_admin` definition up (after `_current_user`) so earlier endpoints can depend on it.
- NOT fixed (env, per user): SEC-005 LIVE Stripe key + plaintext admin creds in .env — user chose to keep LIVE key.
Verified via curl: 3 endpoints return 401 unauth / 200 with admin token; admin/coupons regression 200; invoice+track return 200.

---
## README overhaul (2026-06)
- Rewrote stale `/app/README.md` (was branded "Curry & Co.", SDK 53, wrong DB/env names). Now fully documents Bong Hneshel: three-app architecture, full feature catalogue (customer/delivery/admin), all integrations, correct env vars (DB_NAME=bonghneshel_db, STRIPE_API_KEY, EMERGENT_* keys, REVIEWER_*), SDK 57 / RN 0.86.3 stack, seeded accounts, prod web_dist serving, pytest suite, rebranding pointer. Docs-only change; no code touched.
- Also supplied Apple 2.1 review-notes copy (purpose/audience/problem/value) for App Store Connect.

---
## Email + Password Auth (2026-06)
Added email/password login to the customer login screen (previously Google + guest only). Confirmed scope: sign-up + login + forgot/reset.
- Backend (`server.py`, via auth playbook): `POST /api/auth/register`, `/auth/login`, `/auth/forgot-password`, `/auth/reset-password`. Issues the SAME opaque `session_token` (prefixed `pw-`) as Google/guest via new helper `_issue_customer_session`, so `_current_user` is unchanged. Passwords hashed with existing passlib bcrypt (`_pwd`). Duplicate email → 409, wrong creds → generic 401, dummy-hash verify to equalize timing.
- Password reset = single-use 6-digit code emailed via Resend (`_email.send_email`), stored as sha256 hash in new `password_reset_codes` collection (TTL 15 min, max 5 attempts). On reset: sets new password_hash + invalidates all sessions.
- **This activates the seeded reviewer account** (`reviewer@bong-hneshel.ca`) which previously had a password_hash but no login route — fixes Apple's "provide working demo credentials" request.
- Frontend: `src/auth.tsx` gained `signInWithEmail`/`signUpWithEmail`; new screen `app/email-auth.tsx` (login/signup/forgot/reset modes); `app/login.tsx` "Continue with email" button; route registered in `app/_layout.tsx`.
- Verified: testing_agent iteration_8 — backend 16/16 + all frontend flows incl. reviewer login. Tests: `backend/tests/test_email_auth_iter8.py`.

---
## Signup phone + Add-phone-later + Welcome email + Loyalty gate (2026-06)
- **Optional phone on email signup**: `EmailRegisterReq.phone`; `/auth/register` stores it. Frontend `email-auth.tsx` signup form has an optional "Mobile number *optional" field + loyalty hint.
- **Add phone later (Profile)**: new `POST /api/me/profile` (auth) updates name/phone. `profile.tsx` gained a "Your details → Mobile number" row (Add/Edit) opening a bottom-sheet modal; saves then `refresh()`.
- **Welcome email (all new customers)**: `_send_welcome_email(user_doc)` helper fired via `asyncio.create_task` from BOTH `/auth/register` and `/auth/session` new-user branch. Best-effort (never blocks/errors signup). Dynamically includes the ACTIVE first_time_only coupon from Admin→Coupons if one exists; otherwise omits the offer line. Skips guest placeholder emails. NOTE: no first-order coupon exists in DB yet — owner must create one in Admin → Coupons (first-order-only) for it to appear in the email.
- **Loyalty gate (cart)**: `cart-loyalty-gate` nudge shown to logged-in members with no phone, inviting them to add one to earn points.
- Verified: testing_agent iteration_9 — backend 8/8 pytest + all frontend flows. Tests: `backend/tests/test_profile_welcome_iter9.py`. Minor non-blocking UX note: profile modal Save can sit below fold on small screens.

---
## Dynamic first-order banner (2026-06)
- `FirstOrderBanner.tsx` no longer hardcodes "10% OFF / FIRST10". It now fetches the active first-order coupon and renders its real code + discount (e.g. "20% OFF … WELCOME20"). Hides entirely if no active first_time_only coupon exists.
- Logged-in customers use eligibility-aware `GET /api/coupons/first-time` (null after they've ordered); guests/logged-out use new public `GET /api/coupons/promo`.
- Verified via curl (`/coupons/promo` → WELCOME20) + screenshot (guest home shows "20% OFF your first order — code WELCOME20").

---
## Referral / Invite program (2026-06)
Spec: referrer earns points on friend's FIRST PAID order; friend gets a first-order discount; share via unique code; amounts editable in Admin.
- Backend (`server.py`): `BusinessSettings` referral_enabled / referral_reward_points / referral_friend_discount_type / referral_friend_discount_value. Helpers `_gen_referral_code`, `_get_or_create_referral_code`, `_link_referral`, `_referral_discount`, `_maybe_reward_referral`. Endpoints `GET /api/referrals/me`, `POST /api/referrals/redeem`. `/auth/register` accepts `referral_code`. Friend discount folded into `discount` in quote + create_order. Referrer reward fired from BOTH loyalty-credit paths (COD/Interac + card finalize), idempotent via a claim on `users.referral_rewarded`. New collection `referrals` (unique invitee_id). Partial unique index on `users.referral_code` (only string values) — fixed a null-dup 500.
- Frontend: `app/invite.tsx` (code, share sheet, copy, stats, redeem box), `email-auth.tsx` signup referral field + `?ref=` deep link, Profile "Invite friends & earn" row, `admin/settings.tsx` Referral section.
- Verified: testing_agent iteration_10 — backend 19/19 pytest + all frontend/admin flows. Tests: `backend/tests/test_referrals_iter10.py`.
- Follow-up: coupon vs referral discounts now shown SEPARATELY at checkout. Quote/order return `discount_cents` (coupon only, labeled with coupon code) + new `referral_discount_cents` ("Referral bonus" line). Order model gained `referral_discount_cents`. Cart summary + tax denominator updated. Verified via curl (WELCOME20 20% = 400 + referral 10% = 200 shown separately on a $20 subtotal).
- Follow-up 2 (iteration_11): (A) invite banner on `/email-auth?ref=CODE` ("You were invited — enjoy X% off…"), (B) Bag `cart-savings` "You saved $X today" combining coupon+referral+points, (C) Admin `/admin/referrals` leaderboard (top referrers) + `GET /api/admin/referrals/leaderboard`, (D) Profile `profile-referral-bonus` card under loyalty balance (available/used) via extended `/referrals/me` (`you_were_referred`, `your_bonus_status`), (E) one-time bonus confirmed (first-order-only discount, idempotent reward, single referral link). Verified: testing_agent iteration_11 8/8 backend + 5/5 frontend. Tests: `backend/tests/test_referrals_iter11.py`.

---
## Web-bundle freshness guarantee (2026-06)
Root cause of "production shows stale UI": prod serves the committed `backend/web_dist/` (preferred over preview `frontend/dist/`), and the old `_try_build_web_bundle` fast-path never rebuilt when a stale prod bundle already existed — so the Sep-16 bundle (no Referrals/email-login/etc.) kept serving until manually rebuilt.
Fix (server.py, near SPA serving): fingerprint the frontend source (`app/`+`src/`+`app.config.js`/`brand.config.js`/`package.json`) → `_frontend_source_hash()`, stored as marker `backend/web_dist/.source_hash`. On startup `_maybe_schedule_web_refresh()` compares marker to live source; on mismatch it rebuilds in a background thread (`_do_web_export_and_mirror`, atomic dir swap) and writes the new marker. Result: (a) every deploy self-heals to latest code if stale, (b) dev backend restarts after a frontend change keep committed `web_dist` continuously fresh. Diagnostic `GET /api/health/web-bundle` now returns `committed_marker`, `current_source_hash`, `bundle_matches_source`. Confirmed `bundle_matches_source: true` with Referrals present.
NOTE for future agents: after any frontend change, restarting the backend auto-refreshes `web_dist`; verify `bundle_matches_source: true` before telling the user to publish.
