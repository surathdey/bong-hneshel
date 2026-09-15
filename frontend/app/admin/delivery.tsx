import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView,
  TextInput, Modal, Platform, Alert,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD } from "@/src/utils/format";

type Partner = {
  partner_id: string; name: string; email: string; phone: string; vehicle: string;
  is_active: boolean; active_orders?: number;
  current_lat?: number; current_lng?: number;
};

type Order = {
  order_id: string; status: string; delivery_status?: string | null;
  delivery_partner_id?: string | null; delivery_partner_name?: string | null;
  address: any; phone: string; total_cents: number; items_snapshot: any[];
  created_at: string; slot: any;
  customer_name?: string;
  user_summary?: { name?: string; email?: string; phone?: string };
};

type Tab = "partners" | "assign";

export default function AdminDelivery() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("partners");
  const [partners, setPartners] = useState<Partner[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Partner | null>(null);
  const [assigning, setAssigning] = useState<Order | null>(null);

  // Form state (create/edit)
  const [fName, setFName] = useState("");
  const [fEmail, setFEmail] = useState("");
  const [fPhone, setFPhone] = useState("");
  const [fVehicle, setFVehicle] = useState("car");
  const [fPassword, setFPassword] = useState("");

  const load = useCallback(async () => {
    const [rp, ro] = await Promise.all([
      adminApi.get<Partner[]>("/admin/delivery-partners"),
      adminApi.get<Order[]>("/admin/orders?statuses=confirmed,new,preparing,out_for_delivery"),
    ]);
    if (rp.status === 401 || ro.status === 401) { router.replace("/admin"); return; }
    if (rp.ok) setPartners(rp.data || []);
    if (ro.ok) setOrders(ro.data || []);
    setLoading(false);
  }, [router]);

  useEffect(() => {
    (async () => {
      const t = await getAdminToken();
      if (!t) return router.replace("/admin");
      await load();
    })();
    // Poll every 15s while on the page
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, [router, load]);

  const openCreate = () => {
    setEditing(null);
    setFName(""); setFEmail(""); setFPhone(""); setFVehicle("car"); setFPassword("");
    setCreating(true);
  };
  const openEdit = (p: Partner) => {
    setEditing(p);
    setFName(p.name); setFEmail(p.email); setFPhone(p.phone); setFVehicle(p.vehicle); setFPassword("");
    setCreating(true);
  };
  const closeForm = () => { setCreating(false); setEditing(null); };

  const savePartner = async () => {
    if (!fName.trim() || !fEmail.trim() || (!editing && !fPassword.trim())) {
      Alert.alert("Missing info", "Name, email and (for new partners) password are required.");
      return;
    }
    if (editing) {
      const body: any = { name: fName, phone: fPhone, vehicle: fVehicle };
      if (fPassword) body.password = fPassword;
      const r = await adminApi.patch(`/admin/delivery-partners/${editing.partner_id}`, body);
      if (!r.ok) { Alert.alert("Update failed", r.error || ""); return; }
    } else {
      const r = await adminApi.post("/admin/delivery-partners", {
        name: fName, email: fEmail.toLowerCase(), phone: fPhone,
        vehicle: fVehicle, password: fPassword,
      });
      if (!r.ok) { Alert.alert("Create failed", r.error || ""); return; }
    }
    closeForm();
    await load();
  };

  const toggleActive = async (p: Partner) => {
    const r = await adminApi.patch(`/admin/delivery-partners/${p.partner_id}`, { is_active: !p.is_active });
    if (!r.ok) Alert.alert("Update failed", r.error || "");
    await load();
  };

  const deletePartner = async (p: Partner) => {
    const ok = Platform.OS === "web" ? window.confirm(`Deactivate "${p.name}"? Any active orders will be unassigned.`) : true;
    if (!ok) return;
    await adminApi.del(`/admin/delivery-partners/${p.partner_id}`);
    await load();
  };

  const assignOrder = async (order: Order, partner_id: string | null) => {
    const r = await adminApi.post(`/admin/orders/${order.order_id}/assign`, { partner_id });
    if (!r.ok) { Alert.alert("Assignment failed", r.error || ""); return; }
    setAssigning(null);
    await load();
  };

  // Split orders: unassigned vs assigned
  const unassignedOrders = useMemo(() => orders.filter(o => !o.delivery_partner_id), [orders]);
  const assignedOrders = useMemo(() => orders.filter(o => !!o.delivery_partner_id), [orders]);

  return (
    <AdminShell title="Delivery">
      <View style={styles.tabRow}>
        <TouchableOpacity
          testID="tab-partners"
          onPress={() => setTab("partners")}
          style={[styles.tab, tab === "partners" && styles.tabActive]}
        >
          <Ionicons name="people-outline" size={16} color={tab === "partners" ? "#fff" : colors.text} />
          <Text style={[styles.tabText, tab === "partners" && styles.tabTextActive]}>Partners ({partners.length})</Text>
        </TouchableOpacity>
        <TouchableOpacity
          testID="tab-assign"
          onPress={() => setTab("assign")}
          style={[styles.tab, tab === "assign" && styles.tabActive]}
        >
          <Ionicons name="git-network-outline" size={16} color={tab === "assign" ? "#fff" : colors.text} />
          <Text style={[styles.tabText, tab === "assign" && styles.tabTextActive]}>Assign orders ({unassignedOrders.length} unassigned)</Text>
        </TouchableOpacity>
      </View>

      {loading ? <ActivityIndicator color={colors.primary} size="large" style={{ marginTop: spacing.xl }} /> : (
        tab === "partners" ? (
          <>
            <View style={styles.actionRow}>
              <Text style={styles.hint}>Manage the delivery workforce. Deactivating auto-unassigns their active orders.</Text>
              <TouchableOpacity testID="new-partner-btn" style={styles.primaryBtn} onPress={openCreate}>
                <Ionicons name="add" size={16} color="#fff" />
                <Text style={styles.primaryBtnText}>New partner</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.grid}>
              {partners.map(p => (
                <View key={p.partner_id} style={styles.pCard} testID={`partner-card-${p.partner_id}`}>
                  <View style={styles.pTop}>
                    <View style={styles.avatar}>
                      <Text style={styles.avatarText}>{(p.name || "?").slice(0, 1).toUpperCase()}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.pName}>{p.name}</Text>
                      <Text style={styles.pEmail}>{p.email}</Text>
                    </View>
                    <View style={[styles.stateChip, p.is_active ? styles.stateOn : styles.stateOff]}>
                      <Text style={[styles.stateChipText, p.is_active ? { color: "#166534" } : { color: "#991B1B" }]}>
                        {p.is_active ? "ACTIVE" : "OFF"}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.pMetaRow}>
                    <View style={styles.pMeta}><Ionicons name="call-outline" size={12} color={colors.textMuted} /><Text style={styles.pMetaText}>{p.phone || "—"}</Text></View>
                    <View style={styles.pMeta}><Ionicons name={p.vehicle === "bike" ? "bicycle-outline" : p.vehicle === "scooter" ? "flash-outline" : "car-outline"} size={12} color={colors.textMuted} /><Text style={styles.pMetaText}>{p.vehicle}</Text></View>
                    <View style={styles.pMeta}><Ionicons name="cube-outline" size={12} color={colors.textMuted} /><Text style={styles.pMetaText}>{p.active_orders || 0} active</Text></View>
                    {p.current_lat != null && (
                      <View style={styles.pMeta}><Ionicons name="location-outline" size={12} color={colors.success} /><Text style={styles.pMetaText}>online</Text></View>
                    )}
                  </View>
                  <View style={styles.pFoot}>
                    <TouchableOpacity testID={`edit-partner-${p.partner_id}`} style={styles.iconBtn} onPress={() => openEdit(p)}>
                      <Ionicons name="pencil" size={14} color={colors.text} />
                    </TouchableOpacity>
                    <TouchableOpacity testID={`toggle-partner-${p.partner_id}`} style={styles.iconBtn} onPress={() => toggleActive(p)}>
                      <Ionicons name={p.is_active ? "pause" : "play"} size={14} color={colors.text} />
                    </TouchableOpacity>
                    <TouchableOpacity testID={`del-partner-${p.partner_id}`} style={styles.iconBtn} onPress={() => deletePartner(p)}>
                      <Ionicons name="trash-outline" size={14} color={colors.danger} />
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
              {partners.length === 0 && <Text style={styles.empty}>No delivery partners yet — create your first one.</Text>}
            </View>
          </>
        ) : (
          <>
            <Text style={styles.sectionTitle}>Unassigned orders</Text>
            <View style={styles.assignList}>
              {unassignedOrders.map(o => (
                <OrderRow key={o.order_id} o={o} partners={partners} onAssign={pid => assignOrder(o, pid)} setAssigning={setAssigning} />
              ))}
              {unassignedOrders.length === 0 && <Text style={styles.empty}>Nothing to assign right now.</Text>}
            </View>

            <Text style={[styles.sectionTitle, { marginTop: spacing.xl }]}>Assigned & in progress</Text>
            <View style={styles.assignList}>
              {assignedOrders.map(o => (
                <OrderRow key={o.order_id} o={o} partners={partners} onAssign={pid => assignOrder(o, pid)} setAssigning={setAssigning} />
              ))}
              {assignedOrders.length === 0 && <Text style={styles.empty}>No orders in progress.</Text>}
            </View>
          </>
        )
      )}

      {/* ==== Create / Edit modal ==== */}
      <Modal visible={creating} transparent animationType="slide" onRequestClose={closeForm}>
        <View style={styles.overlay}>
          <View style={styles.modal} testID="partner-form-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>{editing ? `Edit — ${editing.name}` : "New delivery partner"}</Text>
              <TouchableOpacity onPress={closeForm}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ gap: spacing.sm }}>
              <Text style={styles.label}>Full name</Text>
              <TextInput value={fName} onChangeText={setFName} style={styles.input} testID="partner-name" />
              <Text style={styles.label}>Email {editing ? "(read-only)" : ""}</Text>
              <TextInput value={fEmail} onChangeText={setFEmail} editable={!editing} autoCapitalize="none" keyboardType="email-address" style={[styles.input, editing && { opacity: 0.6 }]} testID="partner-email" />
              <Text style={styles.label}>Phone</Text>
              <TextInput value={fPhone} onChangeText={setFPhone} keyboardType="phone-pad" style={styles.input} testID="partner-phone" />
              <Text style={styles.label}>Vehicle</Text>
              <View style={{ flexDirection: "row", gap: 6 }}>
                {(["car", "bike", "scooter"] as const).map(v => (
                  <TouchableOpacity key={v} onPress={() => setFVehicle(v)} style={[styles.vehChip, fVehicle === v && styles.vehChipOn]}>
                    <Text style={[styles.vehChipText, fVehicle === v && { color: "#fff" }]}>{v}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.label}>{editing ? "New password (leave blank to keep)" : "Password"}</Text>
              <TextInput value={fPassword} onChangeText={setFPassword} secureTextEntry style={styles.input} testID="partner-password" />
              <TouchableOpacity testID="partner-save" style={styles.primaryBtn} onPress={savePartner}>
                <Ionicons name="save" size={16} color="#fff" />
                <Text style={styles.primaryBtnText}>Save partner</Text>
              </TouchableOpacity>
              {!editing && (
                <Text style={styles.helperText}>The partner logs in at{" "}
                  <Text style={styles.mono}>/delivery-partner</Text> using this email + password.</Text>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ==== Assign modal ==== */}
      <Modal visible={!!assigning} transparent animationType="slide" onRequestClose={() => setAssigning(null)}>
        <View style={styles.overlay}>
          <View style={styles.modal} testID="assign-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>Assign delivery partner</Text>
              <TouchableOpacity onPress={() => setAssigning(null)}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>
            {assigning && (
              <>
                <Text style={styles.assignSub}>
                  {assigning.customer_name || assigning.user_summary?.name || assigning.address?.name || "Guest"} · Order {assigning.order_id.slice(0, 12)} · {centsToCAD(assigning.total_cents)} · {assigning.address?.line1}
                </Text>
                <ScrollView contentContainerStyle={{ gap: 6 }} style={{ maxHeight: 400 }}>
                  {partners.filter(p => p.is_active).map(p => (
                    <TouchableOpacity
                      key={p.partner_id}
                      style={[styles.pickerRow, assigning.delivery_partner_id === p.partner_id && styles.pickerRowActive]}
                      onPress={() => assignOrder(assigning, p.partner_id)}
                      testID={`assign-to-${p.partner_id}`}
                    >
                      <View style={styles.avatar}><Text style={styles.avatarText}>{p.name.slice(0, 1)}</Text></View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.pName}>{p.name}</Text>
                        <Text style={styles.pEmail}>{p.active_orders || 0} active · {p.vehicle}</Text>
                      </View>
                      {assigning.delivery_partner_id === p.partner_id && <Ionicons name="checkmark-circle" size={20} color={colors.primary} />}
                    </TouchableOpacity>
                  ))}
                  {assigning.delivery_partner_id && (
                    <TouchableOpacity style={[styles.pickerRow, { borderColor: colors.danger }]} onPress={() => assignOrder(assigning, null)} testID="unassign-btn">
                      <Ionicons name="close-circle" size={20} color={colors.danger} />
                      <Text style={[styles.pName, { color: colors.danger }]}>Unassign</Text>
                    </TouchableOpacity>
                  )}
                </ScrollView>
              </>
            )}
          </View>
        </View>
      </Modal>
    </AdminShell>
  );
}

function OrderRow({ o, partners, onAssign, setAssigning }: {
  o: Order; partners: Partner[]; onAssign: (partner_id: string) => void; setAssigning: (o: Order) => void;
}) {
  const partner = partners.find(p => p.partner_id === o.delivery_partner_id);
  const customerName = o.customer_name || o.user_summary?.name || o.address?.name || "Guest";
  return (
    <View style={styles.orderRow} testID={`order-row-${o.order_id}`}>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <Ionicons name="person-circle-outline" size={14} color={colors.primary} />
          <Text style={styles.customerName} numberOfLines={1}>{customerName}</Text>
          <Text style={styles.orderIdInline}>· {o.order_id.slice(0, 12)}</Text>
          <Text style={styles.orderIdInline}>· {centsToCAD(o.total_cents)}</Text>
        </View>
        <Text style={styles.orderMeta}>{o.address?.line1 || "—"}, {o.address?.city || ""} · {o.slot?.window || ""}</Text>
        <View style={styles.orderChips}>
          <Chip label={o.status.toUpperCase()} tone={o.status === "delivered" ? "green" : "orange"} />
          {o.delivery_status && <Chip label={o.delivery_status.replace("_", " ").toUpperCase()} tone="blue" />}
          {partner && <Chip label={`→ ${partner.name}`} tone="grey" />}
        </View>
      </View>
      <TouchableOpacity testID={`assign-btn-${o.order_id}`} style={styles.assignBtn} onPress={() => setAssigning(o)}>
        <Ionicons name="git-network-outline" size={14} color="#fff" />
        <Text style={styles.assignBtnText}>{o.delivery_partner_id ? "Reassign" : "Assign"}</Text>
      </TouchableOpacity>
    </View>
  );
}

function Chip({ label, tone }: { label: string; tone: "green" | "orange" | "blue" | "grey" }) {
  const bg = tone === "green" ? "#DCFCE7" : tone === "orange" ? "#FFEDD5" : tone === "blue" ? "#DBEAFE" : "#E5E7EB";
  const fg = tone === "green" ? "#166534" : tone === "orange" ? "#9A3412" : tone === "blue" ? "#1E40AF" : "#374151";
  return (
    <View style={{ backgroundColor: bg, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
      <Text style={{ color: fg, fontSize: 10, fontWeight: "800", letterSpacing: 0.5 }}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tabRow: { flexDirection: "row", gap: 8, marginBottom: spacing.md },
  tab: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  tabActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  tabText: { color: colors.text, fontSize: 13, fontWeight: "700" },
  tabTextActive: { color: "#fff" },

  actionRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  hint: { color: colors.textMuted, fontSize: 12, flex: 1 },
  primaryBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.pill, ...shadows.soft },
  primaryBtnText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  sectionTitle: { fontSize: 14, fontWeight: "800", color: colors.text, marginBottom: spacing.sm },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  pCard: { flexGrow: 1, flexBasis: 320, minWidth: 320, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm, ...shadows.soft },
  pTop: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  avatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  avatarText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  pName: { fontSize: 15, fontWeight: "800", color: colors.text },
  pEmail: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  stateChip: { paddingHorizontal: 6, paddingVertical: 3, borderRadius: 4 },
  stateOn: { backgroundColor: "#DCFCE7" },
  stateOff: { backgroundColor: "#FEE2E2" },
  stateChipText: { fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  pMetaRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  pMeta: { flexDirection: "row", alignItems: "center", gap: 4 },
  pMetaText: { color: colors.textMuted, fontSize: 11, fontWeight: "600" },
  pFoot: { flexDirection: "row", gap: 6, marginTop: 4 },
  iconBtn: { width: 30, height: 30, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },

  assignList: { gap: spacing.sm },
  orderRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  orderId: { fontSize: 13, fontWeight: "800", color: colors.text },
  customerName: { fontSize: 13, fontWeight: "800", color: colors.text, maxWidth: 180 },
  orderIdInline: { fontSize: 11, fontWeight: "700", color: colors.textMuted, letterSpacing: 0.2 },
  orderMeta: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  orderChips: { flexDirection: "row", gap: 6, marginTop: 6, flexWrap: "wrap" },
  assignBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill },
  assignBtnText: { color: "#fff", fontSize: 12, fontWeight: "800" },

  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl, width: "100%" },

  overlay: { flex: 1, backgroundColor: colors.overlay, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modal: { width: "100%", maxWidth: 560, maxHeight: "90%", backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.lg, gap: spacing.sm, ...shadows.card },
  modalHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.text },
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800", marginTop: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14 },
  vehChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  vehChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  vehChipText: { color: colors.text, fontWeight: "700", fontSize: 12, textTransform: "capitalize" },
  helperText: { color: colors.textMuted, fontSize: 12, marginTop: spacing.sm },
  mono: { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", color: colors.primary },
  assignSub: { color: colors.textMuted, fontSize: 12, marginBottom: spacing.sm },
  pickerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pickerRowActive: { borderColor: colors.primary, backgroundColor: "#FFF7F3" },
});
