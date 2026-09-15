/**
 * API client — thin fetch wrapper. Always uses EXPO_PUBLIC_BACKEND_URL + /api prefix.
 * Adds Authorization: Bearer <token> if a session token is stored in secure storage.
 */
import { storage } from "@/src/utils/storage";
import { getBackendUrl } from "@/src/utils/backendUrl";

export const BACKEND_URL_STATIC = process.env.EXPO_PUBLIC_BACKEND_URL as string;
// Runtime resolver — prefer this on web so bundle isn't tied to a specific host.
export const BACKEND_URL = BACKEND_URL_STATIC;
export const SESSION_KEY = "curryco.session_token";

export type ApiResult<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

export async function getToken(): Promise<string | null> {
  return await storage.secureGet<string>(SESSION_KEY, "");
}

export async function setToken(token: string) {
  await storage.secureSet(SESSION_KEY, token);
}

export async function clearToken() {
  await storage.secureRemove(SESSION_KEY);
}

async function request<T>(method: string, path: string, body?: any): Promise<ApiResult<T>> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  try {
    const res = await fetch(`${getBackendUrl()}/api${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let data: any = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) return { ok: false, status: res.status, error: data?.detail || text || "Error" };
    return { ok: true, data: data as T };
  } catch (e: any) {
    return { ok: false, status: 0, error: e?.message || "Network error" };
  }
}

export const api = {
  get: <T = any>(path: string) => request<T>("GET", path),
  post: <T = any>(path: string, body?: any) => request<T>("POST", path, body),
  put: <T = any>(path: string, body?: any) => request<T>("PUT", path, body),
  del: <T = any>(path: string) => request<T>("DELETE", path),
};
