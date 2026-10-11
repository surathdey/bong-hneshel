# 🍛 Bong Hneshel — API Reference

- **Base URL:** `<your-domain>` (all app endpoints are prefixed with `/api`)
- **Auth:**
  - **Customer** endpoints use a session token (cookie/bearer) issued by `/api/auth/*`.
  - **Admin** endpoints require an admin bearer token from `POST /api/admin/login` → `Authorization: Bearer <token>`.
  - **Delivery partner** endpoints require a partner token from `POST /api/delivery/login`.
- **Interactive schema:** FastAPI generates an OpenAPI schema at the service root (`/openapi.json`) when accessed directly on the backend.

---

## 1. Auth & Profile (customer)
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Create an email/password account (optional phone). Triggers welcome email + first-order coupon. |
| POST | `/api/auth/login` | Email/password login. |
| POST | `/api/auth/logout` | End the current session. |
| GET  | `/api/auth/me` | Current logged-in user. |
| POST | `/api/auth/guest` | Start a guest session (checkout without an account). |
| POST | `/api/auth/session` | Issue/refresh a session token. |
| POST | `/api/auth/forgot-password` | Request a password-reset email. |
| POST | `/api/auth/reset-password` | Complete password reset with the emailed token. |
| POST | `/api/me/profile` | Update profile (name, phone). |
| POST | `/api/me/address` | Add/update a saved address. |
| DELETE | `/api/me/address` | Remove a saved address. |
| DELETE | `/api/user/me` | Delete the user's own account. |

## 2. Menu & Catalog (public)
| Method | Path | Description |
|---|---|---|
| GET | `/api/menu/current` | This week's menu (items include `avg_rating` + `review_count`). |
| GET | `/api/menu/upcoming` | Next week's menu. |
| GET | `/api/menu/history` | Past menus. |
| GET | `/api/menu/anytime` | "Always Available" items. |
| GET | `/api/catering` | Catering packages. |
| GET | `/api/catering/{package_id}` | A single catering package. |
| POST | `/api/catering/quote-request` | Request a catering quote. |
| GET | `/api/settings` | Public business settings (hours, loyalty/reviews toggles, etc.). |
| GET | `/api/brand` | Brand name/colors/metadata. |

## 3. Cart, Orders & Checkout (customer)
| Method | Path | Description |
|---|---|---|
| POST | `/api/orders/quote` | Price a cart (subtotal, tax, discounts, loyalty) before placing. |
| POST | `/api/orders` | Place an order (COD / Interac). |
| GET | `/api/orders` | List the customer's orders. |
| GET | `/api/orders/{order_id}` | Order detail. |
| POST | `/api/orders/{order_id}/cancel-unpaid` | Cancel an unpaid order. |
| GET | `/api/orders/{order_id}/tracking` | Live delivery tracking data. |
| POST | `/api/checkout/session` | Create a Stripe hosted-checkout session (card). |
| GET | `/api/checkout/status/{session_id}` | Poll a checkout session's status. |
| POST | `/api/checkout/webhook` | Stripe webhook (payment events). |
| GET | `/api/checkout/success` / `/api/checkout/cancel` | Stripe redirect landings. |
| GET | `/api/invoice/{order_id}` | Order invoice (HTML/link). |
| GET | `/api/track/{order_id}` | Public tracking page data. |

## 4. Coupons, Loyalty & Referrals (customer)
| Method | Path | Description |
|---|---|---|
| GET | `/api/coupons/{code}` | Validate/lookup a coupon. |
| GET | `/api/coupons/first-time` | The active first-order coupon (for the Home banner). |
| GET | `/api/coupons/promo` | Active promo coupon(s). |
| GET | `/api/referrals/me` | The user's referral code + stats. |
| POST | `/api/referrals/redeem` | Apply a referral code. |

## 5. Reviews (public + token-gated)
| Method | Path | Description |
|---|---|---|
| GET | `/api/menu-items/{item_id}/reviews` | Approved reviews + rating summary for a dish. |
| GET | `/api/reviews/summary?item_ids=a,b` | Batch rating summary for multiple dishes. |
| GET | `/api/reviews/request/{token}` | Load the dishes to review (no login, token link). |
| POST | `/api/reviews/submit` | Submit ratings/comments (held for admin moderation). |

## 6. Address / Maps (public)
| Method | Path | Description |
|---|---|---|
| GET | `/api/places/autocomplete` | Google Places address autocomplete. |
| GET | `/api/places/details` | Place details for a selected suggestion. |
| POST | `/api/delivery/geocode` | Address → coordinates. |
| POST | `/api/delivery/reverse-geocode` | Coordinates → address. |

## 7. Delivery Partner app
| Method | Path | Description |
|---|---|---|
| POST | `/api/delivery/login` | Partner login. |
| GET | `/api/delivery/me` | Current partner profile. |
| GET | `/api/delivery/orders` | Orders assigned to the partner. |
| POST | `/api/delivery/route` | Optimize a delivery route. |
| POST | `/api/delivery/journey/start` | Start delivery → notifies customers (ETA SMS + tracking link). |
| GET | `/api/delivery/journey/current` | Current active journey. |
| POST | `/api/delivery/journey/end` | End the journey. |
| POST | `/api/delivery/location` | Push live GPS location. |
| POST | `/api/delivery/orders/{order_id}/status` | Update a stop (delivered → confirmation SMS; next stop gets exact ETA). |
| POST | `/api/delivery/orders/{order_id}/proof` | Upload proof-of-delivery photo. |
| POST | `/api/delivery-partner/apply` | Public driver application. |

