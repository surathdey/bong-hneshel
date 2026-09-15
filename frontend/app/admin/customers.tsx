/**
 * Admin Customers page.
 *
 * Features:
 *   - List of customers with aggregated stats (orders, total spent, loyalty, last order)
 *   - Search by name/email/phone
 *   - Multi-select + Export (Download / Drive / SMS) — same as Orders page
 *   - Row expand → shows saved addresses + full order history
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView, TextInput,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import AdminShell from "@/src/components/AdminShell";
import ExportMenu from "@/src/components/ExportMenu";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius } from "@/src/theme";

type Customer = {
  user_id: string; name: string; email: string; phone: string; role?: string;
  created_at?: string;
  loyalty_points: number;
  total_orders: number;
  total_spent_cents: number;
  last_order_date?: string | null;
  last_order_status?: string;
  addresses?: any[];
};

type Order = {
  order_id: string; created_at: string; status: string; total_cents: number;
  slot?: { date?: string };
  payment_method?: string;
  items_snapshot?: { name: string; quantity: number }[];
};

const STATUS_COLORS: Record<string, string> = {
  new: "#6d28d9", confirmed: colors.accent, preparing: colors.secondary,
  packed: "#0284c7", out_for_delivery: colors.primary, delivered: colors.success,
  cancelled: colors.danger, pending_payment: "#B45309",
};

function fmtDate(v?: string | null) {
  if (!v) return "—";
  try {
    const d = new Date(v);
    return d.toLocaleDateString("en-CA", { year: "numeric", month: "short", day: "numeric" });
  } catch { return v; }
}

export default function AdminCustomers() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [integrationsCfg, setIntegrationsCfg] = useState({ email: false, twilio: false, drive: false, emailRecipient: "" });
  const [detailCache, setDetailCache] = useState<Record<string, { orders: Order[]; addresses: any[]; loyalty_history?: any[]; loyalty_points?: number }>>({});
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [r, ir] = await Promise.all([
      adminApi.get<Customer[]>("/admin/customers"),
      adminApi.get<any>("/admin/integrations"),
    ]);
    if (r.status === 401) { router.replace("/admin"); return; }
    if (r.ok) setCustomers(r.data || []);
    if (ir.ok) setIntegrationsCfg({
      email: !!ir.data?.email?.configured && !!ir.data?.email?.recipient,
      twilio: !!ir.data?.twilio?.configured,
      drive: !!ir.data?.google_drive?.configured,
      emailRecipient: ir.data?.email?.recipient || "",
    });
    setLoading(false);
  }, [router]);

  useEffect(() => {
    (async () => {
      const t = await getAdminToken();
      if (!t) return router.replace("/admin");
      await load();
    })();
  }, [router, load]);

  const filtered = useMemo(() => {
    if (!search.trim()) return customers;
    const q = search.trim().toLowerCase();
    return customers.filter(c =>
      (c.name || "").toLowerCase().includes(q) ||
      (c.email || "").toLowerCase().includes(q) ||
      (c.phone || "").toLowerCase().includes(q)
    );
  }, [customers, search]);

  const toggleOne = (id: string) => setSelected(s => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleAll = () => setSelected(s =>
    s.size === filtered.length ? new Set() : new Set(filtered.map(c => c.user_id))
  );

  const expandRow = async (uid: string) => {
    setExpanded(prev => prev === uid ? null : uid);
    if (detailCache[uid]) return;
    setLoadingDetail(uid);
    const r = await adminApi.get<any>(`/admin/customers/${uid}`);
    if (r.ok) {
      setDetailCache(dc => ({ ...dc, [uid]: { orders: r.data?.orders || [], addresses: r.data?.customer?.addresses || [], loyalty_history: r.data?.loyalty_history || [], loyalty_points: r.data?.customer?.loyalty_points ?? 0 } }));
    }
    setLoadingDetail(null);
  };

  const doExport = async (dest: "download" | "drive" | "sms", opts?: any) => {
    const body = {
      user_ids: [...selected],
      destination: dest,
      include_order_history: true,
      sms_to: opts?.sms_to,
      sms_message: opts?.sms_message,
    };
    const r = await adminApi.post<any>("/admin/customers/export", body);
    if (!r.ok) throw new Error(r.error || "Export failed");
    return r.data;
  };

  const stats = useMemo(() => {
    const totalOrders = customers.reduce((s, c) => s + (c.total_orders || 0), 0);
    const totalSpent = customers.reduce((s, c) => s + (c.total_spent_cents || 0), 0);
    return { totalOrders, totalSpent };
  }, [customers]);

  return (
    <AdminShell title="Customers">
      {/* KPI strip */}
      <View style={styles.kpiRow}>
        <View style={styles.kpi}>
          <Ionicons name="people-outline" size={20} color={colors.primary} />
          <Text style={styles.kpiValue}>{customers.length}</Text>
          <Text style={styles.kpiLabel}>Total customers</Text>
        </View>
        <View style={styles.kpi}>
          <Ionicons name="bag-check-outline" size={20} color={colors.secondary} />
          <Text style={styles.kpiValue}>{stats.totalOrders}</Text>
          <Text style={styles.kpiLabel}>Total orders</Text>
        </View>
        <View style={styles.kpi}>
          <Ionicons name="cash-outline" size={20} color={colors.success} />
          <Text style={styles.kpiValue}>CA${(stats.totalSpent / 100).toFixed(0)}</Text>
          <Text style={styles.kpiLabel}>Lifetime revenue</Text>
        </View>
      </View>

      {/* Search + Export */}
      <View style={styles.topRow}>
        <View style={styles.searchWrap}>
          <Ionicons name="search-outline" size={16} color={colors.textMuted} />
          <TextInput
            testID="customers-search"
            placeholder="Search name, email, or phone…"
            value={search}
            onChangeText={setSearch}
            style={styles.searchInput}
            placeholderTextColor={colors.textMuted}
          />
          {search.length > 0 && (
            <TouchableOpacity onPress={() => setSearch("")}>
              <Ionicons name="close-circle" size={16} color={colors.textMuted} />
            </TouchableOpacity>
          )}
        </View>
        <ExportMenu
          testID="customers-export"
          selectedCount={selected.size}
          totalCount={filtered.length}
          isConfigured={integrationsCfg}
          onExport={doExport}
          disabled={loading}
        />
      </View>

      {/* Select-all row */}
      {filtered.length > 0 && (
        <TouchableOpacity onPress={toggleAll} style={styles.selectAllRow} testID="customers-select-all">
          <View style={[styles.checkbox, selected.size === filtered.length && styles.checkboxOn]}>
            {selected.size === filtered.length && <Ionicons name="checkmark" size={14} color="#fff" />}
          </View>
          <Text style={styles.selectAllText}>
            {selected.size === 0
              ? `Select all (${filtered.length})`
              : `${selected.size} selected · tap to ${selected.size === filtered.length ? "deselect" : "select"} all`}
          </Text>
        </TouchableOpacity>
      )}

      {loading ? (
        <ActivityIndicator color={colors.primary} size="large" />
      ) : filtered.length === 0 ? (
        <Text style={styles.empty}>No customers match your search.</Text>
      ) : (
        <ScrollView contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.xxl }}>
          {filtered.map(c => {
            const isOpen = expanded === c.user_id;
            const isSelected = selected.has(c.user_id);
            const detail = detailCache[c.user_id];
            return (
              <View key={c.user_id} style={[styles.card, isSelected && styles.cardSelected]} testID={`customer-${c.user_id}`}>
                <View style={styles.head}>
                  {/* Checkbox */}
                  <TouchableOpacity onPress={() => toggleOne(c.user_id)} testID={`select-${c.user_id}`} style={{ padding: 4 }}>
                    <View style={[styles.checkbox, isSelected && styles.checkboxOn]}>
                      {isSelected && <Ionicons name="checkmark" size={14} color="#fff" />}
                    </View>
                  </TouchableOpacity>

                  <TouchableOpacity style={{ flex: 1, gap: 2 }} onPress={() => expandRow(c.user_id)}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <Text style={styles.name}>{c.name || "—"}</Text>
                      {c.role === "guest" && (
                        <View style={styles.guestPill}>
                          <Text style={styles.guestPillText}>GUEST</Text>
                        </View>
                      )}
                      {c.loyalty_points > 0 && (
                        <View style={styles.pointsPill}>
                          <Ionicons name="star" size={10} color="#B45309" />
                          <Text style={styles.pointsPillText}>{c.loyalty_points} pts</Text>
                        </View>
                      )}
                    </View>
                    <Text style={styles.subLine}>
                      {c.email || "no email"} · 📞 {c.phone || "no phone"}
                    </Text>
                    <Text style={styles.subLineDim}>
                      Joined {fmtDate(c.created_at)}
                      {c.last_order_date ? ` · Last order ${fmtDate(c.last_order_date)}` : " · No orders yet"}
                      {c.last_order_status ? (
                        <Text style={{ color: STATUS_COLORS[c.last_order_status] || colors.textMuted, fontWeight: "700" }}>
                          {` (${c.last_order_status.replace(/_/g, " ")})`}
                        </Text>
                      ) : null}
                    </Text>
                  </TouchableOpacity>

                  <View style={styles.headStats}>
                    <Text style={styles.orderCount}>{c.total_orders} orders</Text>
                    <Text style={styles.spent}>CA${(c.total_spent_cents / 100).toFixed(2)}</Text>
                    <Ionicons name={isOpen ? "chevron-up" : "chevron-down"} size={18} color={colors.textMuted} />
                  </View>
                </View>

                {isOpen && (
                  <View style={styles.body}>
                    {loadingDetail === c.user_id ? (
                      <ActivityIndicator color={colors.primary} />
                    ) : detail ? (
                      <>
                        {/* Addresses */}
                        {detail.addresses.length > 0 && (
                          <>
                            <Text style={styles.subhead}>SAVED ADDRESSES</Text>
                            {detail.addresses.map((a: any, i: number) => (
                              <Text key={i} style={styles.addr}>
                                📍 {a.label ? `[${a.label}] ` : ""}{a.line1}{a.line2 ? `, ${a.line2}` : ""}, {a.city} {a.postal_code}
                              </Text>
                            ))}
                          </>
                        )}
                        {/* Order history */}
                        <Text style={[styles.subhead, { marginTop: spacing.md }]}>
                          ORDER HISTORY ({detail.orders.length})
                        </Text>
                        {detail.orders.length === 0 ? (
                          <Text style={styles.emptyMini}>No orders yet.</Text>
                        ) : detail.orders.map(o => (
                          <View key={o.order_id} style={styles.orderRow}>
                            <View style={{ flex: 1 }}>
                              <Text style={styles.orderTitle}>#{o.order_id.slice(-6).toUpperCase()} · {fmtDate(o.created_at)}</Text>
                              <Text style={styles.orderMeta}>
                                {(o.items_snapshot || []).slice(0, 3).map(i => `${i.quantity}× ${i.name}`).join(", ")}
                                {(o.items_snapshot?.length || 0) > 3 ? ` +${(o.items_snapshot!.length - 3)} more` : ""}
                              </Text>
                            </View>
                            <View style={{ alignItems: "flex-end", gap: 4 }}>
                              <Text style={[styles.statusMini, { color: STATUS_COLORS[o.status] || colors.textMuted }]}>
                                {o.status.replace(/_/g, " ")}
                              </Text>
                              <Text style={styles.orderTotal}>CA${(o.total_cents / 100).toFixed(2)}</Text>
                            </View>
                          </View>
                        ))}

                        {/* Loyalty history */}
                        <Text style={[styles.subhead, { marginTop: spacing.md }]}>
                          LOYALTY POINTS · BALANCE {detail.loyalty_points ?? c.loyalty_points} PTS
                        </Text>
                        {(!detail.loyalty_history || detail.loyalty_history.length === 0) ? (
                          <Text style={styles.emptyMini}>No points activity yet.</Text>
                        ) : detail.loyalty_history!.map((h: any) => (
                          <View key={h.entry_id} style={styles.orderRow} testID={`loyalty-entry-${h.entry_id}`}>
                            <View style={{ flex: 1 }}>
                              <Text style={styles.orderTitle}>
                                {h.type === "earn" ? "Earned" : "Redeemed"} · {fmtDate(h.created_at)}
                              </Text>
                              <Text style={styles.orderMeta}>{h.note || `Order #${(h.order_id || "").slice(-6).toUpperCase()}`}</Text>
                            </View>
                            <View style={{ alignItems: "flex-end", gap: 4 }}>
                              <Text style={[styles.orderTotal, { color: h.type === "earn" ? colors.success : colors.primary }]}>
                                {h.type === "earn" ? "+" : "−"}{h.points} pts
                              </Text>
                              {typeof h.balance_after === "number" && <Text style={styles.orderMeta}>bal {h.balance_after}</Text>}
                            </View>
                          </View>
                        ))}
                      </>
                    ) : (
                      <Text style={styles.emptyMini}>Loading…</Text>
                    )}
                  </View>
                )}
              </View>
            );
          })}
        </ScrollView>
      )}
    </AdminShell>
  );
}

