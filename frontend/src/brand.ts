/**
 * Runtime brand context — the ONE place TypeScript code should import from
 * to reach brand-specific values. It re-exports `brand.config.js` with a
 * fully-typed interface.
 *
 * Do NOT import from `brand.config.js` directly in your components — this
 * file exists so the type-checker catches typos + so we can extend the
 * shape without editing every call site.
 */

// eslint-disable-next-line @typescript-eslint/no-var-requires
const brandJs = require("../brand.config.js");

export type BrandColors = {
  primary: string;
  primaryDark: string;
  secondary: string;
  accent: string;
};

export type BrandContact = {
  email: string;
  phone: string;
  website: string;
  privacyUrl: string;
  termsUrl: string;
};

export type BrandRegion = {
  country: string;
  currency: string;
  currencySymbol: string;
  timezone: string;
  defaultCity: string;
  serviceArea: string;
};

export type BrandNativeVariant = {
  bundleIdentifier: string;
  androidPackage: string;
  deepLinkScheme: string;
};

export type BrandCopy = {
  aboutBlurb: string;
  deleteWarning: string;
  deleteFarewell: string;
  orderTagline: string;
};

export type BrandPlatform = {
  tenantId: string | null;
  apiKey: string | null;
  statusUrl: string | null;
};

export type BrandConfig = {
  key: string;
  name: string;
  legalName: string;
  tagline: string;
  colors: BrandColors;
  support: BrandContact;
  region: BrandRegion;
  native: {
    customer: BrandNativeVariant;
    delivery: BrandNativeVariant;
  };
  copy: BrandCopy;
  assets: Record<string, string>;
  platform: BrandPlatform;
};

export const BRAND: BrandConfig = brandJs;

// Convenience shorthands — most components only need one of these.
export const BRAND_NAME = BRAND.name;
export const BRAND_COLORS = BRAND.colors;
export const BRAND_SUPPORT = BRAND.support;
export const BRAND_REGION = BRAND.region;
export const BRAND_COPY = BRAND.copy;
