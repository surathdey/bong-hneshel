# 🔁 CLONE.md — Fork this template into a new restaurant brand

This repo is the **Curry & Co. reference implementation** of the
**Suparna Dey SaaS Restaurant Platform**. Every restaurant is a self-contained
fork of this repo with only the branding config swapped.

> **Time to launch a new brand:** ~30 minutes (config) + Emergent deploy time.

---

## 📋 Prerequisites

- [ ] A copy of this repo on your GitHub (fork or push a clone).
- [ ] A new **Emergent project** targeting the forked repo.
- [ ] Your new brand's:
    - App name (e.g. `Jomidari`)
    - Legal entity name (e.g. `Suparna Dey Enterprise Inc.` — this stays the same across restaurants because YOU are the parent)
    - Colors (primary, primaryDark, secondary, accent — 4 hex codes)
    - Support email + phone
    - Region (country / currency / timezone)
    - Bundle ID (e.g. `com.jomidari.customer`) — **must be unique** on the App Store
    - Android package (usually the same as bundle ID)
    - Logo assets: `logo.png`, `logo-square.png`, `splash.png`, `notification-icon.png`, `adaptive-icon.png`

---

## 🚀 Step-by-step (5 files, 1 folder)

### 1. `frontend/brand.config.js`
Open it. Change EVERY string. Don't skip any. Reference the file's inline comments — they explain each field.

```js
const brand = {
  key: "jomidari",
  name: "Jomidari",
  legalName: "Suparna Dey Enterprise Inc.",
  tagline: "Modern zamindar-era cuisine, delivered.",
  colors: {
    primary:     "#7B2D26",   // your brand red
    primaryDark: "#5A1F1B",
    secondary:   "#D4A017",
    accent:      "#1E4145",
  },
  support: {
    email: "hello@jomidari.com",
    phone: "+1-416-555-0200",
    website: "https://jomidari-ecosystem.emergent.host",
    privacyUrl: "https://jomidari.com/privacy",
    termsUrl:   "https://jomidari.com/terms",
  },
  region: {
    country: "CA",
    currency: "CAD",
    currencySymbol: "$",
    timezone: "America/Toronto",
    defaultCity: "Toronto",
    serviceArea: "the Greater Toronto Area",
  },
  native: {
    customer: {
      bundleIdentifier: "com.jomidari.customer",
      androidPackage:   "com.jomidari.customer",
      deepLinkScheme:   "jomidari",
    },
    delivery: {
      bundleIdentifier: "com.jomidari.delivery",
      androidPackage:   "com.jomidari.delivery",
      deepLinkScheme:   "jomidaridelivery",
    },
  },
  copy: {
    aboutBlurb:     "Jomidari — modern zamindar-era cuisine.",
    deleteWarning:  "This permanently removes your profile from Jomidari.",
    deleteFarewell: "Your data has been removed. Thanks for trying Jomidari.",
    orderTagline:   "Fresh chef-curated meals, delivered weekly.",
  },
  // ...
};
```

### 2. `brand.json` (at the repo root)
Mirror the brand config on the backend side. Update every field to match.

```json
{
  "key": "jomidari",
  "name": "Jomidari",
  "legal_name": "Suparna Dey Enterprise Inc.",
  "email_from": "orders@jomidari.com",
  "admin_email": "admin@jomidari.local",
  "support_email": "hello@jomidari.com",
  "guest_email_domain": "guest.jomidari.local",
  "delivery_admin_email": "delivery@jomidari.local",
  "region": {
    "country": "CA",
    "currency": "CAD",
    "timezone": "America/Toronto"
  }
}
```

### 3. `frontend/assets/brand/*`
Drop new PNGs into this folder. **Keep the filenames identical** to what's referenced in `brand.config.js → assets`. Recommended dimensions:

| File                    | Size          | Purpose                                       |
| ----------------------- | ------------- | --------------------------------------------- |
| `logo.png`              | 1024×1024     | Login screen + admin sidebar                  |
| `logo-square.png`       | 512×512       | Splash, tab icons                             |
| `splash.png`            | 2048×2048     | iOS + Android launch screen                   |
| `notification-icon.png` | 96×96 (mono)  | Android status bar (single-color)             |
| `adaptive-icon.png`     | 432×432 fg    | Android adaptive icon (foreground layer)      |

### 4. `frontend/app.config.js`
**Don't edit — it auto-reads from `brand.config.js`.**

### 5. `frontend/src/theme.ts`
**Don't edit — colors are pulled from `brand.config.js`.**

### 6. Repository-wide search
Run this before you deploy to catch any hardcoded string that slipped through:

```bash
grep -rn "Curry & Co\|curryandco\|Suparna Dey" \
  --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=web_dist \
  --exclude=CLONE.md --exclude=PUBLISH_SOP.md --exclude=README.md .
```

Expected result: **zero hits inside `frontend/app/**`, `frontend/src/**`, or `backend/**`**. If you find a hit, wire that string through `BRAND` / `brand.py` and commit.

---

## 🧪 Test locally

```bash
# from repo root
cd frontend && yarn install
cd ..
cd backend && pip install -r requirements.txt
```

Restart Expo + FastAPI → open the customer app → the top of the login screen and admin sidebar should show the NEW brand name.

---

## ☁️ Deploy the new brand

1. New Emergent project → point at the forked repo.
2. Emergent Deploy Secrets → set:
    - `JWT_SECRET` (any 64-char random string; different from Curry's)
    - `ADMIN_EMAIL` = the value in `brand.json`
    - `ADMIN_PASSWORD` (strong; store in your password manager)
    - `MONGO_URL` = a NEW MongoDB Atlas cluster (or a separate DB inside the shared cluster)
    - `EXPO_PUBLIC_GOOGLE_MAPS_API_KEY` — reuse the parent org's key if quota allows
    - Any brand-specific overrides you like: `BRAND_NAME`, `BRAND_EMAIL_FROM`, etc.
3. Emergent → Publish → Deploy Backend.
4. Emergent → Publish → Generate iOS + Android builds. (Follow `docs/PUBLISH_SOP.md`.)
5. Register the new tenant in the Suparna Dey Platform → generate `tenantId` + `apiKey` → paste into `brand.config.js → platform`.

Done. Welcome the new restaurant to the family. 🍽

---

## 🛡 Multi-tenant guardrails

- **Never share MongoDB collections across tenants.** Each fork = separate DB.
- **Never share JWT_SECRET across tenants.** Otherwise a compromised secret compromises every restaurant.
- **Never share Emergent projects.** One project = one tenant.
- **Stripe:** the parent org (Suparna Dey Enterprise Inc.) collects subscriptions from each restaurant → each restaurant's own Stripe (once we turn on card payments) is separate.
