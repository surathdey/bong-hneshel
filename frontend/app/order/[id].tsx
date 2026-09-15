import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Image, TouchableOpacity, ActivityIndicator, RefreshControl,
  Platform, Vibration,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { api } from "@/src/api";
import { mediaUrl } from "@/src/utils/backendUrl";
import { RouteMap } from "@/src/components/RouteMap";
import { LiveTrackingMap } from "@/src/components/LiveTrackingMap";
import { expandComboPicks } from "@/src/utils/comboExpand";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD } from "@/src/utils/format";

// Great-circle distance in metres — used for the client-side ETA countdown
// (between server polls) and for the "driver is arriving" alert trigger.
function haversineMeters(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const φ1 = toRad(a.lat), φ2 = toRad(b.lat);
  const dφ = toRad(b.lat - a.lat);
  const dλ = toRad(b.lng - a.lng);
  const s = Math.sin(dφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(dλ / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)));
}

// Tiny helper: play a soft chime on web via Web Audio (no asset needed).
// On native we fall back to a triple haptic pulse (heavy → medium → light) so
// the alert is felt even if the phone is on silent.
function playArrivalCue() {
  if (Platform.OS === "web") {
    try {
      // @ts-ignore — RN types don't know about AudioContext
      const Ctx = (typeof window !== "undefined" && (window.AudioContext || (window as any).webkitAudioContext));
      if (!Ctx) return;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.type = "sine";
      // Two-tone chime C6 → E6
      osc.frequency.setValueAtTime(1046.5, ctx.currentTime);
      osc.frequency.setValueAtTime(1318.5, ctx.currentTime + 0.18);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.55);
      osc.start();
      osc.stop(ctx.currentTime + 0.6);
    } catch { /* swallow — audio is best-effort */ }
    return;
  }
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {});
  setTimeout(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}), 180);
  setTimeout(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {}), 360);
  try { Vibration.vibrate([0, 220, 120, 220]); } catch { /* ignore */ }
}

type Order = any;

const CARD_STATUS_STEPS: { key: string; label: string; icon: any }[] = [
  { key: "new", label: "Order placed", icon: "receipt-outline" },
  { key: "paid", label: "Payment confirmed", icon: "checkmark-circle-outline" },
  { key: "preparing", label: "Kitchen preparing", icon: "restaurant-outline" },
  { key: "packed", label: "Packed", icon: "cube-outline" },
  { key: "out_for_delivery", label: "Out for delivery", icon: "bicycle-outline" },
  { key: "delivered", label: "Delivered", icon: "home-outline" },
];

const COD_STATUS_STEPS: { key: string; label: string; icon: any }[] = [
  { key: "confirmed", label: "Order confirmed", icon: "receipt-outline" },
  { key: "preparing", label: "Kitchen preparing", icon: "restaurant-outline" },
  { key: "packed", label: "Packed", icon: "cube-outline" },
  { key: "out_for_delivery", label: "Out for delivery", icon: "bicycle-outline" },
  { key: "delivered", label: "Delivered · pay driver", icon: "cash-outline" },
];

