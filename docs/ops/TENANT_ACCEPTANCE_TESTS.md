# Tenant Acceptance Test Plan — Suparna Dey Platform

> **Audience:** Suparna Dey Platform operations team
> **When to run:** every time a new tenant is spun up, before you flip
> them from *ONBOARDING* to *LIVE* in the Super Admin portal.
> **How to run:** work top-to-bottom, tick each ✅ box as you pass a
> case. If any P0 or P1 case fails, stop and get engineering — do
> NOT go live.
> **Expected time:** 60–90 minutes for the full run.
>
> Legend: **P0** = blocks launch · **P1** = must fix within 24 hours ·
> **P2** = fix within 1 week

---

## 0 · Pre-flight

Fill in these values before you start. Everything else in the plan
references them.

| Field | Value |
| ----- | ----- |
| Tenant slug | `<slug>` |
| Tenant name | `<Display Name>` |
| Preview URL | `https://<slug>-preview.emergent.host` |
| Production URL | `https://<slug>.emergent.host` (fill after §11) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | (from `generate_tenant_secrets.py`) |
| `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` | (from `generate_tenant_secrets.py`) |
| Delivery driver test account | `delivery@<tenant-domain>` / `<password>` |
| `platform.tenant_id` in Super Admin | `tnt_<slug>` |
| Google Maps key restricted for this tenant? | ☐ Yes |
| Seed data imported? | ☐ Yes ☐ Skipped |

**Devices you'll need:**
- ☐ Laptop with a modern browser (Chrome / Safari)
- ☐ One real iOS device (for TestFlight verification later, §13)
- ☐ One real Android device (for `.APK` sideload verification, §13)

---

## 1 · Infrastructure & boot health · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| INF-01 | Backend health | `curl <preview>/api/` | `{"message": ... }` 200 OK, no exception | ☐ |
| INF-02 | MongoDB connected | Watch backend logs on Emergent → look for `indexes ready` on startup | Present, no `ServerSelectionTimeoutError` | ☐ |
| INF-03 | Expo web bundles | Open preview URL in browser | Page renders < 5 s, no red-screen error overlay | ☐ |
| INF-04 | No unhandled exceptions on boot | Scroll last 200 lines of backend logs | No `Traceback`, no `ERROR` lines | ☐ |
| INF-05 | Frontend uses HTTPS | Browser address bar shows a padlock | Locked, no mixed-content warnings in DevTools console | ☐ |
| INF-06 | `/api/brand` returns tenant config | `curl <preview>/api/brand` | JSON has correct `name`, `currency`, `timezone` | ☐ |

---

## 2 · Branding verification · P0

Open the preview URL in the browser. Take a screenshot of every screen
listed below and confirm each item.

| # | Screen | Check | Pass |
| - | ------ | ----- | ---- |
| BRD-01 | Customer home (`/`) | Logo displayed top-left is the **tenant's** logo, not Curry & Co. | ☐ |
| BRD-02 | Customer home | Brand name in header matches `brand.json → name` | ☐ |
| BRD-03 | Customer home | Tagline matches intake form B.1 | ☐ |
| BRD-04 | All screens | Primary color is the auto-derived hex (or the manual override from intake) | ☐ |
| BRD-05 | Splash screen | Reload — the splash shown while the JS bundle loads matches the tenant | ☐ |
| BRD-06 | Browser tab | Title bar shows tenant name | ☐ |
| BRD-07 | Favicon | Small icon in browser tab is tenant's logo, not the default Expo icon | ☐ |
| BRD-08 | Admin login (`/admin`) | Header logo + name are tenant-branded | ☐ |
| BRD-09 | Currency | Every price shows the correct symbol (e.g. `CA$`, `$`, `₹`) | ☐ |
| BRD-10 | Timezone | Order timestamps in Admin match the tenant's timezone, not UTC | ☐ |
| BRD-11 | Legal footer | Legal name + support email match `brand.json` | ☐ |
| BRD-12 | Delete-account modal | Warning text mentions the tenant's brand, not Curry & Co. | ☐ |

---

## 3 · Customer app · P0

