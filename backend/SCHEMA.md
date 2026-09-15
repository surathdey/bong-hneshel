# Curry & Co. — MongoDB Schema Reference

> **Database name:** `curry_co_db`
> **Driver:** Motor (async) via `motor.motor_asyncio.AsyncIOMotorClient`
> **Connection string:** Environment variable `MONGO_URL` in `backend/.env`

## 🌐 Where is the production MongoDB?

Emergent manages the MongoDB instance for your production deployment. Your app connects to it via the `MONGO_URL` env var **inside the deployed backend container** — the connection string is **not exposed to end users** and Emergent handles backups + availability.

If you need direct access (for backups, migration, or ad-hoc queries), email **support@emergent.sh** with your job ID and ask for:
- Read-only credentials for the production database
- A scheduled `mongodump` you can download
- Or a one-time snapshot export

For local development, `MONGO_URL` in `/app/backend/.env` points to a local mongod instance running inside your preview container.

---

## 📚 Collections at a glance

| Collection | Docs (approx) | Purpose |
|---|---|---|
| [`admins`](#admins) | 1 | Admin login credentials (bcrypt hashed) |
| [`business_settings`](#business_settings) | 1 | Global config (tax, delivery fee, payment methods, integrations) |
| [`catering_packages`](#catering_packages) | 5 | Catering menu (per-guest pricing) |
| [`catering_quote_requests`](#catering_quote_requests) | 1+ | Custom-quote enquiries from catering page |
| [`coupons`](#coupons) | 3 | Promo codes (percent / flat / free-delivery) |
| [`delivery_applications`](#delivery_applications) | 10 | Applicants to become delivery partners |
| [`delivery_partners`](#delivery_partners) | 7 | Approved delivery partners + live journey state |
| [`export_files`](#export_files) | live | Temp XLS blobs for email/SMS download links (48h TTL) |
| [`master_menu`](#master_menu) | 46 | All possible dishes (source of truth for weekly menus) |
| [`orders`](#orders) | 76 | Every placed order |
| [`payment_transactions`](#payment_transactions) | 23 | Stripe session log for reconciliation |
| [`user_sessions`](#user_sessions) | 13 | Login tokens |
| [`users`](#users) | 59 | Customers (+ guest checkouts) |
| [`weekly_menus`](#weekly_menus) | 4 | Weekly published menus (Sun–Sat cycles) |

---

## 🔑 Conventions

- **Money is stored in cents** (integer) throughout. Divide by 100 for CAD dollars.
- **Timestamps** are stored as `datetime` (UTC-aware) via Motor.
- **IDs** — every document has a business-facing UUID-like string (`order_id`, `user_id`, `item_id`, `partner_id`, …) in addition to Mongo's internal `_id`. Use the business ID in APIs.
- **Weekly cycles** use `week_start` = ISO date of the Sunday that opens the week.

---

## 🗂️ Collections in detail

### `admins`
Single-row collection holding the sole admin login. Additional admins are not supported by the UI yet — this doc is seeded on startup from `ADMIN_EMAIL`/`ADMIN_PASSWORD` env vars.

| Field | Type | Notes |
|---|---|---|
| `email` | string | Login email |
| `password_hash` | string | bcrypt hash |
| `created_at` | datetime | |

Index: `email` unique.

---

### `business_settings`
The one and only "global config" doc. `key == "default"` (used as a natural primary key). All admin Settings page fields land here.

| Field | Type | Notes |
|---|---|---|
| `key` | string | Always `"default"` |
| `business_name` | string | Shown in customer app header |
| `kitchen_address` | string | Origin for route optimization |
| `phone` | string | Business phone |
| `email` | string | Business support email |
| `operating_hours` | string | Free-form display text |
| `delivery_areas` | array<string> | e.g. `["Mississauga", "Toronto"]` |
| `default_delivery_fee_cents` | int | Cents |
| `minimum_order_cents` | int | Cents |
| `tax_enabled` | bool | |
| `tax_rate_bps` | int | Basis points (1300 = 13%) |
| `tax_label` | string | e.g. "HST" |
| `currency` | string | ISO 4217 code, default `"CAD"` |
| `company_info` | string | Legal footer text |
| `payment_methods` | object | `{cod: {enabled, ...}, stripe: {...}, interac: {...}, paypal: {...}}` |
| `ordering_days` | array<int> | 0=Sun … 6=Sat. Days customers can PLACE orders |
| `delivery_days` | array<int> | 0=Sun … 6=Sat. Days when kitchen delivers |
| `integrations.email.recipient` | string | Where XLS exports get emailed |
| `integrations.email.last_test_ok` | bool\|null | Last test result |
| `integrations.google_drive.service_account_json_encrypted` | string | Fernet-encrypted service-account JSON |
| `integrations.google_drive.folder_id` | string | Target Drive folder |
| `integrations.google_drive.user_email` | string | Owner for "share back" |
| `integrations.google_drive.client_email` | string | Non-secret; extracted from JSON for display |
| `integrations.twilio.account_sid` | string | Non-secret |
| `integrations.twilio.auth_token_encrypted` | string | Fernet-encrypted |
| `integrations.twilio.from_number` | string | E.164 |

Index: `key` unique.

---

### `catering_packages`
Bundled offers that scale by guest count.

| Field | Type | Notes |
|---|---|---|
| `package_id` | string | UUID |
| `name` / `tagline` / `description` | string | Marketing copy |
| `emoji` | string | Small display glyph |
| `perfect_for` | string | e.g. "Weddings" |
| `price_cents` | int | Per-guest price |
| `min_guests` | int | |
| `image_url` | string | Cover image |
| `includes` | array<string> | Bulleted list |
| `included_master_ids` | array<string> | Refs to `master_menu.item_id` |
| `choice_groups` | array<object> | Optional groups where guest picks N of M |
| `upgrade_tiers` | array<object> | Premium upgrades w/ extra per-guest cost |
| `premium_items` | array<object> | Add-ons |
| `is_custom_quote` | bool | If true, checkout is a quote request |
| `contact_email` / `contact_phone` | string | For custom quotes |
| `is_featured` / `is_active` | bool | |
| `sort_order` | int | Display order |

---

### `catering_quote_requests`
Custom-catering enquiries from the customer app.

| Field | Type | Notes |
|---|---|---|
| `request_id` | string | UUID |
| `package_id` | string | Optional package ref |
| `name` / `email` / `phone` | string | Contact |
| `guest_count` | int | |
| `event_date` | string | ISO date |
| `notes` | string | Free-form |
| `status` | string | `pending` \| `contacted` \| `booked` \| `cancelled` |
| `created_at` | datetime | |

---

### `coupons`
Simple promo codes.

| Field | Type | Notes |
|---|---|---|
| `code` | string | User-typed, uppercased |
| `active` | bool | |
| `description` | string | Admin-visible label |
| `discount_type` | string | `percent` \| `flat` \| `free_delivery` |
| `value` | int | For percent: bps (1000=10%). For flat: cents. Ignored for free_delivery. |
| `min_order_cents` | int | Minimum subtotal to qualify |

Index: `code` unique.

---

### `delivery_applications`
Signups from the "Become a delivery partner" flow. Reviewed by admin who then creates a `delivery_partners` row.

| Field | Type | Notes |
|---|---|---|
| `app_id` | string | UUID |
| `user_id` | string | Ref to `users.user_id` |
| `full_name` / `email` / `phone` / `city` | string | Contact |
| `vehicle` | string | `bike` \| `car` \| `scooter` \| `walk` |
| `availability` | string | Free-form ("Weekends, evenings") |
| `experience` | string | Free-form |
| `status` | string | `pending` \| `approved` \| `rejected` |
| `created_at` | datetime | |

---

### `delivery_partners`
Approved partners plus their live GPS journey state.

| Field | Type | Notes |
|---|---|---|
| `partner_id` | string | UUID |
| `name` / `email` / `phone` / `vehicle` | string | Profile |
| `password_hash` | string | bcrypt |
| `is_active` | bool | Set to false to deactivate |
| `current_lat` / `current_lng` | float | Live GPS |
| `current_location_updated_at` | datetime | Freshness |
| `journey_active` | bool | Currently doing a run |
| `journey_started_at` / `journey_ended_at` | datetime | |
| `journey_order_ids` | array<string> | Orders in this run |
| `journey_stops` | array<object> | Optimized stop metadata |
| `journey_origin_address` / `journey_origin_lat` / `journey_origin_lng` | mixed | Route start |
| `journey_polyline` | string | Encoded Google Maps polyline |
| `journey_total_duration_sec` | int | Estimated run duration |
| `journey_optimized` | bool | Whether Google Directions optimized the order |
| `created_at` / `updated_at` | datetime | |

---

### `export_files`
Ephemeral XLS blobs referenced by email/SMS download links.

| Field | Type | Notes |
|---|---|---|
| `token` | string | 32-byte URL-safe token (part of the download URL) |
| `filename` | string | e.g. `curryco-orders-2026-08-31-1000.xlsx` |
| `content_b64` | string | Base64 of the XLSX bytes |
| `content_type` | string | Always `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `created_at` | datetime | |
| `expires_at` | datetime | 48h after creation. TTL index auto-deletes. |

Indexes: `token` unique, `expires_at` TTL (`expireAfterSeconds: 0`).

---

### `master_menu`
The full library of dishes. Weekly menus reference these by `item_id`.

| Field | Type | Notes |
|---|---|---|
| `item_id` | string | UUID |
| `name` | string | Dish name |
| `short_description` / `full_description` | string | Marketing copy |
| `category` | string | e.g. "Main", "Side", "Dessert" |
| `cuisine` | string | e.g. "Bengali", "North Indian" |
| `default_price_cents` | int | Cents |
| `cost_price_cents` | int | For margin analysis |
| `image_url` | string | Primary image (Emergent Object Storage) |
| `extra_images` | array<string> | Alternate photos |
| `veg_type` | string | `veg` \| `non_veg` \| `vegan` \| `contains_egg` |
| `spice_level` | int | 0–5 |
| `allergens` | array<string> | e.g. `["nuts", "dairy"]` |
| `is_active` | bool | Hide from menu builder without deleting |
| `prep_notes` / `kitchen_notes` | string | Internal notes |
| `display_order` | int | Sort within category |
| `created_at` / `updated_at` | datetime | |

---

### `orders`
The heart of the system.

| Field | Type | Notes |
|---|---|---|
| `order_id` | string | `ord_xxxxxxxxxx` |
| `user_id` | string | Ref to `users.user_id`. `guest_*` for guest orders |
| `items_snapshot` | array<object> | Frozen line items (see below) |
| `address` | object | `{name, line1, line2, city, postal_code, lat, lng}` |
| `slot` | object | `{date: "YYYY-MM-DD", window: "friday_evening"}` |
| `subtotal_cents` | int | Sum of line totals |
| `delivery_fee_cents` | int | |
| `discount_cents` | int | Coupon + point redemption |
| `points_redeemed_cents` | int | Loyalty burn |
| `total_cents` | int | Final charge |
| `coupon_code` | string\|null | Applied coupon |
| `special_instructions` | string | Customer notes |
| `status` | string | `pending_payment` → `new` → `confirmed` → `preparing` → `packed` → `out_for_delivery` → `delivered`. Or `cancelled` |
| `payment_status` | string | `pending` \| `paid` \| `failed` \| `refunded` |
| `payment_method` | string | `card` \| `cod` \| `interac` \| `paypal` |
| `stripe_session_id` | string\|null | For reconciliation |
| `points_awarded` | int | Loyalty points earned |
| `tracking_events` | array<object> | `[{status, at, note}]` for audit trail |
| `created_at` / `updated_at` | datetime | |

**`items_snapshot[]` shape:**
| Field | Notes |
|---|---|
| `name` | Frozen at order time |
| `image_url` | |
| `quantity` | Combo count OR portion count for à la carte |
| `unit_price_cents` | Per-unit price frozen at order time |
| `line_total_cents` | Total after quantity + surcharges |
| `kind` | `alacarte` \| `weekly_package` \| `catering` |
| `catering_guest_count` | For catering only |
| `package_selection_names` | For combos: which dishes the customer picked (may include " × N" qty suffix) |

Indexes: `order_id` unique, `user_id`, `status`, `created_at` desc.

---

### `payment_transactions`
Stripe session log for support / reconciliation.

| Field | Type | Notes |
|---|---|---|
| `session_id` | string | Stripe checkout session ID |
| `order_id` | string | Our order ref |
| `user_id` | string | |
| `amount_cents` / `currency` | int / string | |
| `payment_status` | string | Mirror of Stripe's status |
| `status` | string | Our internal status |
| `created_at` | datetime | |

---

### `user_sessions`
Server-side session tokens (not JWT).

| Field | Type | Notes |
|---|---|---|
| `session_token` | string | Random |
| `user_id` | string | Ref to `users.user_id` |
| `created_at` | datetime | |
| `expires_at` | datetime | |

Index: `session_token` unique. Suggest adding `expires_at` TTL.

---

### `users`
Customers, including guests.

| Field | Type | Notes |
|---|---|---|
| `user_id` | string | `user_xxxx` for real users, `guest_xxxx` for guest checkouts |
| `email` | string | Nullable for guests |
| `name` | string | |
| `picture` | string | Google avatar URL if available |
| `phone` | string | |
| `default_address` | object | Same shape as `orders.address` |
| `loyalty_points` | int | 1 point ≈ 1¢ redeemable |
| `role` | string | `customer` \| `guest` \| `delivery_partner` |
| `created_at` | datetime | |

Index: `user_id` unique.

---

### `weekly_menus`
Menu published each Sunday.

| Field | Type | Notes |
|---|---|---|
| `menu_id` | string | UUID |
| `week_start` | string | ISO date (Sunday) — used as natural key |
| `week_end` | string | ISO date (Saturday) |
| `title` / `description` | string | Marketing copy |
| `banner_image_url` | string | Hero image |
| `alacarte_enabled` | bool | Show à la carte tab |
| `items` | array<object> | À la carte: `[{item_id, price_cents, override_name, is_featured}]` |
| `package_enabled` | bool | Show combo tab |
| `package` | object | Weekly combo config: `{name, description, price_cents, item_surcharges_cents, choice_groups}` |
| `lines` | array<object> | Legacy field (kept for backwards compat) |
| `status` | string | `draft` \| `published` |
| `published` | bool | Fast filter |
| `created_at` | datetime | |

Index: `week_start` unique.

---

## 🧰 Backup / export tips

For a full local backup during development:
```bash
mongodump --uri="$MONGO_URL" --out=/tmp/backup-$(date +%Y%m%d)
```

For production backups, email **support@emergent.sh** with your job ID — they can arrange a scheduled `mongodump` or a one-time snapshot.

## 🔒 Sensitive fields

Never log or return these to the client:
- `admins.password_hash`
- `delivery_partners.password_hash`
- `business_settings.integrations.google_drive.service_account_json_encrypted`
- `business_settings.integrations.twilio.auth_token_encrypted`

The Fernet key that decrypts the last two lives in `INTEGRATIONS_FERNET_KEY` (backend/.env). Rotate carefully — old ciphertext becomes unreadable.
