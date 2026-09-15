# Curry & Co. — App Store Publishing SOP

> **Purpose:** Step-by-step reference for shipping the Curry & Co. mobile apps (Customer + Delivery Partner) to the **Apple App Store** and the **Google Play Store**.
>
> **Owner:** Rakesh (Founder) — with agent-generated builds via **Emergent**
>
> **Last updated:** August 2026

---

## 📚 Table of contents

1. [Architecture recap](#0-architecture-recap)
2. [One-time prerequisites](#1-one-time-prerequisites)
3. [Every-release preflight checklist](#2-every-release-preflight-checklist)
4. [🍎 iOS — Apple App Store SOP](#3-ios--apple-app-store-sop)
5. [🤖 Android — Google Play Store SOP](#4-android--google-play-store-sop)
6. [Post-release monitoring](#5-post-release-monitoring)
7. [Emergency rollback playbook](#6-emergency-rollback-playbook)
8. [Support & escalation contacts](#7-support--escalation-contacts)
9. [Appendix A — Store assets checklist](#appendix-a--store-assets-checklist)
10. [Appendix B — Store copy templates](#appendix-b--store-copy-templates)
11. [Appendix C — Test credentials (redacted)](#appendix-c--test-credentials-redacted)

---

## 0. Architecture recap

Curry & Co. is a **single-codebase, multi-variant** Expo Router app:

| Variant             | `APP_VARIANT` | Where it ships               |
| ------------------- | ------------- | ---------------------------- |
| Customer            | `customer`    | App Store + Play Store       |
| Delivery Partner    | `delivery`    | App Store + Play Store       |
| Admin Web Portal    | `admin`       | Served from backend web_dist |

- **Backend:** FastAPI on Emergent Kubernetes, MongoDB Atlas, at `https://curry-ecosystem.emergent.host`.
- **Builds:** produced by **Emergent's Publish panel** — do **NOT** use EAS CLI or a personal Expo account.
- **Deployment domain:** managed by Emergent. Never modify DNS or the K8s config yourself.

---

## 1. One-time prerequisites

Do these once and never again unless credentials expire.

### 1.1 Legal & business

- [ ] Registered business entity (sole prop or corp) with a real address (Apple + Google both require this).
- [ ] A support email + support phone number (published on both listings).
- [ ] Privacy Policy hosted on a public URL — e.g. `https://curry-ecosystem.emergent.host/privacy.html`.
- [ ] Terms of Service hosted on a public URL.
- [ ] EULA (optional — Apple auto-supplies one if you don't).
- [ ] Refund policy page (linked from privacy policy).

### 1.2 Apple side — one-time

- [ ] **Apple Developer Program** membership — **US $99 / year**. Sign up at https://developer.apple.com/programs/enroll/.
    - Individual works; a company account needs a **D-U-N-S number** (free, takes 3–5 business days).
- [ ] **App Store Connect** access with an Admin role: https://appstoreconnect.apple.com.
- [ ] Apple ID with 2FA enabled + a trusted device to receive login codes.
- [ ] Bank account + tax forms (W-8BEN for non-US) set up under **Agreements, Tax, and Banking**. Apple will not release your app until this is 100% complete.

### 1.3 Google side — one-time

- [ ] **Google Play Console** account — **US $25 one-time**: https://play.google.com/console.
    - Registration approves in ~48 h; identity verification (photo of gov't ID) may be required.
- [ ] Merchant Center set up if you plan to accept in-app purchases (not required if you only sell physical food orders paid via COD/Interac).
- [ ] Bank + tax details filled in *Setup → Payments profile*.

### 1.4 Code / config

Check these values in `frontend/app.config.js` — **change now if wrong; you can never rename them after first upload**.

```js
{
  name: "Curry & Co.",
  slug: "curry-and-co",
  ios: {
    bundleIdentifier: "com.curryandco.customer",         // ← lock in
  },
  android: {
    package: "com.curryandco.customer",                  // ← lock in
    versionCode: 1,                                      // Emergent auto-bumps
  },
  version: "1.0.0",                                      // semver — human readable
}
```

> 🔒 **Once submitted, `bundleIdentifier` and `package` are permanent.** Renaming later means "new app, zero reviews, zero installs". Choose carefully.

---

## 2. Every-release preflight checklist

Do this **immediately before** you click *Generate Build* in Emergent. Tick every box.

- [ ] All new features validated on **Preview** (`emergent-preview.…dev`).
- [ ] Testing agent green (`/app/test_reports/iteration_*.json` — latest `should_call_test_agent_after_fix: false`).
- [ ] `test_credentials.md` up to date — reviewers need working logins for **customer** *and* **admin**.
- [ ] Backend redeployed via Emergent Publish → the K8s pod is running the latest commit.
- [ ] `frontend/app.config.js` `version` bumped (semver). Emergent auto-bumps `versionCode` (Android) and `buildNumber` (iOS).
- [ ] Release notes drafted (see [Appendix B](#appendix-b--store-copy-templates)).
- [ ] Fresh screenshots taken (if UI changed — see [Appendix A](#appendix-a--store-assets-checklist)).
- [ ] Privacy Policy page reflects any new data collected in the release (e.g., if you added camera → mention it).
- [ ] No mocked APIs, no `TODO: real key` in code.
- [ ] Delivery test done end-to-end on **production**: place order → driver accepts → driver GPS → customer sees moving pin.

---

## 3. iOS — Apple App Store SOP

### 3.1 Bundle identifier + certificates

You do **not** need to manually create certificates when using Emergent. Emergent handles signing.
When Emergent prompts you for **Apple credentials** during the first Publish, provide:

1. Apple Developer team ID (found at https://developer.apple.com/account → *Membership Details*).
2. App Store Connect API key (create at *Users and Access → Keys → App Store Connect API → +*).
   - Role: **App Manager**
   - Download the `.p8` file — save it in your password manager, you can only download it once.
   - Note the **Issuer ID** and **Key ID**.
3. Provide the `.p8`, Issuer ID, and Key ID to Emergent in the Publish panel.

### 3.2 Create the app record in App Store Connect

1. Sign in to https://appstoreconnect.apple.com.
2. **Apps → +** → **New App**.
3. Fill:
    - Platform: **iOS**
    - Name: `Curry & Co.` (public-facing, ≤ 30 chars)
    - Primary language: English (Canada)
    - Bundle ID: pick the one Emergent registered on Apple Developer (should show as `com.curryandco.customer`)
    - SKU: `curry-co-customer-001` (internal only — any string)
    - User Access: Full Access
4. Click **Create**.

Repeat for the **Delivery Partner** app if you're shipping it separately (`com.curryandco.delivery`, SKU `curry-co-delivery-001`).

### 3.3 Fill the "App Information" page

Left sidebar → **App Information**:

- [ ] **Category — Primary:** *Food & Drink*. **Secondary:** *Lifestyle*.
- [ ] **Content Rights:** *Does not contain third-party content*.
- [ ] **Age Rating:** Click **Edit** → answer the questionnaire honestly (usually 4+ for a food app).
- [ ] **Privacy Policy URL** (required).

### 3.4 Fill "Pricing and Availability"

- [ ] **Price:** Free
- [ ] **Availability:** deselect **All Countries or Regions** → pick **Canada** only (or wherever you deliver).

### 3.5 Fill the "1.0 Prepare for Submission" page

Left sidebar → click **1.0**:

- [ ] **App Preview and Screenshots** — see [Appendix A](#appendix-a--store-assets-checklist).
- [ ] **Promotional Text** (≤ 170 chars) — updated any time without a re-review.
- [ ] **Description** (≤ 4000 chars) — see [Appendix B](#appendix-b--store-copy-templates).
- [ ] **Keywords** (≤ 100 chars, comma-separated).
- [ ] **Support URL:** `https://curry-ecosystem.emergent.host/support`.
- [ ] **Marketing URL** (optional).
- [ ] **Version** (from `app.config.js`).
- [ ] **Copyright:** `© 2026 Curry & Co.`.
- [ ] **App Review Information:**
    - Contact name + email + phone
    - **Demo credentials** — paste from `test_credentials.md`. Reviewers **will** log in.
    - Notes: "The app requires a Canada-based address to place an order. Use the demo customer account (email/phone above). No Stripe payment is required — Cash on Delivery works."

### 3.6 App Privacy (data disclosure)

Left sidebar → **App Privacy → Get Started**. Declare each data type:

| Data type              | Collected? | Linked to user? | Used for tracking? | Purpose                         |
| ---------------------- | ---------- | --------------- | ------------------ | ------------------------------- |
| Name                   | Yes        | Yes             | No                 | App functionality (account)     |
| Email                  | Yes        | Yes             | No                 | Account + order confirmations   |
| Phone                  | Yes        | Yes             | No                 | Order updates + driver contact  |
| Physical address       | Yes        | Yes             | No                 | Delivery                        |
| Precise Location       | Yes        | Yes             | No                 | Delivery tracking (driver only) |
| Purchase history       | Yes        | Yes             | No                 | Order history                   |
| Device ID (push token) | Yes        | Yes             | No                 | Push notifications              |

- Confirm **no data used for third-party tracking**.

### 3.7 Trigger the iOS build via Emergent

1. Open Emergent dashboard → **Publish** (top-right).
2. Choose **Generate iOS build** → variant **Customer** (repeat for **Delivery** if applicable).
3. Wait ~15–30 min. Emergent will upload the `.ipa` to App Store Connect and mark it as a **TestFlight build**.
4. Back in App Store Connect → **TestFlight** tab → wait for **"Processing" → "Ready to Test"** (~10 min).
5. Add **Internal testers** (up to 100 people, use your own Apple IDs) → they get an email → install via **TestFlight** app.
6. Test the full flow on a physical device — auth, ordering, tracking, push, deep-links.

### 3.8 Submit for review

Only after TestFlight looks solid:

1. On the **1.0 Prepare for Submission** page → scroll to **Build** section → click **+** → pick the tested build.
2. Answer **Export Compliance** questions (Curry & Co. uses HTTPS only → *"Uses standard encryption exempt from EAR"* → **Yes / No** as appropriate; most cases: standard HTTPS → *No*).
3. Answer **Advertising Identifier** → **No** (unless you added an ad SDK).
4. Click **Add for Review** → **Submit to App Review**.

### 3.9 Expected timeline & responses

- **In Review** typically starts within 24 h.
- **Approved** in 1–3 days for a first release. Updates go faster.
- If **Rejected**:
    - Read the reviewer's note in **App Store Connect → Resolution Center**.
    - Common Curry & Co. reasons: "guest access" (Apple wants a way to browse without full sign-up) → fix by allowing menu browse without login; "metadata unclear" → tighten description.
    - Fix → **Reply** to the reviewer explaining what changed → resubmit.

### 3.10 Release strategy

Choose one on the version page:

- **Manually release this version** → you press a button after approval (recommended for first launch).
- **Automatically release this version** → goes live the moment it's approved.
- **Phased release** → rolls out to 1% → 100% over 7 days. Good for de-risking. Use for major updates.

---

## 4. Android — Google Play Store SOP

### 4.1 Create the app record in Play Console

1. https://play.google.com/console → **Create app**.
2. Fill:
    - App name: `Curry & Co.`
    - Default language: English (Canada)
    - App or game: **App**
    - Free or paid: **Free**
    - Confirm both declarations → **Create app**.
3. Repeat for the **Delivery Partner** app if separate.

### 4.2 Complete the "Set up your app" checklist

Play Console shows a to-do list. Tick each item:

| Item                     | Answer for Curry & Co.                                              |
| ------------------------ | ------------------------------------------------------------------- |
| App access               | *"All functionality is available without restrictions"* + demo creds if you gated any admin routes |
| Ads                      | *No, my app does not contain ads*                                   |
| Content rating           | Complete the IARC questionnaire → typically **Everyone**            |
| Target audience          | Age: **18+** (or your minimum service age)                          |
| News app                 | No                                                                  |
| COVID-19 contact tracing | No                                                                  |
| Government app           | No                                                                  |
| Financial features       | Yes → *"Facilitates purchases of physical goods"*                   |
| App category             | **Food & Drink**                                                    |
| Store settings           | External store contact = your support email                         |

### 4.3 Data safety declaration

Left sidebar → **App content → Data safety → Manage**.

Declare each data type — mirror the Apple table in §3.6. For each:

- Encrypted in transit: **Yes**
- Users can request data deletion: **Yes** (provide a link like `mailto:privacy@curryandco.ca`)
- Complies with **Play Families Policy**: N/A (target 18+)

### 4.4 Fill the "Main store listing"

- [ ] App icon (512 × 512) — see [Appendix A](#appendix-a--store-assets-checklist).
- [ ] Feature graphic (1024 × 500).
- [ ] Screenshots (phone: 2–8; tablet 7"/10": optional but recommended).
- [ ] Short description (≤ 80 chars).
- [ ] Full description (≤ 4000 chars).
- [ ] Category: **Food & Drink**.
- [ ] Tags: `Bengali`, `Indian`, `Delivery`, `Cloud kitchen`, `Home cooked`.
- [ ] Contact details (email + phone + website).
- [ ] Privacy Policy URL.

### 4.5 Trigger the Android build via Emergent

1. Emergent dashboard → **Publish** → **Generate Android build**.
2. Two files come out:
    - **`.APK`** — for sideloading / manual testing on your own phone.
    - **`.AAB`** (Android App Bundle) — **the file you upload to Play Store**.
3. Download the `.AAB`. Never rename it (Emergent embeds the version code in the filename).

### 4.6 Upload to Closed testing (do this first — do NOT go straight to Production)

1. Play Console → **Testing → Closed testing → Create track**.
2. Track name: `alpha` (or `internal-qa`).
3. Add tester email list (yourself + a few friends).
4. **Create new release** → drag the `.AAB` in.
5. **Release name:** `1.0.0-alpha` (matches `app.config.js` version).
6. **Release notes:**
    ```
    English – Canada:
    First alpha of Curry & Co. — Bengali & Indian cloud kitchen delivery.
    Includes weekly menus, catering packages, and live driver tracking.
    ```
7. **Save → Review release → Start rollout to Alpha**.
8. Wait for Google's **automated + human review** (typically 1–7 days for the first-ever submission; hours for subsequent).
9. Testers install via the opt-in link shown on the Alpha track page.

### 4.7 Promote to Production

Only after alpha is stable for **at least 3 days**:

1. **Production → Create new release → Add from library** → pick the reviewed AAB.
2. Select target **countries** (Canada only, or wherever you deliver).
3. **Staged rollout percentage:** start at **20%** for 2–3 days → watch the Vitals dashboard → bump to **50%** → **100%**.

### 4.8 Common rejection reasons — pre-empt

| Reason                                       | How to avoid                                                                      |
| -------------------------------------------- | --------------------------------------------------------------------------------- |
| Location permission unclear                  | Match the wording in `app.config.js` `NSLocationWhenInUseUsageDescription` + Data Safety |
| Camera permission unused but declared        | Remove `android.permissions.CAMERA` if the customer variant doesn't take photos    |
| No visible privacy policy link inside app    | Add a "Privacy Policy" link in the Settings screen                                |
| Health / medical claims in copy              | Avoid "healthy", "diet", "medical" — stick to "authentic", "chef-prepared"        |
| Broken demo login                            | Verify the credentials in Play Console **the day you submit**                     |
| Undisclosed background location              | Curry & Co. uses foreground-only — don't add `ACCESS_BACKGROUND_LOCATION`         |
| Doesn't work on Android 8 (API 26)           | Emergent builds already target API 34+ / min 24; verify in `expo build` logs      |

### 4.9 Expected timeline

- First submission: **3–7 days** (can stretch to 14).
- Updates: **24–48 hours**.
- Rejections are handled in **Publishing overview → Rejected releases** — read the reason → fix → regenerate build in Emergent → upload → resubmit.

---

## 5. Post-release monitoring

For the first 72 hours after each release, watch:

### iOS

- **App Store Connect → Analytics** — impressions, installs, crashes.
- **App Store Connect → App Analytics → Crashes** — investigate any crash > 0.5% users.

### Android

- **Play Console → Statistics** — install/uninstall ratio.
- **Play Console → Quality → Android vitals** — crash rate < 1%, ANR rate < 0.5%.
- **Reviews** tab — reply to negative reviews within 24 h.

### Backend

- Emergent dashboard → **Deployments → Logs** — 5xx spike?
- Watch order volume in Admin portal → sudden zero means the app is broken.

---

## 6. Emergency rollback playbook

Something's broken in a shipped version:

### iOS

1. **Cannot** delete a shipped iOS build. Instead:
    - Fix in preview → Emergent Publish → new iOS build → App Store Connect → **Expedited Review** request (from **Contact Us**) → mention "app is unusable".
    - Expedited approvals often within 6–12 h.
2. If it's a backend regression only — **redeploy the previous backend commit** via `git revert` + Emergent Publish → the shipped iOS app will start working immediately.

### Android

1. **Play Console → Production → Halt rollout** → stops future users installing the bad version.
2. **Create new release** with the previous good AAB (download from **App bundle explorer**) → bump versionCode +1 → rollout.

### Backend

- All state is in MongoDB Atlas → point-in-time recovery is 24 h in Atlas Free tier / 7 days on Serverless. Contact Emergent Support if you need a restore.

---

## 7. Support & escalation contacts

| Need                                     | Contact                                                             |
| ---------------------------------------- | ------------------------------------------------------------------- |
| Emergent build fails / backend deploy    | **support@emergent.sh** (include job ID from top-right info panel)  |
| Apple developer / App Store Connect      | https://developer.apple.com/contact/                                |
| Google Play Console                      | https://support.google.com/googleplay/android-developer             |
| Stripe (once re-enabled)                 | https://support.stripe.com                                          |
| Twilio (SMS exports)                     | https://support.twilio.com                                          |
| MongoDB Atlas                            | via Emergent Support (Emergent manages the cluster on your behalf)  |

---

## Appendix A — Store assets checklist

Keep these in `/app/store-assets/` (create the folder in the repo).

### App icon

- **File:** `icon-1024.png` (1024 × 1024, PNG, no transparency, no rounded corners — Apple + Play auto-round).
- **Used for:** app icon on both stores.

### Adaptive Android icon (extra)

- **File:** `icon-adaptive-foreground.png` (432 × 432 safe zone inside 512 × 512).

### Feature graphic (Play Store only)

- **File:** `feature-graphic-1024x500.png` (1024 × 500).

### Phone screenshots

At least **3**, ideally **5**, per app store. Recommended screens to feature:

1. Home / this week's menu with combo hero card.
2. Item detail with add-to-bag stepper.
3. Bag / checkout showing tax + total.
4. Live tracking map with driver icon.
5. Order confirmation with celebratory illustration.

Resolutions:
- **iOS 6.7"** (iPhone 15 Pro Max, required): 1290 × 2796.
- **iOS 6.5"** (iPhone 11 Pro Max, required if you don't have 6.7"): 1242 × 2688.
- **iOS 5.5"** (iPhone 8 Plus, optional): 1242 × 2208.
- **Android phone:** 1080 × 1920 (portrait) or 1920 × 1080 (landscape).

### App preview videos (optional but boosts conversion)

- 15–30 sec, MP4, up to 3 per app.

---

## Appendix B — Store copy templates

### Short description (Play Store, ≤ 80 chars)

> Bengali & Indian home-style meals, delivered fresh across the GTA.

### Full description (≤ 4000 chars)

```
Curry & Co. brings authentic, home-style Bengali and Indian meals from our
Toronto cloud kitchen to your doorstep. We publish a fresh weekly menu every
Sunday — order between Sunday and Thursday, and we hand-deliver on Friday
and Saturday, piping hot.

WHAT'S ON THE MENU
• A weekly combo curated by our chef (six portions from a rotating shortlist)
• À la carte specials — from Kolkata Chicken Biryani to Shorshe Ilish
• Catering packages priced per guest for family gatherings and office events

WHY YOU'LL LOVE IT
• Real driver tracking on a live map (like your favourite ride app)
• A live "Arriving in ~X min" countdown that actually keeps ticking
• Loyalty points on every order — save toward a free meal
• Pay by Cash on Delivery or Interac e-Transfer — no card details stored
• Delivery across the Greater Toronto Area

DIETARY OPTIONS
Every item is tagged veg / non-veg / vegan so you always know what you're
getting. Weekly menus include at least one gluten-free option.

CUSTOMER SUPPORT
Our team replies in under 4 hours during business hours. Reach us at
support@curryandco.ca or via in-app chat.

Sunday–Thursday ordering. Friday–Saturday delivery. See you at the table.
```

### Keywords (App Store, ≤ 100 chars, comma-separated)

> bengali,indian,food,delivery,cloud kitchen,biryani,catering,toronto,gta,home cooked

### Release notes template

```
Version 1.0.X

What's new:
• [Feature or improvement 1]
• [Feature or improvement 2]

Fixes:
• [Bug fix 1]
• [Bug fix 2]

Thanks for feasting with us! Rate us if you're enjoying the meals.
```

---

## Appendix C — Test credentials (redacted)

The **real** credentials live in `/app/memory/test_credentials.md` and are never committed to the public repo.

Provide reviewers with:

| Role      | Where to enter                     | What we tell the reviewer                                                            |
| --------- | ---------------------------------- | ------------------------------------------------------------------------------------ |
| Customer  | Home → Sign in                     | "Use the email/phone in `App Review Information → Demo Account`"                    |
| Admin     | Not needed (reviewers only test the customer flow) | —                                                                                    |

If Apple/Google **require** an admin login for review, use the seeded reviewer account from `test_credentials.md`. **Rotate the password after approval.**

---

## 📝 Release-day playbook (quick reference)

```
□ 1. Preview all features working
□ 2. Testing agent green
□ 3. Bump `version` in app.config.js
□ 4. Update /app/memory/PRD.md with the change
□ 5. Emergent → Publish → Redeploy backend
□ 6. Emergent → Publish → Generate iOS + Android build
□ 7. iOS: upload processes automatically → verify in TestFlight
□ 8. Android: download AAB → upload to Closed testing track
□ 9. Test on real device via TestFlight + Play alpha
□ 10. Submit to App Store review + promote Android to Production
□ 11. Post release notes on your own Instagram / socials
□ 12. Monitor crash + review dashboards for 72 h
```

Godspeed 🚀
