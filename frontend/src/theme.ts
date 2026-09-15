/**
 * Theme tokens — driven by `brand.config.js`.
 * The palette (`primary`, `primaryDark`, `secondary`, `accent`) is pulled
 * from the brand config so a fork can rebrand the whole app without
 * touching this file. Neutrals (background, text, border, etc.) stay here
 * because they're rarely brand-specific.
 */
import { BRAND } from "./brand";

export const colors = {
  background: "#FAF9F6",
  surface: "#FFFFFF",
  surfaceAlt: "#F3EEE5",
  primary: BRAND.colors.primary,
  primaryDark: BRAND.colors.primaryDark,
  secondary: BRAND.colors.secondary,
  accent: BRAND.colors.accent,
  text: "#2C2C2C",
  textMuted: "#6B7280",
  border: "#E5E7EB",
  danger: "#B91C1C",
  success: "#166534",
  overlay: "rgba(0,0,0,0.35)",
  chipBg: "#F0E7D8",
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 18,
  xl: 24,
  pill: 999,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
};

export const shadows = {
  card: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 12,
    elevation: 3,
  },
  soft: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },
};

export const fonts = {
  heading: "System",
  body: "System",
};
