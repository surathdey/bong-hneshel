/**
 * ============================================================
 *  BRAND CONFIG — the ONE file you edit to rebrand this app.
 * ============================================================
 *
 *  To spin up a new restaurant from this template:
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
  key: "bonghneshel",                    // slug used in package IDs + folders
  name: "Bong Hneshel",                  // public-facing brand name
  legalName: "Bong Hneshel",             // for receipts + T&Cs
  tagline: "Home Food, Delivered",

  // ─── Colors (all UI palette flows from here) ─────────────
  //   Auto-derived from logo-square.png (deep-purple monochrome logo):
  //   primary = most-frequent non-white/non-black color; primaryDark = ×0.8;
  //   secondary = 180° hue complement (logo has no distinct 2nd hue), toned
  //   to a contrast-safe emerald; accent = safe dark-teal default.
  colors: {
    primary:     "#3C053C",              // deep purple (logo background)
    primaryDark: "#300430",              // pressed/hover (primary × 0.8)
    secondary:   "#1AA34A",              // emerald accent (180° of primary)
    accent:      "#2F4F4F",              // dark teal (info states)
  },

  // ─── Contact + support ───────────────────────────────────
  support: {
    email: "support@bong-hneshel.ca",
    phone: "",
    website: "https://bong-hneshel.ca",
    privacyUrl: "https://bong-hneshel.ca/privacy",
    termsUrl:   "https://bong-hneshel.ca/terms",
  },

  // ─── Regional / operational ──────────────────────────────
  region: {
    country: "CA",
    currency: "CAD",
    currencySymbol: "$",                 // shown in checkout
    timezone: "America/Toronto",
    defaultCity: "Toronto",
    serviceArea: "the Greater Toronto Area",
  },

  // ─── Native app metadata (per platform) ──────────────────
  //   These are consumed by app.config.js. Once shipped they are IMMUTABLE.
  native: {
    customer: {
      bundleIdentifier: "com.bonghneshel.customer",     // iOS
      androidPackage:   "com.bonghneshel.customer",     // Android
      deepLinkScheme:   "bonghneshel",                  // bonghneshel://order/xyz
    },
    delivery: {
      bundleIdentifier: "com.bonghneshel.delivery",
      androidPackage:   "com.bonghneshel.delivery",
      deepLinkScheme:   "bonghnesheldelivery",
    },
  },

  // ─── Copy overrides (short strings shown in UI) ──────────
  copy: {
    aboutBlurb:     "Bong Hneshel — home food, delivered fresh across the Greater Toronto Area.",
    deleteWarning:  "This permanently removes your profile, order history, addresses, and loyalty points from Bong Hneshel. This cannot be undone.",
    deleteFarewell: "Your data has been removed. Thanks for trying Bong Hneshel.",
    orderTagline:   "Home food, delivered fresh.",
  },

  // ─── Asset paths (relative to /assets/brand/) ────────────
  //   Keep the filenames identical when rebranding — just replace the pixels.
  assets: {
    logo:            "./assets/brand/Bong-Hneshel-Logo.jpg",
    logoSquare:      "./assets/brand/logo-square.png",
    splash:          "./assets/brand/splash.png",
    notificationIcon:"./assets/brand/notification-icon.png",
    adaptiveIcon:    "./assets/brand/adaptive-icon.png",
  },

  // ─── Platform tenant registration (Phase 2/3 — platform control plane) ─
  //   Empty until this tenant is registered in the Super Admin portal.
  //   In preview these can stay empty — the phone-home poller short-circuits
  //   and no platform enforcement gates apply.
  platform: {
    tenantId:     "",
    apiKey:       "",
    statusUrl:    "https://control-plane-11.preview.emergentagent.com/api/tenant/status",
  },
};

module.exports = brand;