### 3.1 · Guest browsing (no login) · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| CUS-01 | Menu loads | Home → scroll the current-week menu | ≥ 1 item visible with photo, name, price | ☐ |
| CUS-02 | Upcoming week | Tap "Upcoming" tab | Shows next week's menu OR a "menu coming soon" empty state | ☐ |
| CUS-03 | History | Tap "History" tab | Shows past weeks or an appropriate empty state | ☐ |
| CUS-04 | Item detail | Tap any item | Modal / page opens with description, price, quantity picker | ☐ |
| CUS-05 | Add to cart | Tap "Add to cart" on any item | Cart icon badge increments; toast confirms | ☐ |
| CUS-06 | Cart view | Open cart | Item, quantity, subtotal all correct | ☐ |
| CUS-07 | Increase / decrease qty | Use +/- in cart | Subtotal updates instantly, no UI lag | ☐ |
| CUS-08 | Remove item | Swipe / tap trash on cart line | Item disappears, subtotal recalculates | ☐ |
| CUS-09 | Empty cart state | Remove last item | Cart shows empty illustration + "back to menu" CTA | ☐ |
| CUS-10 | Combo picker | Add a weekly-combo item | Combo picker modal appears, all sub-choices required before adding | ☐ |
| CUS-11 | Catering | Open Catering tab | ≥ 1 package visible (if seeded); each shows description + price | ☐ |

### 3.2 · Address & delivery zone · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| CUS-20 | Address autocomplete | Checkout → start typing an address in the tenant's service area | Google dropdown appears with suggestions within 500 ms | ☐ |
| CUS-21 | Autocomplete style | Suggestions are styled to match tenant color scheme | Primary color used for highlight | ☐ |
| CUS-22 | Pick address | Tap a suggestion | Address fields populate; map preview centers on the pin | ☐ |
| CUS-23 | Manual entry fallback | Toggle "enter manually" | All fields editable, no autocomplete required | ☐ |
| CUS-24 | Out-of-zone address | Enter an address obviously outside the service area | Error: "we don't deliver to this address" — order blocked | ☐ |
| CUS-25 | Delivery fee | Confirm order shows the fee from `settings.default_delivery_fee_cents` | Displayed correctly, taxable if configured | ☐ |
| CUS-26 | Minimum order | Try to check out with subtotal below `minimum_order_cents` | Blocked with "add $X more to check out" message | ☐ |
| CUS-27 | Delivery slot picker | Only shows days that match `settings.delivery_days` | E.g. weekends only if configured | ☐ |
| CUS-28 | Order cut-off | Set device clock past cut-off, retry | Same-week order blocked; next-week option offered | ☐ |

### 3.3 · Coupons & loyalty · P1

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| CUS-30 | Valid coupon | Enter `WELCOME10` at checkout | 10% off applied, subtotal updates | ☐ |
| CUS-31 | Min-subtotal not met | Enter `BENGALI15` with cart < $50 | Rejected with clear message | ☐ |
| CUS-32 | Invalid coupon | Enter `NOTREAL` | Rejected with "invalid code" | ☐ |
| CUS-33 | Loyalty points display | Log in → account | Balance shown (0 or seeded value) | ☐ |
| CUS-34 | Loyalty earn | Place a paid order | Balance increases by the configured rate after order fulfilled | ☐ |

### 3.4 · Authentication · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| AUTH-01 | Guest checkout | Place an order without logging in | Prompts for email/name only; order created with `guest.<tenant-domain>` email prefix | ☐ |
| AUTH-02 | Google Sign-In | Tap "Sign in with Google" | OAuth popup opens; after success user is landed on home logged in | ☐ |
| AUTH-03 | Session persistence | Reload the page after login | Still logged in | ☐ |
| AUTH-04 | Logout | Profile → sign out | Back to guest state; `/api/auth/me` returns 401 | ☐ |
| AUTH-05 | Expired token | Wait 8 days (or DB-hack the expires_at) → refresh | Silent logout; redirected to login on next authed action | ☐ |
| AUTH-06 | Delete account | Profile → delete account → confirm modal | Modal copy mentions tenant name (see BRD-12); after confirm, user is logged out and cannot log back in with same email | ☐ |

### 3.5 · Payment methods · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| PAY-01 | COD selected | Checkout → cash on delivery | Order placed, status = "confirmed" | ☐ |
| PAY-02 | Interac selected | Checkout → Interac e-transfer | Order placed; confirmation shows the tenant's e-transfer instructions from `settings` | ☐ |
| PAY-03 | Stripe temporarily disabled | Try selecting "Credit card" | UI clearly says "temporarily unavailable" OR the option is hidden — no 500 error | ☐ |
| PAY-04 | Order in DB | Admin → Orders → find the just-placed order | Present with correct total, items, address | ☐ |
| PAY-05 | Order confirmation email | Check inbox of the customer email | Email received within 60 s, contains order summary + branding | ☐ |
| PAY-06 | Order confirmation email — brand | Open the email | Sender name = `EMAIL_FROM_NAME`; no "Curry & Co." references | ☐ |

