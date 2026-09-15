# Hub Billing Spec — for the Suparna Dey Platform (Super Admin) project

> Paste this document into your **Super Admin Emergent project** to have that
> agent implement the matching Stripe-Billing endpoints on the central hub.
> The tenant template (this repo) already has the client side wired against
> these contracts, so once the hub ships them the Billing tab lights up
> automatically.

---

## 1. Architecture recap

```
┌──────────────────────────┐          ┌─────────────────────────────┐
│ Tenant fork              │  HTTPS   │ Suparna Dey Platform (Hub)  │
│  (Curry & Co., Jomidari) │◀────────▶│  ── owns Stripe entirely ── │
│                          │  X-Tenant│                             │
│  Admin → Billing tab     │  headers │  Products / Prices / Subs   │
│  /api/admin/billing/*    │          │  Webhooks → tenant.status   │
└──────────────────────────┘          └─────────────────────────────┘
```

- The **hub** is the single Stripe account. Tenants never see Stripe keys.
- Each tenant has a row in `tenants` with `tenant_id`, `api_key`,
  `stripe_customer_id`, `stripe_subscription_id`, plan_id, subscription_status.
- The tenant fork already talks to `GET /api/tenant/status` every 5 min —
  this new spec adds **3 endpoints** on top of that same base URL.
- The tenant fork calls these endpoints via its own admin-JWT-protected
  proxy routes (`/api/admin/billing/*`) so the hub URL never reaches the
  browser and each call is authorised on both ends.

---

## 2. Auth (same as existing phone-home)

Every request from the tenant carries these headers:

```
X-Tenant-Id:      tnt_curryco
X-Tenant-Api-Key: sk_tnt_...
Content-Type:     application/json
```

Reject with `401` if either header is missing or invalid.

---

## 3. Endpoints to implement

Base URL (already deployed): the same host as `/api/tenant/status`.

### 3.1 `GET /api/tenant/billing/summary`

Returns everything the Billing tab shows for the authenticated tenant.

**Response 200** — shape (all fields optional except `status`):

```jsonc
{
  "status": "active",                        // one of: none | trialing | active | past_due | unpaid | canceled | incomplete
  "message": "Your platform subscription is in good standing.",  // free-text banner copy (optional)

  "plan": {
    "id": "price_1PabcXYZ",
    "name": "Restaurant Pro",
    "price_cents": 9900,
    "currency": "USD",
    "interval": "month"                      // or "year"
  },

  "card": {                                  // omit or null if no card on file
    "brand": "visa",
    "last4": "4242",
    "exp_month": 12,
    "exp_year": 2028
  },

  "current_period_end":   "2026-07-28T00:00:00Z",  // ISO 8601
  "trial_end":            null,                    // ISO if status=trialing else null
  "cancel_at_period_end": false,

  "invoices": [                              // most-recent-first, cap at 12
    {
      "id": "in_1P...",
      "number": "1A2B-0001",
      "amount_cents": 9900,
      "currency": "USD",
      "status": "paid",                      // paid | open | void | uncollectible | draft
      "created_at": "2026-06-28T00:12:34Z",
      "period_start": "2026-06-28T00:00:00Z",
      "period_end":   "2026-07-28T00:00:00Z",
      "hosted_invoice_url": "https://invoice.stripe.com/i/acct_.../inv_...",
      "invoice_pdf":        "https://pay.stripe.com/invoice/.../pdf"
    }
  ]
}
```

**Response 200 when tenant has never subscribed:**

```json
{ "status": "none", "plan": null, "card": null, "invoices": [] }
```

**Errors:**
- `401` — bad tenant headers.

> Implementation tip: pull the latest Stripe `Subscription` + `Customer` +
> `Invoice.list(limit=12)` for the tenant's `stripe_customer_id`, then map
> to the shape above. Cache 30–60s server-side if you want to protect
> against tab-refresh spam.

---

### 3.2 `POST /api/tenant/billing/checkout`

Kicks off a Stripe Checkout Session so the restaurant owner can subscribe
for the first time (or resubscribe after cancel).

**Request:**
```json
{
  "success_url": "https://tenant.example.com/admin/billing?billing=success",
  "cancel_url":  "https://tenant.example.com/admin/billing?billing=cancel"
}
```

Both URLs come from the tenant frontend (see
`/app/frontend/app/admin/billing.tsx` → `handleSubscribe`). The hub must
`stripe.checkout.Session.create(...)` with:

- `mode: "subscription"`
- `customer` = existing `stripe_customer_id` if any; otherwise create one
  and persist it on the tenant row.
- `line_items` = `[{ price: <configured price id for this tenant>, quantity: 1 }]`
- `success_url`, `cancel_url` = as provided
- `metadata: { tenant_id: <tid>, source: "tenant_admin" }`
- `subscription_data.metadata: { tenant_id: <tid> }`

**Response 200:**
```json
{ "url": "https://checkout.stripe.com/c/pay/cs_test_..." }
```

**Errors:** `401`, `409 { "error": "already_subscribed" }`, `500`.

---

### 3.3 `POST /api/tenant/billing/portal`

Returns a Stripe Customer Portal URL so the owner can update card, cancel,
or download invoices. Requires an existing `stripe_customer_id`.

