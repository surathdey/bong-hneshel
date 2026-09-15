/**
 * ============================================================
 *  BRAND CONFIG — the ONE file you edit to rebrand this app.
 * ============================================================
 *
 *  To spin up a new restaurant (e.g. "Jomidari") from this template:
 *    1. Fork the repo on GitHub
 *    2. Edit THIS file — change every value below to match your brand
 *    3. Drop new logo assets into `assets/brand/` (keep filenames the same)
 *    4. Commit + deploy in Emergent
 *
 *  Nothing else in the codebase should be edited for a rebrand. If you find
 *  yourself hand-editing UI strings or colors elsewhere, that value belongs
 *  HERE — please add it and reference it instead.
 *
 *  This file is consumed by:
 *    • `app.config.js`         → app name, bundle ID, package, deep-link scheme
 *    • `src/brand.ts`          → runtime brand context (colors, copy, contact)
 *    • `backend/brand.py`      → server-side name/email/phone in receipts
 *
 *  Note: this file uses CommonJS so it can be `require()`'d by app.config.js
 *  AND imported from TypeScript via a companion type re-export.
 * ============================================================
 */

/** @type {import('./brand.types').BrandConfig} */
const brand = {
  // ─── Identity ────────────────────────────────────────────
  key: "mustardgarden",                  // slug used in package IDs + folders
  name: "Mustard Garden",                // public-facing brand name
  legalName: "Mustard Garden",           // for receipts + T&Cs
  tagline: "Exotic flavors of India — Milton, ON",

  // ─── Colors (all UI palette flows from here) ─────────────
  colors: {
    primary:     "#FBB03B",              // mustard amber (logo background)
    primaryDark: "#C98D2F",              // pressed/hover (primary × 0.8)
    secondary:   "#5D1114",              // deep maroon (chef hat + "GARDEN")
    accent:      "#2F4F4F",              // dark teal (info states)
  },

  // ─── Contact + support ───────────────────────────────────
  support: {
    email: "support@mustardgarden.ca",
    phone: "+1-437-499-9453",
    website: "https://mustardgarden.ca",
    privacyUrl: "https://mustardgarden.ca/privacy",
    termsUrl:   "https://mustardgarden.ca/terms",
  },

  // ─── Regional / operational ──────────────────────────────
  region: {
    country: "CA",
    currency: "CAD",
    currencySymbol: "$",                 // shown in checkout
    timezone: "America/Toronto",
    defaultCity: "Milton",
    serviceArea: "Milton and the Greater Toronto Area",
  },

  // ─── Native app metadata (per platform) ──────────────────
  //   These are consumed by app.config.js. Once shipped they are IMMUTABLE.
  native: {
    customer: {
      bundleIdentifier: "com.mustardgarden.customer",     // iOS
      androidPackage:   "com.mustardgarden.customer",     // Android
      deepLinkScheme:   "mustardgarden",                  // mustardgarden://order/xyz
    },
    delivery: {
      bundleIdentifier: "com.mustardgarden.delivery",
      androidPackage:   "com.mustardgarden.delivery",
      deepLinkScheme:   "mustardgardendelivery",
    },
  },

  // ─── Copy overrides (short strings shown in UI) ──────────
  copy: {
    aboutBlurb:     "Mustard Garden — exotic flavors of India, delivered fresh across Milton, ON.",
    deleteWarning:  "This permanently removes your profile, order history, addresses, and loyalty points from Mustard Garden. This cannot be undone.",
    deleteFarewell: "Your data has been removed. Thanks for trying Mustard Garden.",
    orderTagline:   "Exotic Indian flavors, delivered fresh.",
  },

  // ─── Asset paths (relative to /assets/brand/) ────────────
  //   Keep the filenames identical when rebranding — just replace the pixels.
  assets: {
    logo:            "./assets/brand/logo.png",
    logoSquare:      "./assets/brand/logo-square.png",
    splash:          "./assets/brand/splash.png",
    notificationIcon:"./assets/brand/notification-icon.png",
    adaptiveIcon:    "./assets/brand/adaptive-icon.png",
  },

  // ─── Platform tenant registration (Phase 2/3 — Suparna Dey Platform) ─
  //   These wire this restaurant into the central SaaS platform.
  platform: {
    // Empty until this tenant is registered in the Super Admin portal.
    // In preview these can stay empty — the phone-home poller short-circuits
    // and no platform enforcement gates apply.
    tenantId:     "tnt_264dfe34083a",
    apiKey:       "sk_tnt_b2mdcGJ1TBajUojrmk-rj4n7DXboPsLf",
    statusUrl:    "https://control-plane-11.preview.emergentagent.com/api/tenant/status",
  },
};

module.exports = brand;