### 3.6 · Order tracking · P1

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| TRK-01 | Order list | Customer → My Orders | Latest order at the top with status badge | ☐ |
| TRK-02 | Order detail | Tap the order | Shows timeline (placed → preparing → out for delivery → delivered) | ☐ |
| TRK-03 | Live map | Once a driver accepts → open order detail | Map with driver pin + ETA visible | ☐ |
| TRK-04 | ETA ticking | Wait 30 s on the tracking screen | ETA re-calculates, driver pin moves if driver is actually moving | ☐ |
| TRK-05 | Arrival banner | Driver marks "arrived" | Banner: "Your driver has arrived" appears | ☐ |
| TRK-06 | Delivered state | Driver marks delivered | Timeline shows checkmark; loyalty points credited | ☐ |

---

## 4 · Admin portal · P0

Log in at `/admin` with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

### 4.1 · Dashboard · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| ADM-01 | Login works | Enter creds | Redirects to `/admin/dashboard` | ☐ |
| ADM-02 | Bad password | Enter wrong password | Clear error "Invalid credentials", not a 500 | ☐ |
| ADM-03 | Stats load | Dashboard | GROSS REVENUE, ALL ORDERS, ACTIVE NOW, DELIVERED, CUSTOMERS visible with real numbers | ☐ |
| ADM-04 | Stat cards clickable | Not required, but if any card links to a filtered view — try each | Correct list loads | ☐ |
| ADM-05 | Sidebar has Billing entry | Left nav | "Billing" visible between Delivery and Settings (added in Phase 3) | ☐ |
| ADM-06 | Sign out | Sidebar → Sign out | Back to `/admin` login | ☐ |

### 4.2 · Master Menu · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| ADM-10 | List | Master Menu tab | ≥ 1 item if seeded, otherwise empty state with "add first item" CTA | ☐ |
| ADM-11 | Create item | Add item → fill name, price, description, image | Item appears in list within 1 s | ☐ |
| ADM-12 | Edit item | Tap any item → change price | New price persisted, no reload needed | ☐ |
| ADM-13 | Delete item | Tap trash | Confirm modal, then item removed | ☐ |
| ADM-14 | Duplicate | Duplicate button on an item | Copy created with " (copy)" suffix | ☐ |
| ADM-15 | Image upload | Attach a photo when creating | Image visible in item card | ☐ |
| ADM-16 | Bulk actions | Multi-select items → bulk publish/unpublish | Applies to all selected | ☐ |

### 4.3 · Weekly Menu · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| ADM-20 | Current week | Weekly Menu → this week | Items listed | ☐ |
| ADM-21 | Publish next week | Add items → set `week_start` | Items visible in customer app "Upcoming" tab | ☐ |
| ADM-22 | Change ordering | Drag-reorder items | Order persists after page reload | ☐ |
| ADM-23 | Unpublish week | Toggle publish off | Customer "Current" tab shows the previous week or a "no menu" state — not a broken screen | ☐ |
| ADM-24 | Delete week | Delete a week's menu | Confirmation required; removed from list | ☐ |

### 4.4 · Orders · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| ADM-30 | Order list | Orders tab | Latest order at top, sortable | ☐ |
| ADM-31 | Filter by status | Filter dropdown → "delivered" | Only delivered orders show | ☐ |
| ADM-32 | Order detail | Tap an order | Full detail: items, customer info, address, total, status timeline | ☐ |
| ADM-33 | Status transition | Change status confirmed → preparing → out for delivery → delivered | Each transition succeeds; customer app reflects within 30 s | ☐ |
| ADM-34 | Refund | On a paid order → refund | Refund recorded; order marked refunded | ☐ |
| ADM-35 | New Order (admin) | Orders → New Order | Full order-creation flow works with customer picker + item picker + address entry | ☐ |
| ADM-36 | Print / share receipt | If a print button exists — try it | Opens a print dialog with a clean, brand-styled receipt | ☐ |

