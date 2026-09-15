import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView, Image,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import AdminShell from "@/src/components/AdminShell";
import ExportMenu from "@/src/components/ExportMenu";
import NewOrderModal from "@/src/components/NewOrderModal";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { getBackendUrl } from "@/src/utils/backendUrl";
import { expandComboPicks } from "@/src/utils/comboExpand";
import { colors, spacing, radius, shadows } from "@/src/theme";

type Order = {
  order_id: string; user_id: string; status: string; payment_status: string; payment_method: string;
  phone?: string;
  total_cents: number; subtotal_cents: number; delivery_fee_cents: number; discount_cents: number;
  created_at: string;
  slot: { date: string; window: string };
  address: { line1: string; line2?: string; city: string; postal_code: string; name?: string };
  items_snapshot: {
    name: string; image_url?: string; quantity: number;
    catering_guest_count?: number; unit_price_cents: number; line_total_cents: number;
    kind: string;
    package_selection_names?: string[];
  }[];
  customer_name?: string;
  user_summary?: { name?: string; email?: string; phone?: string };
};

const NEXT_STATUS: Record<string, { key: string; label: string }[]> = {
  new: [{ key: "confirmed", label: "Confirm order" }],
  confirmed: [{ key: "preparing", label: "Start preparing" }],
  preparing: [{ key: "packed", label: "Mark packed" }],
  packed: [{ key: "out_for_delivery", label: "Mark out for delivery" }],
  out_for_delivery: [{ key: "delivered", label: "Mark delivered" }],
  delivered: [],
  pending_payment: [],
  cancelled: [],
};

const STATUS_META: Record<string, { color: string; icon: any; label: string }> = {
  new:              { color: "#6d28d9",    icon: "sparkles-outline",           label: "New" },
  confirmed:        { color: colors.accent, icon: "checkmark-circle-outline",   label: "Confirmed" },
  preparing:        { color: colors.secondary, icon: "restaurant-outline",     label: "Preparing" },
  packed:           { color: "#0284c7",    icon: "cube-outline",                label: "Packed" },
  out_for_delivery: { color: colors.primary, icon: "bicycle-outline",           label: "On the way" },
  delivered:        { color: colors.success, icon: "checkmark-done-outline",    label: "Delivered" },
  pending_payment:  { color: "#B45309",    icon: "card-outline",                label: "Awaiting payment" },
  cancelled:        { color: colors.danger, icon: "close-circle-outline",       label: "Cancelled" },
};

/** Return the Sunday-anchored week-start (YYYY-MM-DD) of the given date. */
// Removed weekStartOf() + bucketLabel() helpers — orders are now shown as
// a flat newest-first list (no week grouping). See the sortedOrders memo.

