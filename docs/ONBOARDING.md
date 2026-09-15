# 🍽 How to Onboard a New Restaurant Client

> **Time to launch a new restaurant on the Suparna Dey Platform: ~45 min end-to-end.**

This is the single source of truth for spinning up a new restaurant brand (e.g. Jomidari, Bombay Bistro, etc.) using the Curry-Co-Template SaaS platform.

If you're onboarding your *first* client (Jomidari), start at **Step 0**.
If you already have one client running and you're adding a second, jump to **Step 2**.

---

## 📚 Table of contents

1. [Prerequisites](#0-prerequisites)
2. [Create the client's GitHub repo](#1-create-the-clients-github-repo)
3. [Create the client's Emergent project](#2-create-the-clients-emergent-project)
4. [Rebrand the template](#3-rebrand-the-template)
5. [Register the tenant on Super Admin](#4-register-the-tenant-on-super-admin)
6. [Wire the phone-home credentials](#5-wire-the-phone-home-credentials)
7. [Import the seed pack (optional)](#6-import-the-seed-pack-optional)
8. [Deploy + smoke test](#7-deploy--smoke-test)
9. [Generate iOS + Android builds](#8-generate-ios--android-builds)
10. [Ongoing operations](#9-ongoing-operations)

---

## 🏗 Architecture recap

There are **TWO kinds of Emergent projects** in this ecosystem:

| Project                                                       | Purpose                                                                                 |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **`suparna-dey-platform`** (Central Hub — Super Admin)        | ONE Emergent project. Tenant registry, subscription mgmt, coupons. Owned by you.        |
| **`curry-and-co`**, **`jomidari`**, etc. (Tenant Restaurants) | ONE Emergent project per restaurant. Each = fork of `Curry-Co-Template`.                |

Each tenant restaurant:
- Has its own MongoDB
- Has its own admin login
- Has its own customer + delivery apps + Play/App Store listings
- **Phones home** to `suparna-dey-platform` every 5 min to check subscription status

The **`Curry-Co-Template`** GitHub repo is the golden master.
Every time you improve a feature in Curry & Co.'s codebase, **push that improvement back into `Curry-Co-Template`** so future clones inherit it. See [§Ongoing operations](#9-ongoing-operations).

---

## 0. Prerequisites

Before you start onboarding any client, make sure these one-time setups are done:

- [ ] `Curry-Co-Template` GitHub repo exists and has the latest platform-client / brand-config / seed-tools changes merged into `main`.
- [ ] `suparna-dey-platform` is deployed and reachable at `https://control-plane-11.preview.emergentagent.com` (or your production URL).
- [ ] You have super-admin login credentials for the platform.
- [ ] You have an Emergent account with room for another project (each project ≈ one small K8s pod).
- [ ] Client has provided:
    - Restaurant name (e.g. `Jomidari`)
    - Brand colors (4 hex codes: primary, primaryDark, secondary, accent)
    - Logo assets (5 PNGs — see [Step 3](#3-rebrand-the-template))
    - Support email + phone
    - Owner name + email (goes into Suparna Dey as the tenant owner)
    - Domain (optional at MVP — Emergent gives you one)

---

## 1. Create the client's GitHub repo

You have three ways to do this. Pick one.

### Option A — GitHub "Use this template" button (simplest)
1. Go to `https://github.com/YOUR-ORG/Curry-Co-Template`.
2. Click **Use this template → Create a new repository**.
3. Repo name: `jomidari` (all lowercase, hyphens ok).
4. Owner: your GitHub username or org.
5. Visibility: **Private** (recommended).
6. Click **Create repository from template**.

> ⚠️ If you don't see the "Use this template" button, enable it via `Curry-Co-Template → Settings → General → check "Template repository"`.

### Option B — Fork with maintained upstream (recommended for long-running clients)
```bash
git clone https://github.com/YOUR-ORG/Curry-Co-Template jomidari
cd jomidari
git remote rename origin upstream          # keep template as read-only source
git remote add origin git@github.com:YOU/jomidari.git
git push -u origin main
```

Later, pull template improvements:
```bash
git fetch upstream
git merge upstream/main
```

### Option C — Plain clone (one-shot, no upstream link)
```bash
git clone https://github.com/YOUR-ORG/Curry-Co-Template jomidari
cd jomidari
rm -rf .git
git init
git remote add origin git@github.com:YOU/jomidari.git
git add . && git commit -m "Initial fork of Curry-Co-Template" && git push
```

---

## 2. Create the client's Emergent project

1. Sign in at https://app.emergent.sh.
2. **New Project** → give it a memorable name: `jomidari-ecosystem`.
3. Source → **"Import from GitHub"** → authorize Emergent (one-time OAuth) → pick the new repo.
4. Branch: `main`.
5. Emergent clones the repo into a fresh sandbox with its own MongoDB and Google Maps quota inheritance.

### Set the Deploy Secrets

Emergent dashboard → **Deploy Secrets** (or **Environment**) → add:

| Key                              | Value                                                                                        |
| -------------------------------- | -------------------------------------------------------------------------------------------- |
| `MONGO_URL`                      | Emergent auto-provisions — do NOT overwrite                                                  |
| `DB_NAME`                        | `jomidari` (or whatever Emergent picked)                                                     |
| `JWT_SECRET`                     | A **fresh** 64-char random string. `openssl rand -hex 32` on your terminal. **Never reuse Curry's.** |
| `ADMIN_EMAIL`                    | e.g. `admin@jomidari.local`                                                                  |
| `ADMIN_PASSWORD`                 | Strong new password. Store in your password manager.                                          |
| `EXPO_PUBLIC_GOOGLE_MAPS_API_KEY`| Copy from Curry if the same Google Cloud project (quota allows) or use a new key             |
| `EMERGENT_LLM_KEY`               | Copy from Curry (universal key)                                                               |
| `EMERGENT_PUSH_KEY`              | Leave as-is — Emergent manages this                                                          |
| `EMAIL_FROM`                     | e.g. `orders@jomidari.com`                                                                   |

> 🛡 **Security rule:** every tenant has its own `JWT_SECRET`, `MONGO_URL`, and `ADMIN_PASSWORD`. Never share secrets between tenants.

---

## 3. Rebrand the template

Open the Emergent chat inside the new project and send this prompt:

> Rebrand this Curry-Co-Template fork to **Jomidari**. Follow `CLONE.md` in the repo. Update these files:
>
> **1. `frontend/brand.config.js`** — change every field. Specifically:
> - `key: "jomidari"`
> - `name: "Jomidari"`
> - `legalName: "Suparna Dey Enterprise Inc."` (parent stays the same)
> - `tagline: "<Jomidari tagline>"`
> - `colors: { primary: "#XXXXXX", primaryDark: "#XXXXXX", secondary: "#XXXXXX", accent: "#XXXXXX" }`
> - `support.email: "hello@jomidari.com"`
> - `support.phone: "+1-..."`
> - `native.customer.bundleIdentifier` + `native.customer.androidPackage`: `"com.jomidari.customer"`
> - `native.delivery.bundleIdentifier` + `native.delivery.androidPackage`: `"com.jomidari.delivery"`
> - `native.customer.deepLinkScheme: "jomidari"`
> - `native.delivery.deepLinkScheme: "jomidaridelivery"`
> - Update all `copy.*` fields to reference "Jomidari" not "Curry & Co."
>
> **2. `brand.json`** at the repo root — mirror the same values in `key`, `name`, `email_from`, `admin_email`, `support_email`, `guest_email_domain`, `delivery_admin_email`.
>
> **3. Logo assets** — I'll drop 5 PNGs (`logo.png`, `logo-square.png`, `splash.png`, `notification-icon.png`, `adaptive-icon.png`) into `frontend/assets/brand/` via the paperclip. Replace the pixels but **keep the filenames identical**.
>
> **4. Grep sanity check** — run:
> ```bash
> grep -rn "Curry & Co\|curryandco" --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=web_dist --exclude=CLONE.md --exclude=ONBOARDING.md .
> ```
> Should return zero hits inside `frontend/app/**`, `frontend/src/**`, `backend/**`. If any hit exists, plumb it through `BRAND` / `brand.py`.
>
> **5. Restart backend + expo**, run the testing agent, screenshot the login screen — should show **"Jomidari"** in the header (not Curry).

Attach the 5 logo PNGs in the same or a follow-up message.

---

## 4. Register the tenant on Super Admin

Go to your **Suparna Dey Platform** (`https://control-plane-11.preview.emergentagent.com`) → log in as super admin.

### 4.1 Create the tenant

Left sidebar → **Tenants** → **`+ New Tenant`** button → fill:

| Field                       | Value                                                          |
| --------------------------- | -------------------------------------------------------------- |
| **Key** (slug)              | `jomidari` — must match `brand.json → key` exactly             |
| **Name**                    | `Jomidari`                                                     |
| **Legal name**              | `Suparna Dey Enterprise Inc.`                                   |
| **Deployment URL**          | Your new Emergent project's public URL                          |
| **Owner name**              | e.g. `Rakesh Dey` (or the person actually running that brand)  |
| **Owner email**             | e.g. `owner@jomidari.com`                                      |
| **Owner phone**             | Phone                                                          |
| **Country / Currency / TZ** | `CA / CAD / America/Toronto`                                    |
| **Plan**                    | `starter` (or `growth` / `enterprise` / `custom`)               |
| **Monthly fee (cents)**     | e.g. `9900` = $99/mo                                            |
| **Trial length (days)**     | `14` (or `0` for immediate paid)                                |
| **Status**                  | `active` (or `trial`)                                           |

Click **Create**.

### 4.2 Copy the API key ONCE

The response modal shows the `sk_tnt_v1_...` key. **Copy it immediately** — the platform hashes it after this. If you lose it, use **Rotate API Key** in the tenant detail page.

---

## 5. Wire the phone-home credentials

Back in the Jomidari Emergent chat, paste this:

> Update `brand.json` at the repo root — add this `platform` block. Keep everything else as-is:
>
> ```json
> "platform": {
>   "tenant_id": "tnt_jomidari",
>   "api_key": "sk_tnt_v1_<PASTE_THE_KEY_FROM_SUPER_ADMIN>",
>   "status_url": "https://control-plane-11.preview.emergentagent.com/api/tenant/status",
>   "poll_seconds": 300
> }
> ```
>
> Restart the backend. Verify with:
> ```bash
> curl -s http://localhost:8001/api/platform/status | python3 -m json.tool
> ```
> Expected: `known: true, operational: true, subscription_status: "active"` (or `"trialing"` if you set a trial).

**Sanity check the round-trip:**

1. Confirm in the Super Admin dashboard that Jomidari's row now shows **"Last heartbeat: <a few seconds ago>"**.
2. Suspend the tenant → within 5 min (or restart Jomidari backend for instant effect) → open its customer app → tap Place Order → you should get a **402 with copy that says the restaurant owner missed billing**.
3. Reactivate → next poll → checkout works again.

---

## 6. Import the seed pack (optional)

If you want Jomidari to open on day one with 46 dishes ready to rename (instead of an empty menu), use the Curry seed pack:

### 6a. Copy the seed pack into the fork

If Jomidari was forked from Curry-Co-Template, the seed pack should already exist at `docs/seed-packs/curryco_seed_pack.json`.
If not, download it from Curry-Co-Template's GitHub UI and drag-drop it into the Jomidari chat.

### 6b. Run the importer

In Jomidari's Emergent chat:

> Import the Curry seed pack into this tenant DB:
>
> ```bash
> cd backend
> python3 -m tools.seed_import /app/docs/seed-packs/curryco_seed_pack.json
> ```
>
> Then restart backend, log into the admin portal, open the Menu page. Confirm 46 dishes appear. Screenshot it.

The seed pack contains:
- 46 master menu items (Bengali dishes)
- 3 weekly menu templates
- 5 catering packages
- 3 coupon codes
- 1 business-settings row (brand-specific fields blanked; filled from `brand.json`)

Once imported, ask the agent:

> Rename every dish in `master_menu` from Bengali-Curry style to **<Jomidari's brand style>**. Keep the same categories, prices, and images — just rewrite `name` and `description`.

---

## 7. Deploy + smoke test

1. Emergent → **Publish** → **Redeploy backend**. Wait ~2 min. Jomidari's backend goes live at `https://jomidari-ecosystem.emergent.host` (or whatever URL Emergent gave you).
2. Open the URL → the admin login should show **Jomidari**, not Curry.
3. Log in with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` you set in Deploy Secrets.
4. Create a menu, add an item, publish a weekly menu.
5. Sign up as a customer via the mobile app (side-loaded APK or Expo Go).
6. Place a test order → verify receipt says **Jomidari**, not Curry.
7. **Cross-check data isolation**: log into Curry's admin in a different browser tab → confirm the Jomidari test order does NOT appear there.

---

## 8. Generate iOS + Android builds

See **`docs/PUBLISH_SOP.md`** for the full step-by-step. TL;DR:

- Emergent → Publish → Generate iOS build (via App Store Connect API key).
- Emergent → Publish → Generate Android build → download the `.APK` for sideload, `.AAB` for Play Store.
- App Store Connect + Google Play Console listings are **separate per tenant** because each has its own bundle ID + package name.

**Critical:** Every restaurant has its **own** Play Store + App Store listing (as we designed in Phase 5). Do not try to share a listing between brands.

---

## 9. Ongoing operations

### 9.1 Push improvements from Curry back to the template

Curry-Co-Template is your **golden master**. Whenever you or the AI agent improves a feature in Curry & Co.'s repo (`curry-and-co`), replicate the change back into `Curry-Co-Template`.

**Two-way sync workflow (recommended for the current stage):**

```bash
# In Curry & Co.'s repo (after a feature ships):
git log --oneline -20                                 # find the commit(s) to promote

# In Curry-Co-Template's local clone:
git remote add curry https://github.com/YOU/curry-and-co.git
git fetch curry
git cherry-pick <commit-sha-from-curry>              # promote just the wanted commits
git push origin main
```

**Every commit that lands in Curry-Co-Template automatically becomes part of every future rebrand.** The current changes that MUST be in Curry-Co-Template as of Phase 2:

- [ ] `frontend/brand.config.js` — brand config system
- [ ] `frontend/src/brand.ts` — typed re-export
- [ ] `backend/brand.py` — Python brand config
- [ ] `brand.json` — data-side brand config
- [ ] `backend/platform_client.py` — Suparna Dey phone-home client
- [ ] `backend/tools/seed_export.py` + `backend/tools/seed_import.py` — seed pack tools
- [ ] `docs/seed-packs/curryco_seed_pack.json` — reference dataset
- [ ] `frontend/src/components/PlatformBanner.tsx` — subscription-status banner
- [ ] Server-side gates on `POST /api/orders` + `POST /api/delivery/login` (402 when platform blocks)
- [ ] `CLONE.md` — rebrand playbook
- [ ] `docs/ONBOARDING.md` — this file
- [ ] `docs/PUBLISH_SOP.md` — App/Play store SOP

### 9.2 Pull template updates into an existing tenant

If you fixed a bug or added a feature in the template and want to backport into Jomidari:

```bash
cd jomidari                              # local clone
git remote add template https://github.com/YOU/Curry-Co-Template.git
git fetch template
git merge template/main                  # or cherry-pick specific commits
# resolve conflicts (brand.json + brand.config.js will always conflict — keep the tenant's)
git push origin main
```

Then Emergent → Publish → Redeploy Jomidari's backend to get the fix live.

### 9.3 Suspend a tenant (billing dispute, offboarding, TOS violation)

Super Admin dashboard → Tenants → click the tenant → **Suspend**. Within 5 min:

- The tenant's customer app returns **402** on checkout with the copy: *"[Restaurant] is temporarily paused because the restaurant owner has not completed their platform subscription payment."*
- The tenant's delivery-partner app returns **402** on login.
- The tenant's admin portal shows a red banner at the top.

**Reactivate:** flip status back to `active` → next poll → all traffic resumes.

**Kill immediately** (no 5-min wait): also tell the tenant's Emergent project to restart backend, which forces an immediate phone-home on cold-boot.

### 9.4 Rotate an API key (if leaked)

Super Admin → Tenants → tenant detail → **Rotate API Key**. Then paste the new key into the tenant's `brand.json → platform.api_key` and restart backend. Old key is immediately rejected with `401`.

### 9.5 Monitor tenant health

Super Admin dashboard shows for each tenant:
- Last heartbeat timestamp (if >15 min ago → alert)
- Subscription status (active / trialing / past_due / cancelled)
- MRR contribution (Phase 3+, when Stripe is wired)
- Orders in last 24 h (Phase 3+, when we add cross-tenant analytics)

---

## 🎯 Full onboarding checklist (print this)

```
CLIENT NAME: ______________________  ONBOARDING DATE: __________

□ 1. Prerequisites collected (colors, logos, owner info)
□ 2. GitHub repo created from Curry-Co-Template
□ 3. Emergent project created + pointed at new repo
□ 4. Deploy Secrets set (JWT, admin, Mongo, etc.)
□ 5. brand.config.js rebranded (all fields)
□ 6. brand.json rebranded (all fields)
□ 7. Logo PNGs replaced in assets/brand/
□ 8. Grep confirms zero "Curry & Co" leaks
□ 9. Tenant registered on Super Admin dashboard
□ 10. sk_tnt_... key pasted into brand.json → platform
□ 11. Backend restarted → /api/platform/status shows known:true, operational:true
□ 12. Super Admin shows the tenant with "last heartbeat: seconds ago"
□ 13. Seed pack imported (optional)
□ 14. Menu customized for this brand
□ 15. Test order placed end-to-end
□ 16. Test order visible only in this tenant's admin (data isolation ✅)
□ 17. Suspension test: platform blocks checkout with correct message
□ 18. Reactivation test: platform restores service
□ 19. Backend published to production
□ 20. iOS + Android builds generated
□ 21. App Store Connect + Play Console listings created (see PUBLISH_SOP.md)
□ 22. TestFlight + Play alpha testers invited
□ 23. Store listings submitted for review
□ 24. Handoff docs shared with the client's team
```

Estimated time end-to-end (excluding App/Play review): **~45 min** for someone who has done it once.

---

## 📞 Escalation

| Issue                                          | Contact                                                             |
| ---------------------------------------------- | ------------------------------------------------------------------- |
| Emergent build fails / backend deploy stuck    | `support@emergent.sh` (include job ID)                              |
| Super Admin platform down / can't reach it     | Contact platform engineering team                                    |
| Client asks for a refund                       | `support@emergent.sh`                                                |
| Bug on a specific tenant only                  | Fix in that tenant's Emergent project → then port to template        |
| Bug across all tenants                         | Fix in `Curry-Co-Template` → cherry-pick to every active tenant repo |