### 4.5 · Customers · P1

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| ADM-40 | Customer list | Customers tab | All registered users listed with created_at, order count | ☐ |
| ADM-41 | Customer detail | Tap a row | Profile, addresses, order history, loyalty balance | ☐ |
| ADM-42 | Credit loyalty | Add loyalty points to a customer | Balance updates; customer sees new balance on next login | ☐ |
| ADM-43 | Search / filter | Search by email | Instant match | ☐ |

### 4.6 · Delivery · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| ADM-50 | Driver list | Delivery tab | ≥ 1 driver if seeded | ☐ |
| ADM-51 | Invite driver | Add driver → email + phone | Driver created; can log in at `/delivery-partner` | ☐ |
| ADM-52 | Deactivate driver | Toggle active off | Driver's login blocked | ☐ |
| ADM-53 | Assign order | On an unassigned order → assign to driver | Order appears in driver's app | ☐ |

### 4.7 · Settings · P1

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| ADM-60 | Load settings | Settings tab | Business name, phone, email, delivery days, tax rate all populated | ☐ |
| ADM-61 | Edit business hours | Change operating hours | Persisted; customer sees updated hours in the app footer | ☐ |
| ADM-62 | Change delivery fee | Set new default | Next order at checkout uses new fee | ☐ |
| ADM-63 | Change tax rate | Toggle tax on/off | Tax line appears/disappears on customer checkout | ☐ |
| ADM-64 | Delivery areas | Edit areas | Autocomplete on customer app respects the new areas | ☐ |
| ADM-65 | Save button feedback | Save with intentional bad input (empty required field) | Inline validation error, no data loss | ☐ |

### 4.8 · Billing (Phase 3) · P0

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| BIL-01 | Billing tab loads | Admin → Billing | Renders without error | ☐ |
| BIL-02 | Coming-soon state | If hub not yet ready | "Billing is coming soon" empty state | ☐ |
| BIL-03 | Plan card | If hub is ready | Plan name + $/month + status badge | ☐ |
| BIL-04 | Subscribe CTA | On a `none` status → tap Subscribe | Opens Stripe Checkout in new tab | ☐ |
| BIL-05 | Complete checkout | Use test card `4242 4242 4242 4242` | Returns to Billing tab; status flips to ACTIVE within 60 s | ☐ |
| BIL-06 | Manage billing | On active sub → tap Manage billing | Opens Stripe Customer Portal | ☐ |
| BIL-07 | Update card | In portal → update to another test card | Portal confirms; Billing tab card row updates | ☐ |
| BIL-08 | Invoice list | Return to Billing tab | ≥ 1 invoice row with amount, date, status, "View" link | ☐ |
| BIL-09 | Force refresh | Pull-to-refresh (or web equivalent) | `GET /admin/billing/summary?force=true` fires; fresh data | ☐ |
| BIL-10 | Cancel flow | Portal → cancel | Status flips to `canceled` or `cancel_at_period_end` | ☐ |

---

## 5 · Delivery partner app · P0

Log in at `/delivery-partner` with the delivery driver credentials.

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| DLV-01 | Login | Enter driver email + password | Redirected to active orders queue | ☐ |
| DLV-02 | Bad password | Wrong password | Clear error, not a 500 | ☐ |
| DLV-03 | Deactivated driver | Deactivate via Admin (ADM-52) → try login | Blocked with "your account is inactive" | ☐ |
| DLV-04 | Active orders | Home | Only orders assigned to this driver, sorted by delivery time | ☐ |
| DLV-05 | Accept order | Tap Accept | Order status = "picked up"; disappears from unassigned list for other drivers | ☐ |
| DLV-06 | Live GPS | On the accepted order screen — allow location permission | Driver location broadcasted; visible on customer app's live map | ☐ |
| DLV-07 | Location permission denied | Deny permission | App still usable; a friendly banner asks to enable in Settings | ☐ |
| DLV-08 | Mark delivered | Tap Delivered | Order removed from active list; customer sees "delivered" | ☐ |
| DLV-09 | History | View past deliveries | Shows list with totals | ☐ |
| DLV-10 | Log out | Sign out | Session cleared | ☐ |

---

## 6 · SaaS phone-home & platform gates · P0