## 8. Admin — Auth & Dashboard
| Method | Path | Description |
|---|---|---|
| POST | `/api/admin/login` | Admin login → bearer token. |
| GET | `/api/admin/me` | Current admin. |
| GET | `/api/admin/stats` | Dashboard KPIs. |
| GET | `/api/admin/settings` · PUT `/api/admin/settings` | Read/update business settings (payments, tax, loyalty, referrals, reviews). |

## 9. Admin — Menu & Catalog
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/admin/master-menu` | List / create master dishes. |
| GET/DELETE | `/api/admin/master-menu/{item_id}` | Read / delete a dish. |
| POST | `/api/admin/master-menu/{item_id}/duplicate` | Duplicate a dish. |
| POST | `/api/admin/master-menu/bulk` · `/bulk-preview` · `/bulk-save` | Bulk import dishes (AI-assisted). |
| GET/POST | `/api/admin/menus` · `/menus/create` | Weekly menus. |
| POST/DELETE | `/api/admin/menus/{week_start}/items` · `/items/{item_id}` | Manage weekly items. |
| POST/DELETE | `/api/admin/menus/{week_start}/lines` · `/lines/{line_id}` | Manage v2 menu lines. |
| POST | `/api/admin/menus/{week_start}/lines/{line_id}/visibility` | Toggle line visibility. |
| POST | `/api/admin/menus/{week_start}/complimentary` · `/settings` | Weekly extras / settings. |
| DELETE | `/api/admin/menus/{week_start}` | Delete a weekly menu. |
| GET/POST | `/api/admin/always-available` | Manage "Always Available" items. |
| GET/POST/DELETE | `/api/admin/catering` · `/catering/{package_id}` | Catering packages. |

## 10. Admin — Orders
| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/orders` | List/filter all orders. |
| GET | `/api/admin/order-builder` | Data needed to build a new order (menus, slots, master items). |
| POST | `/api/admin/orders/create` | Create an order on behalf of a customer (supports **custom dishes**; fires full email + SMS confirmation). |
| POST | `/api/admin/orders/{order_id}/status` | Update order status. |
| POST | `/api/admin/orders/{order_id}/assign` | Assign a delivery partner. |
| POST | `/api/admin/orders/{order_id}/refund` | Refund an order. |
| POST | `/api/admin/orders/export` | Export orders (download/Drive/SMS). |

## 11. Admin — Customers
| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/customers` | Customer list with stats. |
| GET | `/api/admin/customers/{user_id}` | Customer detail (orders, addresses, loyalty history). |
| POST | `/api/admin/customers` | Create a single customer. |
| POST | `/api/admin/customers/bulk-upload` | **Import customers from CSV** (de-dupes by email/phone). |
| POST | `/api/admin/customers/export` | Export customers. |

## 12. Admin — Coupons, Referrals & Reviews
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/admin/coupons` | List / create coupons. |
| PUT/DELETE | `/api/admin/coupons/{code}` | Update / delete a coupon. |
| GET | `/api/admin/coupons/{code}/redemptions` | Who redeemed a coupon. |
| GET | `/api/admin/referrals/leaderboard` | Referral leaderboard. |
| GET | `/api/admin/reviews` | Moderation queue (pending/approved/rejected + counts). |
| POST | `/api/admin/reviews/{review_id}/moderate` | Approve/reject a review. |
| DELETE | `/api/admin/reviews/{review_id}` | Delete a review. |
| POST | `/api/admin/reviews/bulk-upload` | Import historical reviews from CSV (auto-approved). |

## 13. Admin — Delivery, Integrations & Billing
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/admin/delivery-partners` | List / create drivers. |
| PATCH/DELETE | `/api/admin/delivery-partners/{partner_id}` | Update / remove a driver. |
| GET | `/api/admin/integrations` | Integration status. |
| PUT/POST | `/api/admin/integrations/twilio` · `/twilio/test` | Twilio SMS config + test. |
| PUT/POST | `/api/admin/integrations/email` · `/email/test` | Email (Resend) config + test. |
| PUT/POST | `/api/admin/integrations/google-drive` · `/google-drive/test` | Google Drive config + test. |
| GET | `/api/admin/billing/summary` | Subscription/billing summary. |
| POST | `/api/admin/billing/subscribe` · `/billing/portal` | Manage billing. |

## 14. System / Misc
| Method | Path | Description |
|---|---|---|
| GET | `/health`, `/healthz` | Liveness probes. |
| GET | `/api/health/web-bundle` | Production web-bundle freshness diagnostic. |
| GET | `/api/platform/status` | Platform integration status. |
| POST | `/api/register-push` | Register a device push token. |
| GET | `/api/exports/{token}` | Download a generated export file. |
| GET | `/api/downloads/pitch-deck` | Pitch-deck download. |
| GET | `/api/legal/privacy` | Privacy policy. |
| POST | `/api/dev/seed` | Seed demo data (dev). |

_Total: 138 routes. Customer/admin/delivery sections require the appropriate auth token._