**Request:**
```json
{ "return_url": "https://tenant.example.com/admin/billing" }
```

**Response 200:**
```json
{ "url": "https://billing.stripe.com/p/session/..." }
```

`stripe.billing_portal.Session.create(customer=<cid>, return_url=<url>)`.

**Errors:** `401`, `409 { "error": "no_subscription" }`, `500`.

> The Super Admin must first create a **Customer Portal configuration** in
> the Stripe dashboard (allow update payment method, allow cancellation,
> show invoice history). One config, shared across all tenants.

---

## 4. Webhook → keep `tenant.subscription_status` fresh

Stripe → hub webhook already exists in Phase 2 for `/api/tenant/status`
polling. Extend it to react to:

| Stripe event                              | Set `subscription_status` to |
| ----------------------------------------- | ---------------------------- |
| `checkout.session.completed`              | `active`                     |
| `customer.subscription.created`           | subscription.status          |
| `customer.subscription.updated`           | subscription.status          |
| `customer.subscription.deleted`           | `canceled`                   |
| `invoice.payment_failed`                  | `past_due`                   |
| `invoice.payment_succeeded`               | `active` (from past_due)     |

Match the tenant by `subscription.metadata.tenant_id` or by
`customer` → tenant lookup.

The tenant fork's 5-min poll already reads `subscription_status` from
`/api/tenant/status`, so once the DB is updated the tenant's banner
flips within 5 minutes automatically (or instantly if the tenant
admin taps refresh in the Billing tab, which force-invalidates cache).

---

## 5. DB additions on the hub

Extend the existing `tenants` collection:

```jsonc
{
  "tenant_id": "tnt_curryco",
  "api_key":   "sk_tnt_...",
  "name":      "Curry & Co.",

  // NEW ↓
  "plan_price_id":         "price_1PabcXYZ",   // configurable per-tenant, defaults to platform default
  "stripe_customer_id":    "cus_...",           // populated on first checkout
  "stripe_subscription_id":"sub_...",           // populated on subscribe
  "subscription_status":   "active",           // driven by webhook
  "current_period_end":    "2026-07-28T00:00:00Z",
  "cancel_at_period_end":  false,
  "trial_end":             null
}
```

Add a `platform_config` document (single doc collection) for global settings:

```jsonc
{
  "_id": "platform",
  "default_price_id": "price_1PabcXYZ",   // used when tenant.plan_price_id is unset
  "portal_configuration_id": "bpc_...",   // Stripe Customer Portal config
  "trial_days": 14                        // optional default trial length
}
```

---

## 6. Super Admin UI additions

In the Super Admin portal, add a **Plans & Pricing** page that lets the
platform owner:

1. Create/list Stripe Products + Prices via the Stripe API
2. Set the platform-wide default price id
3. Per-tenant override: set `plan_price_id` on a specific tenant row
4. Force-cancel or refund from within Stripe (link out to Stripe dashboard)

This is the "Single monthly plan but configurable from Super Admin" model
the tenant chose.

---

## 7. Environment variables on the hub

```
STRIPE_API_KEY=sk_live_...              # or sk_test_... for dev
STRIPE_WEBHOOK_SECRET=whsec_...         # from Stripe dashboard for /webhooks/stripe
DEFAULT_PLAN_PRICE_ID=price_...         # bootstrap default
PORTAL_CONFIGURATION_ID=bpc_...         # bootstrap default
```

> Use the platform's existing `emergentintegrations.payments.stripe` if
> available, or Stripe's official Python SDK — either works.

---

## 8. Testing checklist

1. `curl -H "X-Tenant-Id: tnt_curryco" -H "X-Tenant-Api-Key: sk_tnt_..." \
    <hub>/api/tenant/billing/summary` returns `status: "none"` for a fresh tenant.
2. `POST .../checkout` returns a real Stripe Checkout URL. Complete
   checkout with test card `4242 4242 4242 4242` → tenant summary
   flips to `active`, card on file shows `visa •••• 4242`.
3. `POST .../portal` returns a Customer Portal URL. Cancel from within
   → summary flips to `canceled` (or `active` + `cancel_at_period_end: true`
   depending on how the portal is configured).
4. Trigger `invoice.payment_failed` from Stripe CLI →
   `subscription_status` becomes `past_due`, banner appears on tenant.
5. Trigger `invoice.payment_succeeded` → status returns to `active`.
6. The existing `/api/tenant/status` endpoint keeps returning correct
   enforcement flags for every subscription state.

---

## 9. Non-goals for Phase 3

Deferred to Phase 4 per the tenant spec:
- Coupon/promo code input in the tenant Billing tab.
- Usage-based / per-order pricing tiers.
- Multi-currency (stick to USD for the platform fee for now).

---

## 10. Reference: matching tenant-side files

Already implemented in the tenant template (`Curry-Co-Template`):

- `backend/billing_client.py` — HTTP client with 60s cache
- `backend/server.py` — `/api/admin/billing/{summary,subscribe,portal}` (admin-JWT)
- `frontend/app/admin/billing.tsx` — the Billing UI
- `frontend/src/components/AdminShell.tsx` — new Billing nav item
- `frontend/src/components/PlatformBanner.tsx` — "Fix billing" routes to the tab

Nothing else on the tenant side needs to change once the hub ships these
3 endpoints.