These prove the tenant is correctly wired into the Suparna Dey Platform.

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| SAAS-01 | Poller connected | `curl <preview>/api/platform/status` | `known: true`, `operational: true`, `subscription_status` set | ☐ |
| SAAS-02 | 5-min cadence | Wait 6 min → curl again | `checked_at` advanced | ☐ |
| SAAS-03 | Banner hidden when active | Admin dashboard | No red platform banner visible | ☐ |
| SAAS-04 | Suspend tenant | In Super Admin → set this tenant to `past_due` | Within 5 min: banner appears in Admin portal | ☐ |
| SAAS-05 | Checkout blocked | While suspended, place a customer order | `/api/orders` returns 402 with "restaurant owner missed billing" message | ☐ |
| SAAS-06 | Driver login blocked | While suspended, try DLV-01 | `/api/delivery/login` returns 402 | ☐ |
| SAAS-07 | Restore | Set tenant back to `active` in Super Admin | Within 5 min: banner disappears, orders + logins succeed | ☐ |
| SAAS-08 | Wrong API key | Rotate api_key in Super Admin but don't update tenant | Within 5 min: banner shows "Tenant credentials rejected" | ☐ |
| SAAS-09 | Restore API key | Update `brand.json` back to the correct key → restart backend | Banner clears | ☐ |

---

## 7 · Integrations end-to-end · P0/P1

