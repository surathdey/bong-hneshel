/**
 * Delivery Partner App (v3).
 * Tab 1: My Orders — assigned/active orders, mark status transitions
 * Tab 2: Route Planner — set start location, optimize via Google Directions, show map
 *
 * Auth is separate from the customer app (its own JWT stored in `curryco.delivery.token`).
 * Route: /delivery-partner  (accessible via web preview or Expo Go link).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, Platform, Linking, KeyboardAvoidingView, Image,
} from "react-native";
import { useRouter, Stack } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { deliveryApi, getDeliveryToken, setDeliveryToken, clearDeliveryToken, uploadDeliveryProof } from "@/src/deliveryApi";
import * as ImagePicker from "expo-image-picker";
import { mediaUrl } from "@/src/utils/backendUrl";
import { APP_VARIANT } from "./_layout";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { BRAND } from "@/src/brand";
import { centsToCAD } from "@/src/utils/format";
import { RouteMap } from "@/src/components/RouteMap";
import { AddressAutocomplete, StructuredAddress } from "@/src/components/AddressAutocomplete";
import * as Location from "expo-location";

type Partner = { partner_id: string; name: string; email: string; phone: string; vehicle: string; };
type Order = {
  order_id: string; status: string; delivery_status?: string; total_cents: number;
  address: any; phone: string; slot: any; items_snapshot: any[];
  customer_name?: string;
  delivery_route_order?: number; delivery_eta_seconds?: number;
  delivery_partner_lat?: number; delivery_partner_lng?: number;
  delivery_proof_photo_url?: string;
};

type RouteStop = {
  order_id: string; route_index: number;
  eta_seconds: number; duration_sec: number; distance_m: number;
  address: string; lat: number; lng: number;
};
type RouteResult = { ok: boolean; optimized: boolean; stops: RouteStop[]; total_duration_sec: number; polyline?: string | null; };

export default function DeliveryPartnerApp() {
  const router = useRouter();
  const [booting, setBooting] = useState(true);
  const [partner, setPartner] = useState<Partner | null>(null);

  useEffect(() => {
    (async () => {
      const tk = await getDeliveryToken();
      if (!tk) { setBooting(false); return; }
      const r = await deliveryApi.get<Partner>("/delivery/me");
      if (r.ok && r.data) setPartner(r.data);
      else await clearDeliveryToken();
      setBooting(false);
    })();
  }, []);

  const onLogin = (p: Partner) => setPartner(p);
  const onLogout = async () => { await clearDeliveryToken(); setPartner(null); };

  if (booting) {
    return (
      <View style={styles.center}><ActivityIndicator color={colors.primary} size="large" /></View>
    );
  }

  if (!partner) return <LoginScreen onLogin={onLogin} onExit={() => router.replace("/")} />;
  return <PartnerHome partner={partner} onLogout={onLogout} onExit={() => router.replace("/")} />;
}

// ================================================================
// LOGIN
// ================================================================
function LoginScreen({ onLogin, onExit }: { onLogin: (p: Partner) => void; onExit: () => void }) {
  // In dev we pre-fill test credentials for convenience; production release
  // builds ship with blank fields so no test data leaks in the app bundle.
  const [email, setEmail] = useState(__DEV__ ? "delivery@curryandco.local" : "");
  const [password, setPassword] = useState(__DEV__ ? "curry@delivery2026" : "");
  const [loading, setLoading] = useState(false);
  const isStandalone = APP_VARIANT === "delivery"; // hide "back to customer" nav when this IS the standalone delivery app

  const submit = async () => {
    if (!email || !password) { Alert.alert("Missing", "Enter email and password."); return; }
    setLoading(true);
    const r = await deliveryApi.post<{ access_token: string; partner: Partner }>("/delivery/login", { email, password });
    setLoading(false);
    if (!r.ok || !r.data) { Alert.alert("Login failed", r.error || "Invalid credentials"); return; }
    await setDeliveryToken(r.data.access_token);
    onLogin(r.data.partner);
  };

  return (
    <View style={styles.loginRoot}>
      <Stack.Screen options={{ headerShown: false }} />
      {!isStandalone && (
        <SafeAreaView edges={["top"]} style={{ padding: spacing.lg }}>
          <TouchableOpacity onPress={onExit} style={styles.backBtn}><Ionicons name="chevron-back" size={22} color={colors.text} /></TouchableOpacity>
        </SafeAreaView>
      )}
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[styles.loginBody, isStandalone && { paddingTop: 80 }]}>
          <View style={styles.loginIcon}><Ionicons name="bicycle" size={30} color="#fff" /></View>
          <Text style={styles.loginTitle}>{`${BRAND.name} — Delivery`}</Text>
          <Text style={styles.loginSub}>Sign in with the credentials your admin gave you.</Text>

          <View style={{ gap: spacing.sm, marginTop: spacing.xl }}>
            <Text style={styles.label}>Email</Text>
            <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" style={styles.input} testID="dp-email" />
            <Text style={styles.label}>Password</Text>
            <TextInput value={password} onChangeText={setPassword} secureTextEntry style={styles.input} testID="dp-password" />
            <TouchableOpacity testID="dp-login" style={[styles.primaryBtn, loading && { opacity: 0.6 }]} disabled={loading} onPress={submit}>
              {loading ? <ActivityIndicator color="#fff" /> : (
                <>
                  <Ionicons name="log-in-outline" size={16} color="#fff" />
                  <Text style={styles.primaryBtnText}>Sign in</Text>
                </>
              )}
            </TouchableOpacity>
            <Text style={styles.helperText}>{"Demo credentials pre-filled — press Sign in."}</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

// ================================================================
// HOME (Orders + Route Planner tabs)
// ================================================================
type Tab = "orders" | "route";

function PartnerHome({ partner, onLogout, onExit }: { partner: Partner; onLogout: () => void; onExit: () => void; }) {
  const insets = useSafeAreaInsets();
  const isStandalone = APP_VARIANT === "delivery";
  const [tab, setTab] = useState<Tab>("orders");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const r = await deliveryApi.get<Order[]>("/delivery/orders?status=active");
    if (r.ok) setOrders(r.data || []);
    setLoading(false);
  }, []);

  useEffect(() => { load(); const iv = setInterval(load, 15000); return () => clearInterval(iv); }, [load]);

  const updateStatus = async (order_id: string, status: string) => {
    const r = await deliveryApi.post(`/delivery/orders/${order_id}/status`, { status });
    if (!r.ok) { Alert.alert("Update failed", r.error || ""); return; }
    await load();
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView edges={["top"]} style={styles.hdr}>
        {!isStandalone && (
          <TouchableOpacity onPress={onExit} style={styles.backBtn} testID="dp-back-home">
            <Ionicons name="chevron-back" size={20} color={colors.text} />
          </TouchableOpacity>
        )}
        <View style={styles.avatarSm}><Text style={styles.avatarText}>{partner.name.slice(0, 1)}</Text></View>
        <View style={{ flex: 1 }}>
          <Text style={styles.hdrEyebrow}>DELIVERY</Text>
          <Text style={styles.hdrTitle} numberOfLines={1}>{partner.name}</Text>
        </View>
        <TouchableOpacity onPress={onLogout} style={styles.iconBtn} testID="dp-logout">
          <Ionicons name="log-out-outline" size={18} color={colors.text} />
        </TouchableOpacity>
      </SafeAreaView>

      <View style={styles.tabRow}>
        <TouchableOpacity testID="dp-tab-orders" onPress={() => setTab("orders")} style={[styles.tab, tab === "orders" && styles.tabActive]}>
          <Ionicons name="cube-outline" size={14} color={tab === "orders" ? "#fff" : colors.text} />
          <Text style={[styles.tabText, tab === "orders" && styles.tabTextActive]}>My orders ({orders.length})</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="dp-tab-route" onPress={() => setTab("route")} style={[styles.tab, tab === "route" && styles.tabActive]}>
          <Ionicons name="map-outline" size={14} color={tab === "route" ? "#fff" : colors.text} />
          <Text style={[styles.tabText, tab === "route" && styles.tabTextActive]}>Route planner</Text>
        </TouchableOpacity>
      </View>

      {loading ? <ActivityIndicator color={colors.primary} style={{ marginTop: 40 }} /> : (
        tab === "orders" ? (
          <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 + insets.bottom, gap: spacing.md }}>
            {orders.map(o => <OrderCard key={o.order_id} o={o} onStatus={updateStatus} />)}
            {orders.length === 0 && (
              <View style={styles.emptyCard}>
                <Ionicons name="checkmark-done-circle-outline" size={40} color={colors.textMuted} />
                <Text style={styles.empty}>{"You're all caught up — no active deliveries."}</Text>
                <Text style={[styles.empty, { fontSize: 11 }]}>{"New assignments from admin will appear here within 15 seconds."}</Text>
              </View>
            )}
          </ScrollView>
        ) : (
          <RoutePlanner orders={orders} onStatus={updateStatus} onRefresh={load} />
        )
      )}
    </View>
  );
}

// ================================================================
// ORDER CARD
// ================================================================
function OrderCard({ o, onStatus }: { o: Order; onStatus: (id: string, status: string) => void }) {
  const [proofUri, setProofUri] = useState<string>(o.delivery_proof_photo_url || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const flow: Record<string, { next?: string; label: string; icon: any }> = {
    assigned:    { next: "picked_up",  label: "Mark picked up", icon: "cube-outline" },
    picked_up:   { next: "on_the_way", label: "Start delivery", icon: "car-sport-outline" },
    on_the_way:  { next: "arrived",    label: "I've arrived",    icon: "location-outline" },
    arrived:     { next: "delivered",  label: "Complete delivery", icon: "checkmark-circle" },
    delivered:   { label: "Delivered", icon: "checkmark-done-circle" },
  };
  const st = flow[o.delivery_status || "assigned"] || { label: "—", icon: "help" };
  const addr = o.address || {};
  const addrLine = `${addr.line1 || ""}${addr.line2 ? ", " + addr.line2 : ""}, ${addr.city || ""} ${addr.postal_code || ""}`;
  const openMaps = () => {
    const q = encodeURIComponent(addrLine);
    const url = Platform.OS === "ios" ? `http://maps.apple.com/?q=${q}` : `https://www.google.com/maps/search/?api=1&query=${q}`;
    Linking.openURL(url);
  };
  const callCustomer = () => Linking.openURL(`tel:${(o.phone || "").replace(/\s+/g, "")}`);

  // Capture a proof photo (camera first, gallery fallback), upload, then mark delivered.
  const captureAndComplete = async () => {
    setErr("");
    try {
      let uri = "";
      // Try camera with a contextual permission request.
      const cam = await ImagePicker.requestCameraPermissionsAsync();
      if (cam.granted) {
        const res = await ImagePicker.launchCameraAsync({ quality: 0.6, allowsEditing: false });
        if (res.canceled) return;
        uri = res.assets?.[0]?.uri || "";
      } else {
        // Fall back to the photo library (also used on web where camera is unavailable).
        const lib = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!lib.granted) {
          setErr("Photo permission needed to complete delivery.");
          return;
        }
        const res = await ImagePicker.launchImageLibraryAsync({ quality: 0.6, mediaTypes: ["images"] });
        if (res.canceled) return;
        uri = res.assets?.[0]?.uri || "";
      }
      if (!uri) return;
      setBusy(true);
      const up = await uploadDeliveryProof(o.order_id, uri);
      if (!up.ok) { setErr(up.error || "Upload failed"); setBusy(false); return; }
      setProofUri(up.data!.delivery_proof_photo_url);
      onStatus(o.order_id, "delivered");
    } catch (e: any) {
      setErr(e?.message || "Could not complete delivery");
    } finally {
      setBusy(false);
    }
  };

  const onPrimary = () => {
    if (st.next === "delivered") captureAndComplete();
    else if (st.next) onStatus(o.order_id, st.next);
  };

  return (
    <View style={styles.oCard} testID={`dp-order-${o.order_id}`}>
      <View style={styles.oHead}>
        <View style={{ flex: 1 }}>
          <Text style={styles.oId}>{o.order_id.slice(0, 12)}</Text>
          <Text style={styles.oTime}>{o.slot?.window || "Any time"}</Text>
        </View>
        <View style={[styles.oStatus, { backgroundColor: statusColor(o.delivery_status || "assigned") }]}>
          <Text style={styles.oStatusText}>{(o.delivery_status || "assigned").replace(/_/g, " ").toUpperCase()}</Text>
        </View>
      </View>
      <View style={styles.oBody}>
        <View style={{ flex: 1, gap: 3 }}>
          <Text style={styles.oCust}>{o.customer_name || addr.name || "Customer"}</Text>
          <Text style={styles.oAddr}>{addrLine}</Text>
          <Text style={styles.oItems}>{o.items_snapshot?.length || 0} items · {centsToCAD(o.total_cents)}</Text>
        </View>
      </View>

      {!!proofUri && (
        <View style={styles.proofRow} testID={`dp-proof-${o.order_id}`}>
          <Image source={{ uri: proofUri.startsWith("http") || proofUri.startsWith("file") || proofUri.startsWith("blob") ? proofUri : mediaUrl(proofUri) }} style={styles.proofImg} />
          <View style={{ flex: 1 }}>
            <Text style={styles.proofLabel}>Proof photo uploaded</Text>
            <Text style={styles.proofSub}>Shared with the restaurant.</Text>
          </View>
          <Ionicons name="checkmark-circle" size={20} color={colors.success} />
        </View>
      )}
      {!!err && <Text style={styles.proofErr} testID={`dp-proof-err-${o.order_id}`}>{err}</Text>}

      <View style={styles.oActions}>
        {o.phone ? (
          <TouchableOpacity style={styles.miniBtn} onPress={callCustomer} testID={`dp-call-${o.order_id}`}>
            <Ionicons name="call-outline" size={13} color={colors.text} />
            <Text style={styles.miniBtnText}>Call</Text>
          </TouchableOpacity>
        ) : null}
        <TouchableOpacity style={styles.miniBtn} onPress={openMaps} testID={`dp-navigate-${o.order_id}`}>
          <Ionicons name="navigate-outline" size={13} color={colors.text} />
          <Text style={styles.miniBtnText}>Navigate</Text>
        </TouchableOpacity>
        {st.next && (
          <TouchableOpacity
            testID={`dp-next-${o.order_id}`}
            onPress={onPrimary}
            disabled={busy}
            style={styles.nextBtn}
          >
            {busy ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name={st.next === "delivered" ? "camera" : st.icon} size={14} color="#fff" />}
            <Text style={styles.nextBtnText}>{st.next === "delivered" ? "Photo & complete" : st.label}</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

// ================================================================
// ROUTE PLANNER
// ================================================================
function RoutePlanner({ orders, onStatus, onRefresh }: { orders: Order[]; onStatus: (id: string, s: string) => void; onRefresh: () => void }) {
  const insets = useSafeAreaInsets();
  const [address, setAddress] = useState("");                 // free-form address the partner types
  const [resolvedAddress, setResolvedAddress] = useState(""); // Google's canonical formatted address (for confirmation)
  const [originLat, setOriginLat] = useState<number | null>(null);
  const [originLng, setOriginLng] = useState<number | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const [geocoding, setGeocoding] = useState(false);
  const [journeyActive, setJourneyActive] = useState(false);
  const [journeyStartedAt, setJourneyStartedAt] = useState<Date | null>(null);
  const [startingJourney, setStartingJourney] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const locTimer = useRef<any>(null);  // legacy — no longer wired; see live-GPS effect below

  const isCoordSet = originLat != null && originLng != null;

  // On mount: fetch persisted journey. If active, restore stops + origin + map + banner state.
  useEffect(() => {
    (async () => {
      const r = await deliveryApi.get<{ active: boolean; journey: any }>("/delivery/journey/current");
      if (r.ok && r.data?.active && r.data.journey) {
        const j = r.data.journey;
        if (j.origin_lat != null && j.origin_lng != null) {
          setOriginLat(j.origin_lat);
          setOriginLng(j.origin_lng);
          const addr = j.origin_address || `${j.origin_lat.toFixed(5)}, ${j.origin_lng.toFixed(5)}`;
          setAddress(addr);
          setResolvedAddress(addr);
        }
        if (Array.isArray(j.stops) && j.stops.length > 0) {
          setRoute({
            ok: true, optimized: !!j.optimized, stops: j.stops,
            total_duration_sec: j.total_duration_sec || 0, polyline: j.polyline || null,
          });
        }
        if (j.started_at) setJourneyStartedAt(new Date(j.started_at));
        setJourneyActive(true);
      }
      setRestoring(false);
    })();
  }, []);

  // Cross-platform alert helper (Alert.alert is a no-op on react-native-web).
  const notify = (title: string, msg?: string) => {
    if (Platform.OS === "web") window.alert(msg ? `${title}\n\n${msg}` : title);
    else Alert.alert(title, msg);
  };

  const geocode = async (text: string): Promise<{ lat: number; lng: number } | null> => {
    if (!text.trim()) { notify("Missing", "Enter a start address."); return null; }
    setGeocoding(true);
    const r = await deliveryApi.post<{ lat: number; lng: number; formatted: string }>("/delivery/geocode", { address: text });
    setGeocoding(false);
    if (!r.ok || !r.data) {
      notify("Could not find address", r.error || "Try being more specific (include city / postal code).");
      return null;
    }
    setOriginLat(r.data.lat);
    setOriginLng(r.data.lng);
    setResolvedAddress(r.data.formatted);
    setAddress(r.data.formatted);
    return { lat: r.data.lat, lng: r.data.lng };
  };

  const useCurrent = async () => {
    try {
      setLocating(true);
      // Check existing permission first, then request contextually if needed.
      let perm = await Location.getForegroundPermissionsAsync();
      if (perm.status !== "granted") {
        perm = await Location.requestForegroundPermissionsAsync();
      }
      if (perm.status !== "granted") {
        setLocating(false);
        if (!perm.canAskAgain) {
          Alert.alert(
            "Location permission needed",
            "To use your current location, enable Location access for this app in Settings.",
            [
              { text: "Not now", style: "cancel" },
              { text: "Open Settings", onPress: () => Linking.openSettings() },
            ],
          );
        } else {
          notify("Location permission needed", "Please allow location access, or type the start address instead.");
        }
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const { latitude, longitude } = pos.coords;
      setOriginLat(latitude);
      setOriginLng(longitude);
      const r = await deliveryApi.post<{ formatted: string }>("/delivery/reverse-geocode", { lat: latitude, lng: longitude });
      if (r.ok && r.data?.formatted) {
        setAddress(r.data.formatted);
        setResolvedAddress(r.data.formatted);
      } else {
        const s = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
        setAddress(s);
        setResolvedAddress(s);
      }
      setLocating(false);
    } catch (e: any) {
      setLocating(false);
      notify("Location error", e?.message || "Could not get your location. Please type the address instead.");
    }
  };

  const runRoute = async (lat: number, lng: number, opts: { order_ids?: string[]; optimize?: boolean } = {}) => {
    const orderIds = opts.order_ids ?? orders.map(o => o.order_id);
    if (orderIds.length === 0) { notify("Nothing to route", "You have no active orders."); return; }
    const isReorder = opts.optimize === false;
    if (isReorder) setReordering(true); else setLoading(true);
    const r = await deliveryApi.post<RouteResult>("/delivery/route", {
      origin_lat: lat, origin_lng: lng,
      order_ids: orderIds,
      optimize: opts.optimize !== undefined ? opts.optimize : true,
    });
    if (isReorder) setReordering(false); else setLoading(false);
    if (!r.ok || !r.data) { notify("Route failed", r.error || ""); return; }
    setRoute(r.data);
    deliveryApi.post("/delivery/location", { lat, lng });
  };

  const optimize = async () => {
    // If the address is dirty or coords are unset, geocode first — synchronously chain into optimize.
    if (!isCoordSet || address.trim() !== resolvedAddress.trim()) {
      const coords = await geocode(address);
      if (!coords) return;
      await runRoute(coords.lat, coords.lng);
      return;
    }
    await runRoute(originLat!, originLng!);
  };

  // Move stop up or down (index i by delta ±1). Preserves current stops list order except for the swap.
  const moveStop = async (i: number, delta: -1 | 1) => {
    if (!route) return;
    const j = i + delta;
    if (j < 0 || j >= route.stops.length) return;
    const newStops = [...route.stops];
    [newStops[i], newStops[j]] = [newStops[j], newStops[i]];
    // Optimistic UI: swap positions immediately + clear polyline until recompute.
    setRoute({ ...route, stops: newStops, polyline: null });
    if (isCoordSet) {
      await runRoute(originLat!, originLng!, {
        order_ids: newStops.map(s => s.order_id),
        optimize: false,
      });
    }
  };

  const startJourney = async () => {
    if (!route || !isCoordSet) return;
    setStartingJourney(true);
    const r = await deliveryApi.post<{ ok: boolean; flipped: number; journey_started_at: string }>("/delivery/journey/start", {
      order_ids: route.stops.map(s => s.order_id),
      origin_lat: originLat, origin_lng: originLng,
      origin_address: resolvedAddress,
      stops: route.stops,
      polyline: route.polyline || null,
      total_duration_sec: route.total_duration_sec,
      optimized: route.optimized,
    });
    setStartingJourney(false);
    if (!r.ok || !r.data) { notify("Could not start journey", r.error || ""); return; }
    setJourneyActive(true);
    setJourneyStartedAt(new Date(r.data.journey_started_at));
    notify("Journey started", `Customers of ${r.data.flipped} order(s) can now see live ETA.`);
    onRefresh();
  };

  const endJourney = async () => {
    await deliveryApi.post("/delivery/journey/end", {});
    setJourneyActive(false);
    setJourneyStartedAt(null);
    onRefresh();
  };

  // Tap a stop tile → open Google Maps with driving directions.
  //   Stop 1  → from Start location to A
  //   Stop 2+ → from the previous stop to this one (A→B, B→C, …)
  const openStopNav = (s: RouteStop, index: number) => {
    const prev = index > 0 && route ? route.stops[index - 1] : null;
    const oLat = prev ? prev.lat : originLat;
    const oLng = prev ? prev.lng : originLng;
    const params = new URLSearchParams({
      api: "1",
      destination: `${s.lat},${s.lng}`,
      travelmode: "driving",
    });
    if (oLat != null && oLng != null) params.set("origin", `${oLat},${oLng}`);
    const url = `https://www.google.com/maps/dir/?${params.toString()}`;
    Linking.openURL(url).catch(() => notify("Could not open Google Maps"));
  };

  // -----------------------------------------------------------------
  // LIVE GPS BROADCAST (Uber-style).
  //
  // While a journey is active, stream the driver's REAL phone GPS to the
  // backend so the customer's tracking screen sees the driver actually move
  // on the map. When no journey is running we fall back to sending the
  // typed origin every 30s (used for ETA quotes on new orders).
  //
  // Native (iOS/Android): expo-location `watchPositionAsync` with a 10-metre
  //   distance filter — cheap on battery, high responsiveness.
  // Web (delivery-partner preview): `navigator.geolocation.watchPosition`.
  // Both fall back gracefully to a plain timer if permissions are denied.
  // -----------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    let nativeSub: Location.LocationSubscription | null = null;
    let webWatchId: number | null = null;
    let idleTimer: any = null;

    const postLocation = (lat: number, lng: number) => {
      if (cancelled) return;
      deliveryApi.post("/delivery/location", { lat, lng });
    };

    const startForegroundWatch = async () => {
      // Only stream real GPS while a journey is active.
      if (!journeyActive) {
        // Non-active fallback: 30s ping of the typed origin so admins can see
        // the driver's "last known" pin before the trip starts.
        idleTimer = setInterval(() => {
          if (isCoordSet && originLat != null && originLng != null) {
            postLocation(originLat, originLng);
          }
        }, 30000);
        return;
      }

      if (Platform.OS === "web") {
        if (typeof navigator === "undefined" || !navigator.geolocation) return;
        webWatchId = navigator.geolocation.watchPosition(
          pos => postLocation(pos.coords.latitude, pos.coords.longitude),
          _err => { /* ignore transient errors — retry on next fix */ },
          { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
        );
        return;
      }

      // Native path — request foreground permission, then watch.
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== "granted") {
          Alert.alert(
            "Location permission required",
            "Enable location so customers can see your live position on the map. You can change this in Settings.",
          );
          return;
        }
        if (cancelled) return;
        nativeSub = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.High,
            distanceInterval: 10,   // send an update every 10 metres of movement
            timeInterval: 8000,     // …and at least every 8s if we're stationary
          },
          loc => postLocation(loc.coords.latitude, loc.coords.longitude),
        );
      } catch (e) {
        // Don't surface — just skip live GPS this session.
        // eslint-disable-next-line no-console
        console.warn("watchPositionAsync failed:", e);
      }
    };

    startForegroundWatch();

    return () => {
      cancelled = true;
      if (idleTimer) clearInterval(idleTimer);
      if (nativeSub) nativeSub.remove();
      if (webWatchId != null && typeof navigator !== "undefined" && navigator.geolocation) {
        navigator.geolocation.clearWatch(webWatchId);
      }
    };
  }, [journeyActive, isCoordSet, originLat, originLng]);

  const totalMin = route ? Math.round(route.total_duration_sec / 60) : 0;
  const journeyElapsedMin = journeyStartedAt ? Math.floor((Date.now() - journeyStartedAt.getTime()) / 60000) : 0;
  // Auto-end journey when every stop is delivered
  useEffect(() => {
    if (journeyActive && route && route.stops.length > 0) {
      const allDone = route.stops.every(s => {
        const o = orders.find(x => x.order_id === s.order_id);
        return !o || o.delivery_status === "delivered";
      });
      if (allDone) endJourney();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orders, journeyActive]);

  if (restoring) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: 8 }}>
        <ActivityIndicator color={colors.primary} />
        <Text style={styles.hint}>Loading your route…</Text>
      </View>
    );
  }

  const onOriginPicked = (addr: StructuredAddress) => {
    // Places details already returns lat/lng — skip the extra /geocode call entirely.
    if (addr.lat != null && addr.lng != null) {
      setOriginLat(addr.lat);
      setOriginLng(addr.lng);
      const formatted = addr.formatted || [addr.line1, addr.city, addr.province, addr.postal_code].filter(Boolean).join(", ");
      setAddress(formatted);
      setResolvedAddress(formatted);
    } else {
      // Fall back to geocoding via backend if for some reason lat/lng missing.
      const formatted = addr.formatted || `${addr.line1}, ${addr.city}, ${addr.province}`;
      setAddress(formatted);
      geocode(formatted);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 + insets.bottom, gap: spacing.md }} keyboardShouldPersistTaps="handled">
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Start location</Text>
        <Text style={styles.hint}>{"Type your restaurant / start address — pick a suggestion for the fastest setup."}</Text>
        <AddressAutocomplete
          testID="dp-origin-address"
          value={address}
          onChangeText={t => { setAddress(t); if (resolvedAddress && t.trim() !== resolvedAddress.trim()) { setOriginLat(null); setOriginLng(null); } }}
          onSelect={onOriginPicked}
          placeholder="Start typing an address (Canada)…"
        />
        {geocoding && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <ActivityIndicator size="small" color={colors.textMuted} />
            <Text style={styles.hint}>Finding that address…</Text>
          </View>
        )}
        {isCoordSet && !geocoding && (
          <View style={styles.confirmedRow} testID="dp-origin-confirmed">
            <Ionicons name="checkmark-circle" size={14} color={colors.success} />
            <Text style={styles.confirmedText} numberOfLines={2}>{resolvedAddress}</Text>
          </View>
        )}
        <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
          <TouchableOpacity onPress={useCurrent} style={[styles.ghostBtn, { flex: 1 }]} testID="dp-use-current" disabled={locating || journeyActive}>
            {locating ? <ActivityIndicator color={colors.text} /> : (
              <>
                <Ionicons name="locate" size={14} color={colors.text} />
                <Text style={styles.ghostBtnText}>Use my location</Text>
              </>
            )}
          </TouchableOpacity>
          <TouchableOpacity
            onPress={optimize}
            style={[styles.primaryBtn, { flex: 1 }, (loading || geocoding || journeyActive) && { opacity: 0.6 }]}
            disabled={loading || geocoding || journeyActive}
            testID="dp-optimize"
          >
            {loading ? <ActivityIndicator color="#fff" /> : (
              <>
                <Ionicons name="git-network-outline" size={14} color="#fff" />
                <Text style={styles.primaryBtnText}>Optimize route</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {route && isCoordSet && (
        <>
          <View style={styles.card}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>Optimized route</Text>
                <Text style={styles.hint}>
                  {route.optimized ? "Google-optimized order" : "Manual order (drag ↑↓ to adjust)"} · Total {totalMin} min · {route.stops.length} stops
                </Text>
              </View>
              {reordering && <ActivityIndicator size="small" color={colors.primary} />}
            </View>
            <RouteMap
              origin={{ lat: originLat!, lng: originLng! }}
              stops={route.stops.map((s, i) => ({
                lat: s.lat, lng: s.lng,
                label: String.fromCharCode(65 + i),
                title: `Stop ${i + 1} · ${s.address}`,
              }))}
              polyline={route.polyline}
              height={280}
            />
          </View>

          {/* START / END DELIVERY BAR */}
          <View style={[styles.card, journeyActive && styles.journeyActiveCard]}>
            {!journeyActive ? (
              <>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Ionicons name="flag-outline" size={16} color={colors.text} />
                  <Text style={styles.cardTitle}>Ready to go?</Text>
                </View>
                <Text style={styles.hint}>{"Starting the journey will mark all orders as \"on the way\" and share live ETA with customers."}</Text>
                <TouchableOpacity
                  onPress={startJourney}
                  disabled={startingJourney}
                  style={[styles.startDeliveryBtn, startingJourney && { opacity: 0.6 }]}
                  testID="dp-start-delivery"
                >
                  {startingJourney ? <ActivityIndicator color="#fff" /> : (
                    <>
                      <Ionicons name="rocket" size={16} color="#fff" />
                      <Text style={styles.startDeliveryText}>START DELIVERY</Text>
                    </>
                  )}
                </TouchableOpacity>
              </>
            ) : (
              <>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <View style={styles.livePulse}><View style={styles.livePulseInner} /></View>
                  <Text style={styles.cardTitle}>Journey in progress</Text>
                </View>
                <Text style={styles.hint}>
                  Started {journeyElapsedMin} min ago · Customers now see live ETA · Location broadcasting every 10s.
                </Text>
                <TouchableOpacity onPress={endJourney} style={styles.endDeliveryBtn} testID="dp-end-delivery">
                  <Ionicons name="stop-circle-outline" size={16} color={colors.text} />
                  <Text style={styles.endDeliveryText}>End journey</Text>
                </TouchableOpacity>
              </>
            )}
          </View>

          {route.stops.map((s, i) => {
            const o = orders.find(x => x.order_id === s.order_id);
            // A delivered stop either has delivery_status=="delivered" OR has been
            // filtered out of the active `orders` list by GET /delivery/orders?status=active
            // (see line ~459 which uses the same pattern to detect journey completion).
            const isDelivered = !o || o.delivery_status === "delivered";
            const canMoveUp = i > 0 && !journeyActive;
            const canMoveDown = i < route.stops.length - 1 && !journeyActive;
            const customerName = (o?.customer_name || o?.address?.name || "").trim();
            // Per-leg ETA: Stop 1 = Start→A, Stop 2 = A→B, Stop 3 = B→C, …
            // Backend already returns `duration_sec` on each stop (the individual leg time).
            const legMin = Math.max(1, Math.round((s.duration_sec || 0) / 60));
            const fromLabel = i === 0 ? "Start" : String.fromCharCode(65 + i - 1);
            const toLabel = String.fromCharCode(65 + i);
            return (
              <TouchableOpacity
                key={s.order_id}
                activeOpacity={0.85}
                onPress={() => openStopNav(s, i)}
                style={[styles.stopCard, isDelivered && styles.stopCardDelivered]}
                testID={`dp-stop-${s.order_id}`}
              >
                <View style={[styles.stopIndex, isDelivered && styles.stopIndexDelivered]}>
                  {isDelivered ? (
                    <Ionicons name="checkmark" size={16} color="#fff" />
                  ) : (
                    <Text style={styles.stopIndexText}>{toLabel}</Text>
                  )}
                </View>

                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <Text style={styles.stopTitle}>Stop {i + 1}</Text>
                    <Text style={styles.legEta}>{fromLabel} → {toLabel} · {legMin} min</Text>
                    <Ionicons name="open-outline" size={12} color={colors.textMuted} />
                  </View>
                  {customerName ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 }}>
                      <Ionicons name="person-circle-outline" size={12} color={colors.primary} />
                      <Text style={styles.stopCustomer} numberOfLines={1}>{customerName}</Text>
                    </View>
                  ) : null}
                  <Text style={styles.stopAddr} numberOfLines={2}>{s.address}</Text>
                  <Text style={styles.hint}>
                    {(s.distance_m / 1000).toFixed(1)} km · Total {Math.round((s.eta_seconds || 0) / 60)} min from start · Order {s.order_id.slice(0, 8)} · {o ? centsToCAD(o.total_cents) : ""}
                  </Text>
                </View>

                {/* Reorder controls */}
                <View style={{ gap: 4, alignItems: "center" }}>
                  <TouchableOpacity
                    onPress={(e) => { e.stopPropagation?.(); moveStop(i, -1); }}
                    disabled={!canMoveUp || reordering}
                    style={[styles.arrowBtn, (!canMoveUp || reordering) && { opacity: 0.3 }]}
                    testID={`dp-stop-up-${s.order_id}`}
                    hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                  >
                    <Ionicons name="chevron-up" size={14} color={colors.text} />
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={(e) => { e.stopPropagation?.(); moveStop(i, 1); }}
                    disabled={!canMoveDown || reordering}
                    style={[styles.arrowBtn, (!canMoveDown || reordering) && { opacity: 0.3 }]}
                    testID={`dp-stop-down-${s.order_id}`}
                    hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                  >
                    <Ionicons name="chevron-down" size={14} color={colors.text} />
                  </TouchableOpacity>
                </View>

                {o && o.delivery_status !== "delivered" && (
                  <TouchableOpacity
                    style={styles.miniBtn}
                    onPress={(e) => { e.stopPropagation?.(); onStatus(s.order_id, "delivered"); }}
                    testID={`dp-complete-${s.order_id}`}
                  >
                    <Ionicons name="checkmark" size={14} color={colors.text} />
                    <Text style={styles.miniBtnText}>Done</Text>
                  </TouchableOpacity>
                )}
              </TouchableOpacity>
            );
          })}
        </>
      )}
    </ScrollView>
  );
}

