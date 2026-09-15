/**
 * Centralized backend URL resolver.
 *
 * On WEB (Expo web / Admin portal): uses window.location.origin so that whether
 * the compiled bundle is served from the preview host, the production host, or
 * any future custom domain, API calls go to the SAME ORIGIN. This avoids
 * needing to rebuild the web bundle every time the deployment URL changes.
 *
 * On NATIVE (iOS/Android): uses EXPO_PUBLIC_BACKEND_URL as before.
 */
import { Platform } from "react-native";

export function getBackendUrl(): string {
  if (Platform.OS === "web" && typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return (process.env.EXPO_PUBLIC_BACKEND_URL as string) || "";
}

/**
 * Resolve a media/image path returned by the backend into a fully-qualified URL.
 * Backend serves uploaded images as relative paths like "/api/uploads/menu/x.png".
 * On native (Expo Go / device) relative URLs have no origin, so <Image> can't load
 * them — we must prefix the backend host. Absolute http(s)/data URLs pass through.
 */
export function mediaUrl(path?: string | null): string {
  if (!path) return "";
  if (/^(https?:)?\/\//i.test(path) || path.startsWith("data:")) return path;
  const base = getBackendUrl();
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}