| # | Case | How to run | Priority | Expected | Pass |
| - | ---- | ---------- | -------- | -------- | ---- |
| INT-01 | Google Places autocomplete | Any address field in the customer app | P0 | Suggestions appear; no JS console 403/OVER_QUERY_LIMIT | ☐ |
| INT-02 | Google Geocoding | Pick an address | P0 | lat/lng populated on the order document (check Admin → Order detail) | ☐ |
| INT-03 | Google Directions | Live tracking screen | P1 | Route polyline drawn from kitchen → destination | ☐ |
| INT-04 | Google Maps SDK | Live tracking screen | P0 | Map tiles load, no gray blocks / "for development purposes only" watermark | ☐ |
| INT-05 | Email delivery | Place order → check inbox | P0 | Order confirmation email arrives < 60 s | ☐ |
| INT-06 | Email deliverability | Open email headers | P1 | SPF/DKIM checks pass (green in Gmail's "show original") | ☐ |
| INT-07 | LLM (if any AI features) | Trigger the feature | P2 | Response within 15 s; content is coherent | ☐ |
| INT-08 | Image gen (if used) | Trigger the feature | P2 | Image returned within 30 s | ☐ |
| INT-09 | SMS OTP (if enabled) | Login by phone | P1 | SMS received < 60 s from the tenant's `MG...` messaging service | ☐ |
| INT-10 | Push notifications | Native build only (Expo Go won't show these) | P1 | Push received on order status change; tapping opens the order | ☐ |

**Note:** INT-10 can only be verified against a **native build**
(TestFlight or `.APK`). Expo Go and the web preview cannot receive
push notifications.

---

## 8 · Security & abuse resistance · P1

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| SEC-01 | Admin JWT required | `curl <preview>/api/admin/menus` (no token) | 401 Unauthorized | ☐ |
| SEC-02 | Admin JWT tampered | Change one char of the token → curl | 401 | ☐ |
| SEC-03 | Rate limit on login | Hit `/api/admin/login` with wrong password 10× in a row | Blocked or throttled | ☐ |
| SEC-04 | CORS locked | From browser DevTools: `fetch('<preview>/api/admin/menus', {credentials:'omit'})` from a different origin | Blocked with CORS error | ☐ |
| SEC-05 | No secrets in the frontend bundle | `curl <preview>` → grep for `sk_`, `AIzaSy`, `MG` | No live secret keys appear (only `EXPO_PUBLIC_*` values, which are ok) | ☐ |
| SEC-06 | Delivery driver can't access admin | Log in as driver → try `/admin` | Redirected to `/admin` login screen | ☐ |
| SEC-07 | Customer can't hit driver routes | Log in as customer → curl `/api/delivery/orders` with their token | 401 or 403 | ☐ |
| SEC-08 | Passwords are hashed | Check MongoDB `admins` collection | `password_hash` present, plain `password` absent | ☐ |

---

## 9 · Edge cases · P1

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| EDG-01 | Empty current-week menu | Admin → unpublish current week | Customer home shows friendly empty state, not a spinner forever | ☐ |
| EDG-02 | Zero inventory | Set an item's stock/quantity to 0 (if the feature is on) | Item disabled with "sold out" badge; can't add to cart | ☐ |
| EDG-03 | Massive cart | Add 50 items to cart | Cart still opens; totals compute in < 1 s | ☐ |
| EDG-04 | Slow network | DevTools → throttle to Slow 3G | Loading spinners appear appropriately; no timeouts under 30 s | ☐ |
| EDG-05 | Offline behavior | Turn off network mid-checkout | Clear "no connection" toast; order not silently lost | ☐ |
| EDG-06 | Restart during checkout | Reload the page mid-checkout | Cart is preserved (from AsyncStorage) | ☐ |
| EDG-07 | Very long name | Register a user with a 200-char name | Truncated in UI, saved in DB, no layout break | ☐ |
| EDG-08 | Special chars in name | Use emojis + accented chars | Stored + rendered correctly, no encoding issues in emails | ☐ |
| EDG-09 | Wrong-timezone edge | Place an order at 11:55 PM local | Shows correct day in Admin (tenant's timezone, not UTC) | ☐ |
| EDG-10 | Multiple tabs open | Log into admin in two tabs → change status in one | Other tab reflects change on next action (no stale-state crash) | ☐ |

---

## 10 · Performance smoke · P1

Run each with browser DevTools → Network tab open, cache disabled.

| # | Metric | Target | Measured | Pass |
| - | ------ | ------ | -------- | ---- |
| PRF-01 | Home page — first meaningful paint | < 3 s on cable | ___ s | ☐ |
| PRF-02 | `/api/menu/current` response time | < 400 ms cold | ___ ms | ☐ |
| PRF-03 | `/api/orders` (auth'd, 10 orders) | < 500 ms | ___ ms | ☐ |
| PRF-04 | Cart open → item detail transition | < 200 ms | ___ ms | ☐ |
| PRF-05 | Admin dashboard stats load | < 800 ms | ___ ms | ☐ |
| PRF-06 | Bundle size | Main JS chunk < 3 MB gzipped | ___ MB | ☐ |

If any target is missed by > 2× — flag to engineering, don't block launch.

---

## 11 · Production deploy · P0

Only run after the sections above all pass on **preview**.

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| PROD-01 | Publish | Emergent → Publish button | Build completes without error (~2–5 min) | ☐ |
| PROD-02 | Prod URL accessible | Open the assigned emergent.host URL | Same experience as preview | ☐ |
| PROD-03 | HTTPS enforced | Try `http://` version | Auto-redirects to `https://` | ☐ |
| PROD-04 | `PUBLIC_BASE_URL` set | Env panel | Set to the prod URL; redeploy | ☐ |
| PROD-05 | Google Maps allow-list | The prod domain is in the API key's HTTP referrers | Confirmed in Google Cloud console | ☐ |
| PROD-06 | Prod emails work | Place an order on prod | Confirmation email arrives, contains the prod URL not the preview URL | ☐ |
| PROD-07 | Prod SaaS status | curl `<prod>/api/platform/status` | Same as SAAS-01 but from prod | ☐ |

---

## 12 · iOS build & TestFlight · P0 (when publishing to App Store)

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| IOS-01 | Build succeeds | Emergent → Generate iOS build | `.ipa` produced without errors | ☐ |
| IOS-02 | Bundle IDs match | Check the `.ipa` metadata | `com.<slug>.customer` (and delivery variant) | ☐ |
| IOS-03 | TestFlight upload | Emergent submits automatically | Apple's automated processing succeeds (5–30 min) | ☐ |
| IOS-04 | Install on device | Install via TestFlight | App opens, splash + home render | ☐ |
| IOS-05 | Native permissions prompt | First trigger of camera/location | System prompt shows the tenant's usage description (from `app.json`), not "Curry & Co." | ☐ |
| IOS-06 | Deep link | Tap an `<slug>://order/<id>` link | Opens the correct order screen | ☐ |
| IOS-07 | Push received | Send a test push from Admin → order status change | Notification appears on the device | ☐ |
| IOS-08 | Offline behavior | Turn on airplane mode → open the app | Cached menu visible; clear no-network banner | ☐ |
| IOS-09 | Sign-in-with-Apple | If enabled — try it | Works or is hidden per app.json config | ☐ |
| IOS-10 | Delete account visible | Profile → delete account | Present and functional (Apple requires this for review) | ☐ |

---

## 13 · Android build & sideload · P0 (when publishing to Play Store)

| # | Case | How to run | Expected | Pass |
| - | ---- | ---------- | -------- | ---- |
| AND-01 | Build succeeds | Emergent → Generate Android build | `.APK` + `.AAB` produced | ☐ |
| AND-02 | Package names match | Inspect `.APK` with `aapt dump badging` | `com.<slug>.customer` etc. | ☐ |
| AND-03 | Install on device | `adb install app.apk` (or open from file manager) | App launches | ☐ |
| AND-04 | Runtime permissions | First trigger camera/location | System prompt correct | ☐ |
| AND-05 | Adaptive icon | Home screen | Shows the tenant's adaptive icon (foreground + background) | ☐ |
| AND-06 | Back button behavior | Navigate deep → hardware back | Correct back stack, no crash | ☐ |
| AND-07 | Deep link | Fire an intent with `<slug>://order/<id>` | Opens the app to the order | ☐ |
| AND-08 | Push received | Test push | Notification appears with correct icon | ☐ |
| AND-09 | Data safety | Play Console → Data safety | Filled out correctly (email, address, order history) | ☐ |

---

## 14 · Store submission checklist · P0

| # | Case | Pass |
| - | ---- | ---- |
| SUB-01 | Reviewer credentials shared with Apple & Google | ☐ |
| SUB-02 | Reviewer notes explain "Continue as guest" flow | ☐ |
| SUB-03 | Screenshots — 6.7", 6.5", 5.5" for iOS | ☐ |
| SUB-04 | Screenshots — phone + 7"/10" tablet for Android | ☐ |
| SUB-05 | Privacy policy URL published (tenant's or platform default) | ☐ |
| SUB-06 | Terms of service URL published | ☐ |
| SUB-07 | Support URL published | ☐ |
| SUB-08 | Age rating filled (usually 4+ / PEGI 3) | ☐ |
| SUB-09 | Export compliance answered (usually "no encryption beyond HTTPS") | ☐ |
| SUB-10 | App description proofread — no "Curry & Co." references | ☐ |

---

## 15 · Sign-off

Sign this section only if **every P0 case above passes** AND all P1
failures have been documented + accepted by the tenant owner.

| Role | Name | Signature | Date |
| ---- | ---- | --------- | ---- |
| Ops lead |  |  |  |
| Engineering |  |  |  |
| Tenant owner |  |  |  |

**Failures log** — list every non-passing case + resolution plan:

| Case ID | Failure summary | Priority | Owner | Due | Resolved? |
| ------- | --------------- | -------- | ----- | --- | --------- |
|  |  |  |  |  | ☐ |
|  |  |  |  |  | ☐ |
|  |  |  |  |  | ☐ |

Once signed, mark the tenant **LIVE** in the Super Admin portal and
move them from onboarding to steady-state ops (see
`TENANT_ONBOARDING_OPS.md` §12).

---

## Appendix A · Quick-run 15-min smoke

When you don't have 90 minutes (e.g. re-testing after a hotfix), run
just these 15 cases:

INF-01, INF-06 · BRD-01, BRD-08 · CUS-01, CUS-05, CUS-20, PAY-01,
PAY-05 · ADM-01, ADM-03, ADM-30, BIL-01 · DLV-01, DLV-05 · SAAS-01

If all 15 pass, you're > 90% likely the tenant is healthy. Schedule
the full plan for the next business day regardless.

## Appendix B · Test data helpers

- `POST /api/dev/seed` — populates current week + 2 future weeks +
  catering + coupons. Safe to re-run.
- Seed coupons: `WELCOME10` (10% off, min $20), `BENGALI15` (15% off,
  min $50), `MISHTI5` ($5 off, min $30).
- Stripe test card for BIL-04: `4242 4242 4242 4242` · any future
  expiry · any CVC.
- Alternate test card that DECLINES (for BIL failure paths):
  `4000 0000 0000 0002`.

## Appendix C · When to call engineering

Any single P0 fail + no obvious cause after 15 min of investigation.
Also call if:
- Backend logs contain unbounded traceback loops.
- Any endpoint returns 500 (not 4xx) on a valid request.
- MongoDB connection drops mid-test.
- Google Maps returns `REQUEST_DENIED` or `OVER_QUERY_LIMIT` and the
  key is verified correct.
- The SaaS phone-home poller stops updating `checked_at` for > 15 min.
