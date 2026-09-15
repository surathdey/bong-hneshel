/**
 * Delivery Partner API client.
 * Standalone JWT auth; token stored under `curryco.delivery.token`.
 */
import { storage } from "@/src/utils/storage";
import { getBackendUrl } from "@/src/utils/backendUrl";

const TOKEN_KEY = "curryco.delivery.token";

export async function getDeliveryToken(): Promise<string | null> {
  return await storage.getItem<string>(TOKEN_KEY, "");
}
export async function setDeliveryToken(t: string) { await storage.setItem(TOKEN_KEY, t); }
export async function clearDeliveryToken() { await storage.setItem(TOKEN_KEY, ""); }

export type DResult<T> = { ok: boolean; status: number; data?: T; error?: string };

async function request<T>(method: string, path: string, body?: any): Promise<DResult<T>> {
  const token = await getDeliveryToken();
  const url = `${getBackendUrl()}/api${path}`;
  try {
    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const status = res.status;
    let data: any = null;
    try { data = await res.json(); } catch {}
    if (!res.ok) {
      return { ok: false, status, error: (data?.detail || data?.error || `HTTP ${status}`) };
    }
    return { ok: true, status, data: data as T };
  } catch (e: any) {
    return { ok: false, status: 0, error: e?.message || "Network error" };
  }
}

export const deliveryApi = {
  get: <T = any>(path: string) => request<T>("GET", path),
  post: <T = any>(path: string, body?: any) => request<T>("POST", path, body),
  patch: <T = any>(path: string, body?: any) => request<T>("PATCH", path, body),
  del: <T = any>(path: string) => request<T>("DELETE", path),
};

/** Upload a proof-of-delivery photo (multipart). Works on native + web. */
export async function uploadDeliveryProof(
  orderId: string, uri: string,
): Promise<DResult<{ delivery_proof_photo_url: string }>> {
  const token = await getDeliveryToken();
  const url = `${getBackendUrl()}/api/delivery/orders/${orderId}/proof`;
  const name = (uri.split("?")[0].split("/").pop()) || "proof.jpg";
  const ext = (name.split(".").pop() || "jpg").toLowerCase();
  const type = ext === "png" ? "image/png" : ext === "webp" ? "image/webp" : "image/jpeg";
  const form = new FormData();
  try {
    if (typeof document !== "undefined") {
      // Web: turn the local/blob uri into a real Blob so it attaches correctly.
      const blob = await (await fetch(uri)).blob();
      form.append("photo", blob, name);
    } else {
      // Native: RN FormData file descriptor.
      // @ts-ignore
      form.append("photo", { uri, name, type });
    }
    const res = await fetch(url, {
      method: "POST",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: form,
    });
    const status = res.status;
    let data: any = null;
    try { data = await res.json(); } catch {}
    if (!res.ok) return { ok: false, status, error: data?.detail || `HTTP ${status}` };
    return { ok: true, status, data };
  } catch (e: any) {
    return { ok: false, status: 0, error: e?.message || "Upload failed" };
  }
}

/** Google Static Maps helper — returns an HTTPS URL to a PNG map. */
export function staticMapUrl(opts: {
  size?: string;         // "600x300"
  center?: string;       // "lat,lng"
  zoom?: number;
  markers?: Array<{ lat: number; lng: number; label?: string; color?: string }>;
  polyline?: string;     // encoded polyline
}): string {
  const key = process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY || "";
  const params: string[] = [];
  params.push(`size=${opts.size || "640x300"}`);
  params.push("scale=2");
  if (opts.center) params.push(`center=${encodeURIComponent(opts.center)}`);
  if (opts.zoom) params.push(`zoom=${opts.zoom}`);
  (opts.markers || []).forEach(m => {
    const parts = [
      m.color ? `color:${encodeURIComponent(m.color)}` : "color:red",
      m.label ? `label:${encodeURIComponent(m.label)}` : "",
      `${m.lat},${m.lng}`,
    ].filter(Boolean);
    params.push(`markers=${parts.join("%7C")}`);
  });
  if (opts.polyline) {
    params.push(`path=color:0x008751BB%7Cweight:4%7Cenc:${encodeURIComponent(opts.polyline)}`);
  }
  params.push(`key=${key}`);
  return `https://maps.googleapis.com/maps/api/staticmap?${params.join("&")}`;
}
