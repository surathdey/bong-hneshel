/**
 * Admin API client — thin fetch wrapper. Uses a separate token stored via universal storage.
 * Sends Authorization: Bearer <admin_token>.
 */
import { storage } from "@/src/utils/storage";
import { getBackendUrl } from "@/src/utils/backendUrl";

const ADMIN_TOKEN_KEY = "curryco.admin.token";

export type AdminResult<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

export async function getAdminToken(): Promise<string | null> {
  return await storage.getItem<string>(ADMIN_TOKEN_KEY, "");
}
export async function setAdminToken(t: string) { await storage.setItem(ADMIN_TOKEN_KEY, t); }
export async function clearAdminToken() { await storage.removeItem(ADMIN_TOKEN_KEY); }

async function request<T>(method: string, path: string, body?: any): Promise<AdminResult<T>> {
  const token = await getAdminToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  try {
    const res = await fetch(`${getBackendUrl()}/api${path}`, {
      method, headers, body: body ? JSON.stringify(body) : undefined,
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

export const adminApi = {
  get: <T = any>(path: string) => request<T>("GET", path),
  post: <T = any>(path: string, body?: any) => request<T>("POST", path, body),
  put: <T = any>(path: string, body?: any) => request<T>("PUT", path, body),
  patch: <T = any>(path: string, body?: any) => request<T>("PATCH", path, body),
  del: <T = any>(path: string) => request<T>("DELETE", path),
};
