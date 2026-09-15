/**
 * Curry & Co. — Expo config (dynamic).
 *
 * This project produces TWO separate native apps from ONE codebase, plus a WEB
 * admin portal:
 *
 *   1. Customer App  (iOS + Android)  → default variant "customer"
 *   2. Delivery App  (iOS + Android)  → variant "delivery"
 *   3. Admin Portal  (Web only)       → served at /admin on the web bundle
 *
 * Select the variant at build time with an env variable:
 *
 *   APP_VARIANT=customer   npx expo prebuild / eas build   (default)
 *   APP_VARIANT=delivery   npx expo prebuild / eas build
 *
 * The variant is exposed to JavaScript via `Constants.expoConfig.extra.appVariant`.
 * See `/app/frontend/app/_layout.tsx` for how the root layout redirects users
 * to the correct entry point (customer tabs vs `/delivery-partner`).
 */

const APP_VARIANT = process.env.APP_VARIANT || "customer";

// One source of truth for brand-specific values. Rebrand this whole app by
// editing brand.config.js — never edit hardcoded strings here.
const brand = require("./brand.config.js");

const shared = {
  version: "1.0.0",
  orientation: "portrait",
  userInterfaceStyle: "automatic",
  web: {
    bundler: "metro",
    output: "single",
    favicon: "./assets/images/favicon.png",
  },
  plugins: [
    "expo-router",
    "expo-notifications",
    "expo-font",
    "expo-image",
    "expo-secure-store",
    "expo-web-browser",
    "@react-native-vector-icons/ionicons",
    [
      "expo-splash-screen",
      {
        image: "./assets/images/splash-image.png",
        imageWidth: 200,
        resizeMode: "contain",
        backgroundColor: "#FAF9F6",
      },
    ],
  ],
  experiments: { typedRoutes: true },
};

const variants = {
  customer: {
    name: brand.name,
    slug: "frontend",
    scheme: brand.native.customer.deepLinkScheme,
    icon: "./assets/images/icon.png",
    ios: {
      supportsTablet: true,
      bundleIdentifier: brand.native.customer.bundleIdentifier,
      infoPlist: {
        NSLocationWhenInUseUsageDescription: "Show delivery address on map",
        NSCameraUsageDescription: "Upload profile picture",
        NSPhotoLibraryUsageDescription: "Choose photos for menu items and profile",
        // U.S. Export Compliance — our app uses only iOS-provided crypto (HTTPS,
        // JWT auth, bcrypt) which qualifies for the "authentication only" and
        // "OS-provided" exemptions. Declaring this in Info.plist means Apple
        // stops asking on every TestFlight build.
        ITSAppUsesNonExemptEncryption: false,
      },
    },
    android: {
      adaptiveIcon: {
        foregroundImage: "./assets/images/adaptive-icon.png",
        backgroundColor: brand.colors.primary,
      },
      package: brand.native.customer.androidPackage,
      permissions: ["NOTIFICATIONS"],
    },
  },
  delivery: {
    // Separate app store listing.
    name: `${brand.name} Delivery`,
    slug: "frontend-delivery",
    scheme: brand.native.delivery.deepLinkScheme,
    // Uses the same icon for MVP; swap for a delivery-specific icon later.
    icon: "./assets/images/icon.png",
    ios: {
      supportsTablet: true,
      bundleIdentifier: brand.native.delivery.bundleIdentifier,
      infoPlist: {
        NSLocationWhenInUseUsageDescription:
          "Show your live location so we can optimize delivery routes and share ETA with customers.",
        // NOTE: We only poll geolocation in-foreground while the driver app is
        // open. Do NOT declare NSLocationAlwaysAndWhenInUseUsageDescription
        // unless we actually implement background tracking — over-declaration
        // causes Apple review rejections.
        // Same export-compliance declaration for the delivery variant.
        ITSAppUsesNonExemptEncryption: false,
      },
    },
    android: {
      adaptiveIcon: {
        foregroundImage: "./assets/images/adaptive-icon.png",
        backgroundColor: "#00A651",
      },
      package: brand.native.delivery.androidPackage,
      permissions: [
        "NOTIFICATIONS",
        "ACCESS_FINE_LOCATION",
        "ACCESS_COARSE_LOCATION",
        // ACCESS_BACKGROUND_LOCATION intentionally removed — foreground-only.
      ],
    },
  },
};

const variant = variants[APP_VARIANT] || variants.customer;

module.exports = {
  expo: {
    ...shared,
    ...variant,
    extra: {
      appVariant: APP_VARIANT,
      // Expose the maps key via `extra` too, so it works even when read from
      // Constants (some native runners strip process.env).
      googleMapsApiKey:
        process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY || "",
      // Ship the whole brand config to the runtime so components can read it
      // via `Constants.expoConfig?.extra?.brand` when they can't import
      // `src/brand.ts` (e.g. splash screen JS).
      brand,
    },
  },
};
