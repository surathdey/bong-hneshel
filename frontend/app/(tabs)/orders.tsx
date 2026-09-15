import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Image,
  ActivityIndicator,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { mediaUrl } from "@/src/utils/backendUrl";
import { useAuth } from "@/src/auth";
import { useCart } from "@/src/cart";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD } from "@/src/utils/format";

type Order = {
  order_id: string; status: string; payment_status: string; total_cents: number;
  created_at: string; slot: { date: string; window: string };
  items_snapshot: { name: string; image_url: string; quantity: number }[];
};

const STATUS_LABELS: Record<string, { label: string; color: string; icon: any }> = {
  pending_payment: { label: "Awaiting payment", color: "#B45309", icon: "card-outline" },
  new: { label: "Placed", color: "#6d28d9", icon: "sparkles-outline" },
  confirmed: { label: "Confirmed", color: colors.accent, icon: "checkmark-circle-outline" },
  paid: { label: "Paid", color: colors.success, icon: "checkmark-circle-outline" },
  preparing: { label: "Preparing", color: colors.secondary, icon: "restaurant-outline" },
  packed: { label: "Packed", color: "#0284c7", icon: "cube-outline" },
  out_for_delivery: { label: "Out for delivery", color: colors.primary, icon: "bicycle-outline" },
  delivered: { label: "Delivered", color: colors.success, icon: "checkmark-done-outline" },
  cancelled: { label: "Cancelled", color: colors.danger, icon: "close-circle-outline" },
};

