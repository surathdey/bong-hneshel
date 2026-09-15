/**
 * Auth Context — Emergent Google Auth flow.
 * Handles: check existing session, sign in, sign out, session_id from redirect URL.
 */
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { api, setToken, clearToken, getToken } from "@/src/api";

export type CurrentUser = {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  phone?: string | null;
  loyalty_points: number;
  role: string;
  default_address?: any;
};

type AuthState = {
  user: CurrentUser | null;
  loading: boolean;
  signIn: () => Promise<void>;
  signInAsGuest: () => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  signIn: async () => {},
  signInAsGuest: async () => {},
  signOut: async () => {},
  refresh: async () => {},
});

async function exchangeSession(sessionToken: string) {
  const r = await api.post<{ session_token: string; user: CurrentUser }>("/auth/session", {
    session_token: sessionToken,
  });
  if (r.ok) {
    await setToken(r.data.session_token);
    return r.data.user;
  }
  return null;
}

function extractSessionIdFromUrl(url: string | null): string | null {
  if (!url) return null;
  // Emergent OAuth returns the id ONLY in the URL hash fragment (`#session_id=`).
  // Do NOT read from ?session_id= query — Stripe checkout uses that param too.
  const hashIdx = url.indexOf("#session_id=");
  if (hashIdx !== -1) return decodeURIComponent(url.slice(hashIdx + "#session_id=".length));
  return null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const r = await api.get<CurrentUser>("/auth/me");
    if (r.ok) setUser(r.data);
    else setUser(null);
  }, []);

  useEffect(() => {
    (async () => {
      // Web: check URL fragment for session_id
      if (Platform.OS === "web" && typeof window !== "undefined") {
        const sid = extractSessionIdFromUrl(window.location.href);
        if (sid) {
          const u = await exchangeSession(sid);
          if (u) setUser(u);
          try { window.history.replaceState(null, "", window.location.pathname); } catch {}
        }
      }
      // Try existing token
      const tok = await getToken();
      if (tok) {
        await refresh();
      }
      setLoading(false);
    })();
  }, [refresh]);

  const signIn = useCallback(async () => {
    const redirectUrl = Platform.OS === "web"
      ? (typeof window !== "undefined" ? window.location.origin + "/" : "")
      : Linking.createURL("");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;

    if (Platform.OS === "web") {
      if (typeof window !== "undefined") window.location.href = authUrl;
      return;
    }
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    if (result.type !== "success" || !result.url) return;
    const sid = extractSessionIdFromUrl(result.url);
    if (!sid) return;
    const u = await exchangeSession(sid);
    if (u) setUser(u);
  }, []);

  const signInAsGuest = useCallback(async () => {
    const r = await api.post<{ session_token: string; user: CurrentUser }>("/auth/guest");
    if (r.ok) {
      await setToken(r.data.session_token);
      setUser(r.data.user);
    }
  }, []);

  const signOut = useCallback(async () => {
    await api.post("/auth/logout");
    await clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signInAsGuest, signOut, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