const styles = StyleSheet.create({
  kpiRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md, flexWrap: "wrap" },
  kpi: { flex: 1, minWidth: 120, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: 4 },
  kpiValue: { fontSize: 22, fontWeight: "800", color: colors.text },
  kpiLabel: { fontSize: 11, color: colors.textMuted, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },

  topRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  searchWrap: { flex: 1, flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, backgroundColor: colors.surface, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, minHeight: 40 },
  searchInput: { flex: 1, color: colors.text, fontSize: 13, paddingVertical: 8 },

  selectAllRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8, paddingHorizontal: 4 },
  selectAllText: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  checkbox: { width: 20, height: 20, borderRadius: 4, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  checkboxOn: { backgroundColor: colors.primary, borderColor: colors.primary },

  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  cardSelected: { borderColor: colors.primary, borderWidth: 2 },
  head: { flexDirection: "row", alignItems: "center", padding: spacing.md, gap: spacing.md },
  name: { color: colors.text, fontWeight: "800", fontSize: 15 },
  guestPill: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 3, borderWidth: 1, borderColor: colors.border },
  guestPillText: { fontSize: 9, fontWeight: "800", color: colors.textMuted, letterSpacing: 1 },
  pointsPill: { flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: "#FEF3C7", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 3 },
  pointsPillText: { fontSize: 10, fontWeight: "800", color: "#B45309" },
  subLine: { color: colors.text, fontSize: 12, fontWeight: "600" },
  subLineDim: { color: colors.textMuted, fontSize: 11 },
  headStats: { alignItems: "flex-end", gap: 2 },
  orderCount: { color: colors.text, fontWeight: "700", fontSize: 12 },
  spent: { color: colors.primary, fontWeight: "800", fontSize: 15 },

  body: { padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border, gap: 4 },
  subhead: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  addr: { color: colors.text, fontSize: 12 },
  orderRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, gap: 8, borderBottomWidth: 1, borderBottomColor: colors.surfaceAlt },
  orderTitle: { color: colors.text, fontWeight: "700", fontSize: 13 },
  orderMeta: { color: colors.textMuted, fontSize: 11 },
  orderTotal: { color: colors.text, fontWeight: "800", fontSize: 13 },
  statusMini: { fontSize: 10, fontWeight: "800", textTransform: "uppercase", letterSpacing: 1 },
  emptyMini: { color: colors.textMuted, fontSize: 12, fontStyle: "italic" },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl },
});