export default function OrderScreen() {
  const { id, paid, session_id } = useLocalSearchParams<{ id: string; paid?: string; session_id?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [order, setOrder] = useState<Order | null>(null);
  const [tracking, setTracking] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [polling, setPolling] = useState(false);

  const load = useCallback(async () => {
    const r = await api.get<Order>(`/orders/${id}`);
    if (r.ok) setOrder(r.data);
    setLoading(false);
  }, [id]);

  const loadTracking = useCallback(async () => {
    const r = await api.get<any>(`/orders/${id}/tracking`);
    if (r.ok) setTracking(r.data);
  }, [id]);

  useEffect(() => { load(); loadTracking(); }, [load, loadTracking]);

  // Live tracking polling: 8s while out_for_delivery (matches driver's ~8s GPS
  // heartbeat), 20s otherwise. Keeps the map + ETA feeling live.
  useEffect(() => {
    if (!order) return;
    const active = ["out_for_delivery", "preparing", "packed"].includes(order.status);
    if (!active) return;
    const isMoving = order.status === "out_for_delivery";
    const iv = setInterval(() => { load(); loadTracking(); }, isMoving ? 8000 : 20000);
    return () => clearInterval(iv);
  }, [order?.status, load, loadTracking]);

  // If we came back from Stripe (paid=1 or session_id), poll checkout status a few times
  useEffect(() => {
    if (!order?.stripe_session_id) return;
    if (order.payment_status === "paid") return;
    let mounted = true;
    let attempts = 0;
    setPolling(true);
    const tick = async () => {
      attempts++;
      const r = await api.get<{ payment_status: string }>(`/checkout/status/${order.stripe_session_id}`);
      await load();
      if (!mounted) return;
      if (r.ok && r.data.payment_status === "paid") { setPolling(false); return; }
      if (attempts < 6) setTimeout(tick, 2000);
      else setPolling(false);
    };
    tick();
    return () => { mounted = false; };
    // eslint-disable-next-line
  }, [order?.stripe_session_id]);

  // Client-side "live" ETA — re-derived every second from the freshest
  // driver→destination haversine so "Arriving in ~X min" ticks down between
  // server polls. Falls back to server ETA when we can't compute locally.
  const [liveEtaSec, setLiveEtaSec] = useState<number | null>(null);
  const [liveDistM, setLiveDistM] = useState<number | null>(null);

  useEffect(() => {
    if (!tracking?.partner_location?.lat || !tracking?.destination?.lat) {
      setLiveEtaSec(null); setLiveDistM(null); return;
    }
    const d = haversineMeters(
      { lat: tracking.partner_location.lat, lng: tracking.partner_location.lng },
      { lat: tracking.destination.lat, lng: tracking.destination.lng },
    );
    setLiveDistM(Math.round(d));
    // 30 km/h city avg + 20s idle buffer, floor at 60s so the chip never
    // reads "0 min" while the driver is still on the road.
    const est = Math.max(60, Math.round((d / 1000) / 30 * 3600) + 20);
    setLiveEtaSec(est);
  }, [tracking?.partner_location?.lat, tracking?.partner_location?.lng,
      tracking?.destination?.lat, tracking?.destination?.lng]);

  // Countdown every second — makes "Arriving in ~X min" feel alive between polls.
  useEffect(() => {
    if (liveEtaSec == null || liveEtaSec <= 0) return;
    const iv = setInterval(() => {
      setLiveEtaSec(s => (s == null || s <= 5 ? s : s - 5));
    }, 5000);
    return () => clearInterval(iv);
  }, [liveEtaSec != null]);

  // Arrival alert: fires ONCE per order when the driver first crosses <500m.
  // Uses a ref-lock so re-renders don't re-trigger the chime + haptic.
  const [showArrivalBanner, setShowArrivalBanner] = useState(false);
  const arrivalFiredRef = useRef<string | null>(null);
  useEffect(() => {
    if (!order?.order_id || liveDistM == null) return;
    if (tracking?.delivery_status === "delivered") return;
    if (liveDistM >= 500) return;
    if (arrivalFiredRef.current === order.order_id) return;
    arrivalFiredRef.current = order.order_id;
    playArrivalCue();
    setShowArrivalBanner(true);
    // Auto-dismiss after 20s (banner stays clickable-to-dismiss).
    const t = setTimeout(() => setShowArrivalBanner(false), 20000);
    return () => clearTimeout(t);
  }, [order?.order_id, liveDistM, tracking?.delivery_status]);

  if (loading || !order) return <View style={styles.center}><ActivityIndicator color={colors.primary} size="large" /></View>;

  // Determine current step index — timeline depends on payment method.
  // Card/Stripe has an extra "awaiting payment" step; COD + Interac are confirmed on placement so they share the same timeline.
  const isPrepaidCardFlow = order.payment_method === "card";
  const isCod = order.payment_method === "cod" || order.payment_method === "cash_on_delivery";
  const STATUS_STEPS = isPrepaidCardFlow ? CARD_STATUS_STEPS : COD_STATUS_STEPS;
  const eventStatuses: string[] = (order.tracking_events || []).map((e: any) => e.status);
  const stepReached: Record<string, boolean> = {};
  STATUS_STEPS.forEach(s => { stepReached[s.key] = eventStatuses.includes(s.key); });
  const currentIdx = Math.max(...STATUS_STEPS.map((s, i) => (stepReached[s.key] ? i : -1)));

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <SafeAreaView edges={["top"]}>
        <View style={styles.header}>
          <TouchableOpacity testID="order-back" onPress={() => router.replace("/(tabs)/orders")} style={styles.iconBtn}>
            <Ionicons name="chevron-back" size={22} color={colors.text} />
          </TouchableOpacity>
          <View style={{ flex: 1, alignItems: "center" }}>
            <Text style={styles.headerId}>Order</Text>
            <Text style={styles.headerCode}>#{String(order.order_id).slice(-6).toUpperCase()}</Text>
          </View>
          <View style={{ width: 40 }} />
        </View>
      </SafeAreaView>

      <ScrollView
        testID="order-scroll"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40 + insets.bottom, gap: spacing.lg }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={colors.primary} />}
      >
        {isPrepaidCardFlow && order.payment_status !== "paid" && (
          <View style={styles.warnBox} testID="order-payment-pending">
            <Ionicons name="alert-circle" size={18} color="#B45309" />
            <Text style={styles.warnText}>{polling ? "Confirming your payment…" : "Payment pending. Complete checkout to secure your slot."}</Text>
          </View>
        )}

        {isCod && (
          <View style={styles.codBox} testID="order-cod-banner">
            <Ionicons name="cash" size={18} color={colors.success} />
            <Text style={styles.codText}>
              Cash on Delivery — please have {centsToCAD(order.total_cents)} ready at your door.
            </Text>
          </View>
        )}

        {/* Delivery address */}
        <View style={styles.mapCard} testID="order-address-card">
          <View style={styles.addrRow}>
            <Ionicons name="location" size={16} color={colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.addrLabel}>DELIVERING TO</Text>
              <Text style={styles.addrText}>{order.address.line1}{order.address.line2 ? `, ${order.address.line2}` : ""}, {order.address.city}, {order.address.postal_code}</Text>
              {!!order.phone && <Text style={styles.addrText}>📞 {order.phone}</Text>}
            </View>
          </View>
        </View>

        {!!order.delivery_proof_photo_url && (
          <View style={styles.proofCard} testID="order-proof-card">
            <View style={styles.addrRow}>
              <Ionicons name="checkmark-done-circle" size={16} color={colors.success} />
              <Text style={styles.proofTitle}>Delivered — proof photo</Text>
            </View>
            <Image source={{ uri: mediaUrl(order.delivery_proof_photo_url) }} style={styles.proofPhoto} resizeMode="cover" />
          </View>
        )}


        {/* Live tracking */}
        {tracking && tracking.delivery_partner && (
          <View style={styles.trackCard} testID="order-live-tracking">
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <View style={styles.livePulse}><View style={styles.livePulseDot} /></View>
              <Text style={styles.trackTitle}>Live tracking</Text>
              {(() => {
                // ETA display strategy:
                //   • stops_away === 0  → driver is heading to you now → show exact ETA (uses per-leg time when available).
                //   • stops_away  >  0  → show "N stops away · ~X-Y min" broad window (per-leg time × remaining).
                //   • delivered         → hide the chip.
                const away: number | null = typeof tracking.stops_away === "number" ? tracking.stops_away : null;
                // Prefer the live client-side ETA when we can compute one — that's
                // the one that ticks down each second. Fall back to the server ETA.
                const eta = (liveEtaSec != null && away === 0) ? liveEtaSec : (tracking.eta_seconds ?? 0);
                const leg = tracking.leg_duration_sec ?? 0;
                if (tracking.delivery_status === "delivered") return null;
                if (away === 0) {
                  const min = Math.max(1, Math.round((eta || leg) / 60));
                  return (
                    <View style={styles.etaChip} testID="order-eta-exact">
                      <Ionicons name="time-outline" size={12} color="#fff" />
                      <Text style={styles.etaChipText}>Arriving in ~{min} min</Text>
                    </View>
                  );
                }
                if (typeof away === "number" && away > 0) {
                  const perStopMin = (leg || 600) / 60;                       // fall back to 10 min per leg
                  const midMin = Math.max(5, perStopMin * (away + 1));
                  const lo = Math.max(5, Math.round((midMin * 0.7) / 5) * 5); // round to nearest 5-min bucket
                  const hi = Math.max(lo + 5, Math.round((midMin * 1.3) / 5) * 5);
                  return (
                    <View style={[styles.etaChip, { backgroundColor: colors.text }]} testID="order-eta-window">
                      <Ionicons name="list-outline" size={12} color="#fff" />
                      <Text style={styles.etaChipText}>{away} {away === 1 ? "stop" : "stops"} away · ~{lo}-{hi} min</Text>
                    </View>
                  );
                }
                if (eta > 0) {
                  const min = Math.max(1, Math.round(eta / 60));
                  return (
                    <View style={styles.etaChip}>
                      <Ionicons name="time-outline" size={12} color="#fff" />
                      <Text style={styles.etaChipText}>ETA {min} min</Text>
                    </View>
                  );
                }
                return null;
              })()}
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 }}>
              <View style={styles.driverAvatar}><Text style={styles.driverInitial}>{(tracking.delivery_partner.name || "?").slice(0, 1)}</Text></View>
              <View style={{ flex: 1 }}>
                <Text style={styles.driverName}>{tracking.delivery_partner.name}</Text>
                <Text style={styles.driverMeta}>{(tracking.delivery_status || "assigned").replace(/_/g, " ")}</Text>
              </View>
              {!!tracking.delivery_partner.phone && (
                <TouchableOpacity onPress={() => import("react-native").then(m => m.Linking.openURL(`tel:${tracking.delivery_partner.phone}`))} style={styles.callBtn} testID="order-call-driver">
                  <Ionicons name="call" size={14} color="#fff" />
                </TouchableOpacity>
              )}
            </View>
            {tracking.partner_location?.lat != null && tracking.destination?.lat != null && (
              <View style={styles.trackMapWrap}>
                <LiveTrackingMap
                  driver={{ lat: tracking.partner_location.lat, lng: tracking.partner_location.lng }}
                  destination={{
                    lat: tracking.destination.lat,
                    lng: tracking.destination.lng,
                    address: tracking.destination.address || "",
                  }}
                  polyline={tracking.route_polyline || null}
                  height={240}
                />
                {/* Uber-Eats-style "driver arriving" banner. Fires once (< 500 m)
                    and auto-dismisses after 20s — user can tap to dismiss early. */}
                {showArrivalBanner && (
                  <TouchableOpacity
                    activeOpacity={0.9}
                    onPress={() => setShowArrivalBanner(false)}
                    style={styles.arrivalBanner}
                    testID="order-arrival-banner"
                  >
                    <View style={styles.arrivalIcon}>
                      <Ionicons name="notifications" size={16} color="#fff" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.arrivalTitle}>Your driver is arriving 🎉</Text>
                      <Text style={styles.arrivalSubtitle}>
                        {liveDistM != null ? `${liveDistM} m away · head to the door` : "Head to the door"}
                      </Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color="#fff" />
                  </TouchableOpacity>
                )}
              </View>
            )}
          </View>
        )}

        {/* Timeline */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Progress</Text>
          <View style={{ gap: 4 }}>
            {STATUS_STEPS.map((s, i) => {
              const reached = i <= currentIdx;
              const active = i === currentIdx;
              return (
                <View key={s.key} style={styles.stepRow} testID={`order-step-${s.key}`}>
                  <View style={styles.stepColLine}>
                    <View style={[styles.node, reached && { backgroundColor: colors.primary, borderColor: colors.primary }, active && { transform: [{ scale: 1.2 }] }]}>
                      {reached && <Ionicons name="checkmark" size={12} color="#fff" />}
                    </View>
                    {i < STATUS_STEPS.length - 1 && <View style={[styles.line, reached && { backgroundColor: colors.primary }]} />}
                  </View>
                  <View style={{ flex: 1, paddingBottom: spacing.md }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <Ionicons name={s.icon} size={14} color={reached ? colors.primary : colors.textMuted} />
                      <Text style={[styles.stepLabel, reached && { color: colors.text, fontWeight: "700" }]}>{s.label}</Text>
                    </View>
                    {active && <Text style={styles.stepMeta}>Current status</Text>}
                  </View>
                </View>
              );
            })}
          </View>
        </View>

        {/* Items */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Items</Text>
          <View style={styles.itemsBox}>
            {order.items_snapshot.map((it: any, idx: number) => {
              const isCombo = it.kind === "weekly_package";
              const picks = isCombo ? expandComboPicks(it) : [];
              return (
                <View key={idx}>
                  <View style={styles.itemRow} testID={`order-item-${idx}`}>
                    <Image source={{ uri: mediaUrl(it.image_url) }} style={styles.itemThumb} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemName}>{it.name}</Text>
                      <Text style={styles.itemMeta}>×{it.quantity} · {centsToCAD(it.unit_price_cents)} each</Text>
                    </View>
                    <Text style={styles.itemTotal}>{centsToCAD(it.line_total_cents)}</Text>
                  </View>
                  {isCombo && picks.length > 0 && (
                    <View style={styles.picksBox}>
                      {picks.map((p, i) => (
                        <View key={i} style={styles.pickRow}>
                          <Ionicons name="restaurant-outline" size={13} color={colors.primary} />
                          <Text style={styles.pickText}>{p.name}</Text>
                          <Text style={styles.pickQty}>× {p.qty}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        </View>

        {/* Summary */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Summary</Text>
          <View style={styles.summaryBox}>
            <Row label="Subtotal" value={centsToCAD(order.subtotal_cents)} />
            <Row label="Delivery" value={centsToCAD(order.delivery_fee_cents)} />
            {order.discount_cents > 0 && <Row label={`Coupon ${order.coupon_code || ""}`} value={`-${centsToCAD(order.discount_cents)}`} color={colors.success} />}
            {order.points_redeemed_cents > 0 && <Row label="Points redeemed" value={`-${centsToCAD(order.points_redeemed_cents)}`} color={colors.success} />}
            <View style={styles.hr} />
            <Row label="Total" value={centsToCAD(order.total_cents)} bold />
            {order.points_awarded > 0 && <Text style={styles.pointsAwarded}>🎉 +{order.points_awarded} loyalty points earned</Text>}
          </View>
        </View>

        {/* Slot */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Delivery slot</Text>
          <View style={styles.slotBox}>
            <Ionicons name="calendar" size={22} color={colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.slotDate}>{order.slot.date}</Text>
              <Text style={styles.slotWin}>{order.slot.window === "friday_evening" ? "Friday · 6–9 PM" : "Saturday · 9 AM–12 PM"}</Text>
            </View>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

function Row({ label, value, color, bold }: { label: string; value: string; color?: string; bold?: boolean }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 }}>
      <Text style={{ color: colors.textMuted, fontSize: 13, fontWeight: bold ? "700" : "500" }}>{label}</Text>
      <Text style={{ color: color || colors.text, fontSize: bold ? 18 : 14, fontWeight: bold ? "800" : "600" }}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  header: { flexDirection: "row", alignItems: "center", padding: spacing.lg, borderBottomWidth: 1, borderBottomColor: colors.border },
  iconBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  headerId: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  headerCode: { fontSize: 18, fontWeight: "800", color: colors.text },
  section: { gap: spacing.sm },
  sectionTitle: { color: colors.textMuted, letterSpacing: 2, fontSize: 11, fontWeight: "800", marginBottom: 4 },
  warnBox: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#FEF3C7", padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: "#FDE68A" },
  warnText: { color: "#7C4A03", fontSize: 12, fontWeight: "600", flex: 1 },
  codBox: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#DCFCE7", padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: "#BBF7D0" },
  codText: { color: "#065F46", fontSize: 12, fontWeight: "700", flex: 1 },
  mapCard: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, overflow: "hidden", ...shadows.soft },
  proofCard: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.md, gap: spacing.sm, ...shadows.soft },
  proofTitle: { fontSize: 14, fontWeight: "800", color: colors.text },
  proofPhoto: { width: "100%", height: 220, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  addrRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, padding: spacing.md },
  // Live tracking card
  trackCard: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.md, gap: 4, ...shadows.soft },
  trackTitle: { fontSize: 14, fontWeight: "800", color: colors.text },
  livePulse: { width: 12, height: 12, borderRadius: 6, backgroundColor: "#FEE2E2", alignItems: "center", justifyContent: "center" },
  livePulseDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#DC2626" },
  etaChip: { flexDirection: "row", alignItems: "center", gap: 4, marginLeft: "auto", backgroundColor: colors.success, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  etaChipText: { color: "#fff", fontWeight: "800", fontSize: 12 },
  driverAvatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  driverInitial: { color: "#fff", fontWeight: "800" },
  driverName: { color: colors.text, fontWeight: "800", fontSize: 14 },
  driverMeta: { color: colors.textMuted, fontSize: 12, textTransform: "capitalize" },
  callBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  trackMap: { width: "100%", height: 180, borderRadius: radius.md, marginTop: spacing.sm, backgroundColor: colors.surfaceAlt },
  trackMapWrap: { marginTop: spacing.sm, position: "relative" },
  arrivalBanner: {
    position: "absolute",
    top: 10,
    left: 10,
    right: 10,
    backgroundColor: "#00A651",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    ...shadows.card,
  },
  arrivalIcon: {
    width: 30, height: 30, borderRadius: 15,
    backgroundColor: "rgba(255,255,255,0.22)",
    alignItems: "center", justifyContent: "center",
  },
  arrivalTitle: { color: "#fff", fontWeight: "800", fontSize: 14 },
  arrivalSubtitle: { color: "rgba(255,255,255,0.9)", fontSize: 12, marginTop: 2 },
  addrLabel: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  addrText: { color: colors.text, fontSize: 13, marginTop: 2 },

  stepRow: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  stepColLine: { alignItems: "center" },
  node: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  line: { width: 2, flex: 1, backgroundColor: colors.border, minHeight: 24 },
  stepLabel: { color: colors.textMuted, fontSize: 14, fontWeight: "500" },
  stepMeta: { color: colors.primary, fontSize: 11, marginTop: 2, marginLeft: 20, fontWeight: "700" },

  itemsBox: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.sm, gap: 4 },
  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: 6 },
  itemThumb: { width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  itemName: { fontSize: 13, fontWeight: "700", color: colors.text },
  itemMeta: { fontSize: 11, color: colors.textMuted },
  itemTotal: { fontSize: 13, fontWeight: "700", color: colors.text },
  picksBox: { marginLeft: 60, marginTop: -4, marginBottom: 8, paddingLeft: 10, borderLeftWidth: 2, borderLeftColor: colors.surfaceAlt, gap: 4 },
  pickRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 2 },
  pickText: { flex: 1, color: colors.text, fontSize: 13, fontWeight: "600" },
  pickQty: { color: colors.primary, fontSize: 13, fontWeight: "800" },

  summaryBox: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  hr: { height: 1, backgroundColor: colors.border, marginVertical: 6 },
  pointsAwarded: { color: colors.success, fontWeight: "700", marginTop: 8, textAlign: "center" },

  slotBox: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  slotDate: { fontSize: 15, fontWeight: "800", color: colors.text },
  slotWin: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
});