function statusColor(s: string): string {
  switch (s) {
    case "assigned":   return "#DBEAFE";
    case "picked_up":  return "#FEF3C7";
    case "on_the_way": return "#FFEDD5";
    case "arrived":    return "#FCE7F3";
    case "delivered":  return "#DCFCE7";
    default: return "#E5E7EB";
  }
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },

  // login
  loginRoot: { flex: 1, backgroundColor: colors.background },
  loginBody: { padding: spacing.xl, gap: spacing.md },
  loginIcon: { width: 60, height: 60, borderRadius: 30, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  loginTitle: { fontSize: 24, fontWeight: "800", color: colors.text, letterSpacing: -0.3 },
  loginSub: { color: colors.textMuted, fontSize: 13 },

  // header
  hdr: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border },
  backBtn: { width: 40, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceAlt },
  avatarSm: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  avatarText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  hdrEyebrow: { fontSize: 10, letterSpacing: 3, fontWeight: "800", color: colors.primary },
  hdrTitle: { fontSize: 15, fontWeight: "800", color: colors.text, marginTop: 2 },
  iconBtn: { width: 36, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },

  // tabs
  tabRow: { flexDirection: "row", gap: 6, padding: spacing.md, backgroundColor: colors.background },
  tab: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  tabActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  tabText: { color: colors.text, fontSize: 13, fontWeight: "700" },
  tabTextActive: { color: "#fff" },

  // order card
  oCard: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm, ...shadows.soft },
  oHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  oId: { fontSize: 12, fontWeight: "800", color: colors.text },
  oTime: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  oStatus: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },
  oStatusText: { fontSize: 10, fontWeight: "900", letterSpacing: 1, color: "#1a1a1a" },
  oBody: { flexDirection: "row", gap: spacing.sm },
  oCust: { fontSize: 14, fontWeight: "800", color: colors.text },
  oAddr: { fontSize: 12, color: colors.text },
  oItems: { fontSize: 11, color: colors.textMuted },
  oActions: { flexDirection: "row", gap: 6, marginTop: 4 },
  miniBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 7, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  miniBtnText: { fontSize: 12, fontWeight: "700", color: colors.text },
  nextBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.primary, marginLeft: "auto" },
  nextBtnText: { fontSize: 12, fontWeight: "800", color: "#fff" },
  proofRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.sm, backgroundColor: colors.surfaceAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  proofImg: { width: 46, height: 46, borderRadius: radius.sm, backgroundColor: colors.border },
  proofLabel: { fontSize: 13, fontWeight: "700", color: colors.text },
  proofSub: { fontSize: 11, color: colors.textMuted },
  proofErr: { fontSize: 12, color: colors.danger, fontWeight: "600" },

  // route
  card: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm, ...shadows.soft },
  cardTitle: { fontSize: 14, fontWeight: "800", color: colors.text },
  stopCard: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, ...shadows.soft },
  stopCardDelivered: { backgroundColor: "#F0FDF4", borderColor: colors.success },
  stopIndex: { width: 30, height: 30, borderRadius: 15, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  stopIndexDelivered: { backgroundColor: colors.success },
  stopIndexText: { color: "#fff", fontWeight: "800" },
  stopTitle: { fontSize: 13, fontWeight: "800", color: colors.text },
  legEta: {
    fontSize: 11, fontWeight: "800", color: colors.primary,
    backgroundColor: colors.primary + "18",
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, letterSpacing: 0.2,
  },
  stopCustomer: { fontSize: 12, fontWeight: "700", color: colors.primary },
  stopAddr: { fontSize: 12, color: colors.text, marginTop: 2 },

  // shared inputs
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14 },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.primary, paddingVertical: 12, borderRadius: radius.pill, ...shadows.soft },
  primaryBtnText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  ghostBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  ghostBtnText: { color: colors.text, fontWeight: "700", fontSize: 13 },

  helperText: { color: colors.textMuted, fontSize: 11, fontStyle: "italic" },
  hint: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  confirmedRow: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#DCFCE7", paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.md, borderWidth: 1, borderColor: "#86EFAC" },
  confirmedText: { color: "#166534", fontSize: 12, fontWeight: "700", flex: 1 },
  emptyCard: { alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: 8, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  empty: { color: colors.textMuted, textAlign: "center", fontSize: 13 },

  // journey / start delivery
  journeyActiveCard: { borderColor: colors.success, backgroundColor: "#F0FDF4" },
  startDeliveryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    backgroundColor: colors.success, paddingVertical: 14, borderRadius: radius.pill,
    marginTop: 4, ...shadows.soft,
  },
  startDeliveryText: { color: "#fff", fontWeight: "900", fontSize: 14, letterSpacing: 1 },
  endDeliveryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    paddingVertical: 10, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginTop: 4,
  },
  endDeliveryText: { color: colors.text, fontWeight: "700", fontSize: 13 },
  livePulse: {
    width: 14, height: 14, borderRadius: 7,
    backgroundColor: "rgba(0,166,81,0.25)", alignItems: "center", justifyContent: "center",
  },
  livePulseInner: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },
  arrowBtn: {
    width: 26, height: 22, borderRadius: 6,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceAlt,
  },
});