export default function AdminOrders() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [integrationsCfg, setIntegrationsCfg] = useState({ email: false, twilio: false, drive: false, emailRecipient: "" });
  const [newOrderOpen, setNewOrderOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const path = filter ? `/admin/orders?status_filter=${filter}` : "/admin/orders";
    const [r, ir] = await Promise.all([
      adminApi.get<Order[]>(path),
      adminApi.get<any>("/admin/integrations"),
    ]);
    if (r.status === 401) { router.replace("/admin"); return; }
    if (r.ok) setOrders(Array.isArray(r.data) ? r.data : []);
    if (ir.ok) setIntegrationsCfg({
      email: !!ir.data?.email?.configured && !!ir.data?.email?.recipient,
      twilio: !!ir.data?.twilio?.configured,
      drive: !!ir.data?.google_drive?.configured,
      emailRecipient: ir.data?.email?.recipient || "",
    });
    setLoading(false);
  }, [filter, router]);

  useEffect(() => {
    (async () => {
      const t = await getAdminToken();
      if (!t) return router.replace("/admin");
      await load();
    })();
  }, [router, load]);

  const advance = async (o: Order, next: string) => {
    const r = await adminApi.post(`/admin/orders/${o.order_id}/status`, { status: next });
    if (r.ok) await load();
  };

  const toggleOne = (id: string) => setSelected(s => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleAll = () => setSelected(s =>
    s.size === orders.length ? new Set() : new Set(orders.map(o => o.order_id))
  );

  // Flat list, newest orders first — no week grouping (per user request).
  // Sort primarily by created_at (falling back to slot.date for legacy rows).
  const sortedOrders = useMemo(() => {
    const scoreOf = (o: Order): number => {
      const ts = (o as any).created_at || (o as any).createdAt || o.slot?.date;
      const n = ts ? new Date(ts).getTime() : 0;
      return Number.isFinite(n) ? n : 0;
    };
    return [...orders].sort((a, b) => scoreOf(b) - scoreOf(a));
  }, [orders]);

  const doExport = async (dest: "download" | "drive" | "sms", opts?: any) => {
    const body = {
      order_ids: [...selected], // empty = all
      destination: dest,
      sms_to: opts?.sms_to,
      sms_message: opts?.sms_message,
    };
    const r = await adminApi.post<any>("/admin/orders/export", body);
    if (!r.ok) throw new Error(r.error || "Export failed");
    return r.data;
  };

  const FILTERS = [
    { k: "", label: "All" },
    { k: "new", label: "New" },
    { k: "confirmed", label: "Confirmed" },
    { k: "preparing", label: "Preparing" },
    { k: "out_for_delivery", label: "On the way" },
    { k: "delivered", label: "Delivered" },
    { k: "cancelled", label: "Cancelled" },
  ];

  return (
    <AdminShell title="Orders">
      {/* Top row: filter chips + export button */}
      <View style={styles.topRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, alignItems: "center" }} style={{ flex: 1 }}>
          {FILTERS.map(f => {
            const active = filter === f.k;
            return (
              <TouchableOpacity
                key={f.k || "all"}
                testID={`orders-filter-${f.k || "all"}`}
                onPress={() => { setFilter(f.k); setSelected(new Set()); }}
                style={[styles.chip, active && styles.chipActive]}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{f.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
        <ExportMenu
          testID="orders-export"
          selectedCount={selected.size}
          totalCount={orders.length}
          isConfigured={integrationsCfg}
          onExport={doExport}
          disabled={loading}
        />
        <TouchableOpacity
          testID="new-order-btn"
          onPress={() => setNewOrderOpen(true)}
          style={styles.newOrderBtn}
        >
          <Ionicons name="add-circle" size={16} color="#fff" />
          <Text style={styles.newOrderBtnText}>New order</Text>
        </TouchableOpacity>
      </View>

      <NewOrderModal
        visible={newOrderOpen}
        onClose={() => setNewOrderOpen(false)}
        onCreated={() => load()}
      />

      {/* Select-all + count row */}
      {orders.length > 0 && (
        <TouchableOpacity onPress={toggleAll} style={styles.selectAllRow} testID="orders-select-all">
          <View style={[styles.checkbox, selected.size === orders.length && styles.checkboxOn]}>
            {selected.size === orders.length && <Ionicons name="checkmark" size={14} color="#fff" />}
            {selected.size > 0 && selected.size < orders.length && <View style={styles.checkboxDash} />}
          </View>
          <Text style={styles.selectAllText}>
            {selected.size === 0
              ? `Select all (${orders.length})`
              : `${selected.size} selected · tap to ${selected.size === orders.length ? "deselect" : "select"} all`}
          </Text>
        </TouchableOpacity>
      )}

      {loading ? <ActivityIndicator color={colors.primary} size="large" /> : (
        <View style={{ gap: spacing.md }}>
          {sortedOrders.map(o => {
                const oid = o.order_id || "";
                const oidShort = oid ? `#${oid.slice(-6).toUpperCase()}` : "#—";
                const s = STATUS_META[o.status] || STATUS_META.preparing;
                const isOpen = expanded === oid;
                const nexts = NEXT_STATUS[o.status] || [];
                const isSelected = selected.has(oid);
                return (
                  <View key={oid || Math.random().toString(36)} style={[styles.card, isSelected && styles.cardSelected]} testID={`admin-order-${oid}`}>
                    <View style={styles.head}>
                      {/* Row-select checkbox */}
                      <TouchableOpacity
                        onPress={() => toggleOne(oid)}
                        style={{ padding: 4 }}
                        testID={`select-${oid}`}
                      >
                        <View style={[styles.checkbox, isSelected && styles.checkboxOn]}>
                          {isSelected && <Ionicons name="checkmark" size={14} color="#fff" />}
                        </View>
                      </TouchableOpacity>

                      <TouchableOpacity style={{ flex: 1 }} onPress={() => setExpanded(isOpen ? null : oid)}>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                          <Ionicons name="person-circle-outline" size={14} color={colors.primary} />
                          <Text style={styles.customerName} numberOfLines={1}>
                            {o.customer_name || o.user_summary?.name || o.address?.name || "Guest"}
                          </Text>
                          <Text style={styles.oid}>{oidShort}</Text>
                          <View style={[styles.statusPill, { backgroundColor: s.color + "22", borderColor: s.color }]}>
                            <Ionicons name={s.icon} size={12} color={s.color} />
                            <Text style={[styles.statusText, { color: s.color }]}>{s.label}</Text>
                          </View>
                          <View style={styles.methodPill}>
                            <Text style={styles.methodText}>{o.payment_method === "cod" ? "COD" : o.payment_method === "interac" ? "Interac" : "Card"}</Text>
                          </View>
                        </View>
                        <Text style={styles.userLine}>
                          {o.user_summary?.email || "-"} · 📞 {o.phone || o.user_summary?.phone || "-"}
                        </Text>
                        <Text style={styles.slotLine}>
                          🚚 {o.slot?.window === "friday_evening" ? "Fri evening" : "Sat morning"} · {o.slot?.date || "—"}
                        </Text>
                      </TouchableOpacity>

                      <TouchableOpacity onPress={() => setExpanded(isOpen ? null : oid)} style={{ alignItems: "flex-end" }}>
                        <Text style={styles.price}>CA${(o.total_cents / 100).toFixed(2)}</Text>
                        <Ionicons name={isOpen ? "chevron-up" : "chevron-down"} size={20} color={colors.textMuted} />
                      </TouchableOpacity>
                    </View>

                    {isOpen && (
                      <View style={styles.body}>
                        <Text style={styles.subhead}>DELIVERY</Text>
                        <Text style={styles.addr}>{o.address?.line1 || "—"}{o.address?.line2 ? `, ${o.address.line2}` : ""}{o.address?.city ? `, ${o.address.city}` : ""}{o.address?.postal_code ? `, ${o.address.postal_code}` : ""}</Text>
                        {!!(o as any).delivery_proof_photo_url && (
                          <View style={styles.proofBox} testID={`admin-proof-${oid}`}>
                            <Text style={styles.subhead}>PROOF OF DELIVERY</Text>
                            <Image source={{ uri: (o as any).delivery_proof_photo_url }} style={styles.proofImg} resizeMode="cover" />
                          </View>
                        )}


                        <Text style={[styles.subhead, { marginTop: spacing.md }]}>ITEMS</Text>
                        {(o.items_snapshot || []).map((it, idx) => {
                          const isCombo = (it as any).kind === "weekly_package";
                          const picks = isCombo ? expandComboPicks(it as any) : [];
                          return (
                            <View key={idx}>
                              <View style={styles.itemRow}>
                                {it.image_url ? <Image source={{ uri: it.image_url }} style={styles.itemThumb} /> : null}
                                <View style={{ flex: 1 }}>
                                  <Text style={styles.itemName}>{it.name}</Text>
                                  <Text style={styles.itemMeta}>
                                    {it.kind === "catering"
                                      ? `${it.catering_guest_count || 0} guests × CA$${(it.unit_price_cents / 100).toFixed(2)}/person`
                                      : `×${it.quantity} · CA$${(it.unit_price_cents / 100).toFixed(2)} each`}
                                  </Text>
                                </View>
                                <Text style={styles.itemTotal}>CA${(it.line_total_cents / 100).toFixed(2)}</Text>
                              </View>
                              {isCombo && picks.length > 0 && (
                                <View style={styles.picksBox}>
                                  {picks.map((p, i) => (
                                    <View key={i} style={styles.pickRow}>
                                      <Ionicons name="restaurant-outline" size={12} color={colors.primary} />
                                      <Text style={styles.pickText}>{p.name}</Text>
                                      <Text style={styles.pickQty}>× {p.qty}</Text>
                                    </View>
                                  ))}
                                </View>
                              )}
                            </View>
                          );
                        })}

                        {nexts.length > 0 && (
                          <View style={styles.actions}>
                            {nexts.map(n => (
                              <TouchableOpacity
                                key={n.key}
                                testID={`advance-${oid}-${n.key}`}
                                onPress={() => advance(o, n.key)}
                                style={styles.advBtn}
                              >
                                <Text style={styles.advBtnText}>{n.label}</Text>
                                <Ionicons name="arrow-forward" size={14} color="#fff" />
                              </TouchableOpacity>
                            ))}
                          </View>
                        )}
                        <View style={[styles.actions, { marginTop: 8 }]}>
                          <TouchableOpacity
                            testID={`invoice-${oid}`}
                            onPress={() => {
                              const url = `${getBackendUrl()}/api/invoice/${oid}`;
                              if (typeof window !== "undefined") window.open(url, "_blank");
                            }}
                            style={styles.linkBtn}
                          >
                            <Ionicons name="document-text-outline" size={14} color={colors.primary} />
                            <Text style={styles.linkBtnText}>View / print invoice</Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    )}
                  </View>
                );
              })}
          {orders.length === 0 && <Text style={styles.empty}>No orders in this filter.</Text>}
        </View>
      )}
    </AdminShell>
  );
}

const styles = StyleSheet.create({
  topRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md },

  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexShrink: 0 },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontSize: 12, fontWeight: "700", textTransform: "capitalize" },
  chipTextActive: { color: "#fff" },

  selectAllRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8, paddingHorizontal: 4 },
  selectAllText: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  checkbox: { width: 20, height: 20, borderRadius: 4, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  checkboxOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkboxDash: { width: 10, height: 2, backgroundColor: colors.primary },

  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, ...shadows.soft, overflow: "hidden" },
  cardSelected: { borderColor: colors.primary, borderWidth: 2 },
  head: { flexDirection: "row", alignItems: "center", padding: spacing.md, gap: spacing.md },
  oid: { color: colors.textMuted, fontSize: 12, fontWeight: "700", letterSpacing: 1 },
  customerName: { color: colors.text, fontSize: 14, fontWeight: "800", maxWidth: 160 },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1 },
  statusText: { fontSize: 11, fontWeight: "700", textTransform: "capitalize" },
  proofBox: { marginTop: spacing.md, gap: 6 },
  proofImg: { width: "100%", height: 200, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  methodPill: { paddingHorizontal: 6, paddingVertical: 3, borderRadius: 4, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  methodText: { fontSize: 10, fontWeight: "800", color: colors.text, letterSpacing: 1 },
  userLine: { color: colors.text, fontSize: 13, marginTop: 4, fontWeight: "600" },
  slotLine: { color: colors.textMuted, fontSize: 12 },
  price: { color: colors.primary, fontSize: 18, fontWeight: "800" },

  body: { padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border, gap: 4 },
  subhead: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  addr: { color: colors.text, fontSize: 13 },
  itemRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 6 },
  itemThumb: { width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt },
  itemName: { color: colors.text, fontSize: 13, fontWeight: "700" },
  itemMeta: { color: colors.textMuted, fontSize: 11 },
  itemTotal: { color: colors.text, fontWeight: "700", fontSize: 13 },
  picksBox: { marginLeft: 44, marginTop: -2, marginBottom: 6, paddingLeft: 10, borderLeftWidth: 2, borderLeftColor: colors.surfaceAlt, gap: 3 },
  pickRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 2 },
  pickText: { color: colors.text, fontSize: 12, flex: 1, fontWeight: "600" },
  pickQty: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  newOrderBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.accent, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill },
  newOrderBtnText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, flexWrap: "wrap" },
  advBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill },
  advBtnText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  linkBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.primary },
  linkBtnText: { color: colors.primary, fontWeight: "700", fontSize: 13 },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl },
});