export default function BagTab() {
  const { user } = useAuth();
  const { items: cartItems, setQty, subtotalCents, count } = useCart();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const load = useCallback(async () => {
    setError(null);
    const r = await api.get<Order[]>("/orders");
    if (r.ok) setOrders(r.data || []);
    else {
      setOrders([]);
      setError(r.error || `Could not load orders (status ${r.status})`);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [user?.user_id, load]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.primary} size="large" /></View>;

  const hasCart = cartItems.length > 0;
  const hasOrders = orders.length > 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <SafeAreaView edges={["top"]}>
        <View style={styles.header}>
          <Text style={styles.eyebrow}>YOUR</Text>
          <Text style={styles.title}>Bag</Text>
          <Text style={styles.sub}>
            {count > 0 ? `${count} item${count > 1 ? "s" : ""} in your cart` : "Your cart is empty"}
            {hasOrders ? ` · ${orders.length} past order${orders.length > 1 ? "s" : ""}` : ""}
          </Text>
        </View>
      </SafeAreaView>

      <ScrollView
        testID="bag-scroll"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 + insets.bottom, gap: spacing.lg }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={colors.primary} />}
      >
        {/* ============ CURRENT CART ============ */}
        <View style={styles.section}>
          <View style={styles.sectionHead}>
            <Text style={styles.sectionTitle}>In your cart</Text>
            {count > 0 && <Text style={styles.sectionRight}>{centsToCAD(subtotalCents)}</Text>}
          </View>

          {hasCart ? (
            <>
              <View style={styles.cartBox}>
                {cartItems.map(i => {
                  const isCatering = i.kind === "catering";
                  const isPackage = i.kind === "weekly_package";
                  const guests = i.catering_guest_count || 1;
                  const lineTotal = i.price_cents * (isCatering ? guests : 1) * i.quantity;
                  return (
                    <View key={i.cart_item_id} style={styles.cartRow} testID={`bag-cart-${i.cart_item_id}`}>
                      <Image source={{ uri: mediaUrl(i.image_url) }} style={styles.cartThumb} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.cartName} numberOfLines={2}>{i.name}</Text>
                        {isCatering ? (
                          <>
                            <Text style={styles.cartMeta}>
                              {i.tier_title ? `${i.tier_title} · ` : ""}
                              {centsToCAD(i.price_cents)} / person × {guests} guests
                            </Text>
                            {i.selection_labels?.slice(0, 3).map((s, idx) => (
                              <Text key={idx} style={styles.cartSub} numberOfLines={1}>
                                {s.title}: {s.items.join(", ")}
                              </Text>
                            ))}
                          </>
                        ) : isPackage ? (
                          <>
                            <Text style={styles.cartMeta}>
                              WEEKLY COMBO · Pick {i.package_pick_count} · {centsToCAD(i.price_cents)}
                            </Text>
                            <Text style={styles.cartSub} numberOfLines={2}>
                              {(i.package_selection_names || []).join(", ")}
                            </Text>
                          </>
                        ) : null}
                        <Text style={styles.cartPrice}>{centsToCAD(lineTotal)}</Text>
                      </View>
                      <View style={styles.stepper}>
                        <TouchableOpacity testID={`bag-dec-${i.cart_item_id}`} onPress={() => setQty(i.cart_item_id, i.quantity - 1)} style={styles.stepperBtn}>
                          <Ionicons name="remove" size={14} color={colors.text} />
                        </TouchableOpacity>
                        <Text style={styles.qty}>{i.quantity}</Text>
                        <TouchableOpacity testID={`bag-inc-${i.cart_item_id}`} onPress={() => setQty(i.cart_item_id, i.quantity + 1)} style={styles.stepperBtn}>
                          <Ionicons name="add" size={14} color={colors.text} />
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </View>
              <TouchableOpacity
                testID="bag-checkout-cta"
                style={styles.checkoutCta}
                onPress={() => router.push("/cart")}
              >
                <Text style={styles.checkoutCtaText}>Review & checkout</Text>
                <Ionicons name="arrow-forward" size={16} color="#fff" />
              </TouchableOpacity>
            </>
          ) : (
            <View style={styles.emptyCartBox} testID="bag-cart-empty">
              <Ionicons name="basket-outline" size={28} color={colors.textMuted} />
              <Text style={styles.emptyCartText}>Nothing in your cart yet.</Text>
              <TouchableOpacity testID="bag-browse-menu" style={styles.browseBtn} onPress={() => router.push("/(tabs)/menu")}>
                <Text style={styles.browseBtnText}>Browse menu</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* ============ PAST ORDERS ============ */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Past orders</Text>

          {error ? (
            <View style={styles.errorBox} testID="bag-orders-error">
              <Ionicons name="warning-outline" size={24} color={colors.danger} />
              <Text style={styles.errorText}>{error}</Text>
              <TouchableOpacity testID="bag-orders-retry" style={styles.retryBtn} onPress={load}>
                <Text style={styles.retryBtnText}>Try again</Text>
              </TouchableOpacity>
            </View>
          ) : hasOrders ? (
            <View style={{ gap: spacing.md }} testID="bag-orders-list">
              {orders.map((item) => {
                const s = STATUS_LABELS[item.status] || STATUS_LABELS.pending_payment;
                return (
                  <TouchableOpacity
                    key={item.order_id}
                    testID={`order-card-${item.order_id}`}
                    onPress={() => router.push(`/order/${item.order_id}`)}
                    style={styles.card}
                    activeOpacity={0.9}
                  >
                    <View style={styles.cardHead}>
                      <Text style={styles.orderId}>#{item.order_id.slice(-6).toUpperCase()}</Text>
                      <View style={[styles.statusPill, { backgroundColor: s.color + "22", borderColor: s.color }]}>
                        <Ionicons name={s.icon} size={12} color={s.color} />
                        <Text style={[styles.statusText, { color: s.color }]}>{s.label}</Text>
                      </View>
                    </View>
                    <View style={styles.imgs}>
                      {item.items_snapshot.slice(0, 4).map((i, idx) => (
                        <Image key={idx} source={{ uri: mediaUrl(i.image_url) }} style={[styles.thumb, { marginLeft: idx === 0 ? 0 : -12 }]} />
                      ))}
                      {item.items_snapshot.length > 4 && (
                        <View style={[styles.thumb, styles.moreThumb, { marginLeft: -12 }]}>
                          <Text style={styles.moreText}>+{item.items_snapshot.length - 4}</Text>
                        </View>
                      )}
                      <View style={{ flex: 1, marginLeft: spacing.md }}>
                        <Text style={styles.itemsLine} numberOfLines={1}>
                          {item.items_snapshot.map(i => `${i.name} ×${i.quantity}`).join(" · ")}
                        </Text>
                        <Text style={styles.slotLine}>
                          {item.slot.window === "friday_evening" ? "Fri evening" : "Sat morning"} · {item.slot.date}
                        </Text>
                      </View>
                    </View>
                    <View style={styles.foot}>
                      <Text style={styles.total}>{centsToCAD(item.total_cents)}</Text>
                      <View style={styles.trackBtn}>
                        <Text style={styles.trackBtnText}>Track order</Text>
                        <Ionicons name="arrow-forward" size={14} color={colors.primary} />
                      </View>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          ) : (
            <View style={styles.emptyOrdersBox} testID="bag-orders-empty">
              <Ionicons name="receipt-outline" size={28} color={colors.textMuted} />
              <Text style={styles.emptyCartText}>No past orders yet.</Text>
              <Text style={styles.emptySub}>Complete checkout and your orders will appear here.</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  header: { padding: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.background },
  eyebrow: { color: colors.primary, letterSpacing: 3, fontSize: 11, fontWeight: "800" },
  title: { fontSize: 26, fontWeight: "800", color: colors.text, marginTop: 4, letterSpacing: -0.3 },
  sub: { color: colors.textMuted, fontSize: 12, marginTop: 4 },

  section: { gap: spacing.md },
  sectionHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sectionTitle: { color: colors.textMuted, letterSpacing: 2, fontSize: 11, fontWeight: "800" },
  sectionRight: { color: colors.text, fontSize: 14, fontWeight: "800" },

  cartBox: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, ...shadows.soft, overflow: "hidden" },
  cartRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  cartThumb: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  cartName: { fontSize: 14, fontWeight: "700", color: colors.text },
  cartMeta: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  cartSub: { fontSize: 11, color: colors.textMuted, marginTop: 1 },
  cartPrice: { color: colors.primary, fontWeight: "700", fontSize: 13, marginTop: 2 },
  stepper: { flexDirection: "row", alignItems: "center", gap: 6 },
  stepperBtn: { width: 28, height: 28, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  qty: { fontSize: 13, fontWeight: "800", color: colors.text, minWidth: 20, textAlign: "center" },

  checkoutCta: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.pill, ...shadows.card },
  checkoutCtaText: { color: "#fff", fontWeight: "800", fontSize: 15 },

  emptyCartBox: { alignItems: "center", padding: spacing.xl, gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, borderStyle: "dashed" },
  emptyOrdersBox: { alignItems: "center", padding: spacing.xl, gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  emptyCartText: { color: colors.text, fontSize: 14, fontWeight: "700" },
  emptySub: { color: colors.textMuted, fontSize: 12, textAlign: "center" },
  browseBtn: { backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 10, borderRadius: radius.pill, marginTop: 4 },
  browseBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },

  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.md, ...shadows.soft, gap: spacing.md },
  cardHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  orderId: { fontSize: 12, fontWeight: "700", color: colors.textMuted, letterSpacing: 1 },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1 },
  statusText: { fontSize: 11, fontWeight: "700" },
  imgs: { flexDirection: "row", alignItems: "center" },
  thumb: { width: 42, height: 42, borderRadius: radius.pill, borderWidth: 2, borderColor: colors.surface, backgroundColor: colors.surfaceAlt },
  moreThumb: { alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceAlt },
  moreText: { fontSize: 11, fontWeight: "800", color: colors.text },
  itemsLine: { fontSize: 13, color: colors.text, fontWeight: "600" },
  slotLine: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  foot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.md },
  total: { fontSize: 18, fontWeight: "800", color: colors.primary },
  trackBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  trackBtnText: { color: colors.primary, fontWeight: "700", fontSize: 13 },

  errorBox: { alignItems: "center", padding: spacing.lg, gap: spacing.sm, backgroundColor: "#FEF2F2", borderRadius: radius.lg, borderWidth: 1, borderColor: "#FEE2E2" },
  errorText: { color: colors.danger, fontSize: 12, textAlign: "center" },
  retryBtn: { backgroundColor: colors.danger, paddingHorizontal: 18, paddingVertical: 8, borderRadius: radius.pill },
  retryBtnText: { color: "#fff", fontWeight: "700", fontSize: 12 },
});
