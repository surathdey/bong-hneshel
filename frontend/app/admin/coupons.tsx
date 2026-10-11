import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator, ScrollView, Alert, Modal, Platform,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";

type Coupon = {
  code: string;
  discount_type: "percent" | "fixed";
  value: number;
  active: boolean;
  min_order_cents: number;
  description: string;
  first_time_only: boolean;
};

type FormState = {
  origCode: string | null; // null => creating new
  code: string;
  discount_type: "percent" | "fixed";
  valueStr: string; // percent number OR dollars for fixed
  minStr: string; // dollars
  description: string;
  active: boolean;
  first_time_only: boolean;
};

const blankForm: FormState = {
  origCode: null, code: "", discount_type: "percent", valueStr: "10",
  minStr: "0.00", description: "", active: true, first_time_only: false,
};

export default function AdminCoupons() {
  const router = useRouter();
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [redeem, setRedeem] = useState<{ code: string; loading: boolean; data: any | null } | null>(null);

  const openRedemptions = async (c: Coupon) => {
    setRedeem({ code: c.code, loading: true, data: null });
    const r = await adminApi.get<any>(`/admin/coupons/${encodeURIComponent(c.code)}/redemptions`);
    setRedeem({ code: c.code, loading: false, data: r.ok ? r.data : { redemptions: [], count: 0, error: r.error } });
  };

  const load = useCallback(async () => {
    const r = await adminApi.get<{ coupons: Coupon[] }>("/admin/coupons");
    if (!r.ok) {
      if (r.status === 401) return router.replace("/admin");
      setLoading(false);
      return;
    }
    setCoupons(r.data.coupons || []);
    setLoading(false);
  }, [router]);

  useEffect(() => { (async () => {
    const t = await getAdminToken(); if (!t) return router.replace("/admin");
    await load();
  })(); }, [router, load]);

  const openNew = () => setForm({ ...blankForm });
  const openEdit = (c: Coupon) => setForm({
    origCode: c.code,
    code: c.code,
    discount_type: c.discount_type,
    valueStr: c.discount_type === "percent" ? String(c.value) : (c.value / 100).toFixed(2),
    minStr: ((c.min_order_cents || 0) / 100).toFixed(2),
    description: c.description || "",
    active: c.active,
    first_time_only: c.first_time_only,
  });

  const save = async () => {
    if (!form) return;
    const code = form.code.trim().toUpperCase();
    if (!code) return Alert.alert("Missing code", "Enter a coupon code (e.g. FIRST10).");
    let value: number;
    if (form.discount_type === "percent") {
      value = Math.round(parseFloat(form.valueStr) || 0);
      if (value < 1 || value > 100) return Alert.alert("Invalid discount", "Percentage must be between 1 and 100.");
    } else {
      value = Math.round((parseFloat(form.valueStr) || 0) * 100);
      if (value < 1) return Alert.alert("Invalid discount", "Fixed amount must be at least $0.01.");
    }
    const body = {
      code,
      discount_type: form.discount_type,
      value,
      active: form.active,
      min_order_cents: Math.round((parseFloat(form.minStr) || 0) * 100),
      description: form.description.trim(),
      first_time_only: form.first_time_only,
    };
    setSaving(true);
    const r = form.origCode
      ? await adminApi.put(`/admin/coupons/${encodeURIComponent(form.origCode)}`, body)
      : await adminApi.post("/admin/coupons", body);
    setSaving(false);
    if (!r.ok) return Alert.alert("Save failed", r.error);
    setForm(null);
    await load();
  };

  const confirmDelete = (c: Coupon) => {
    const doDelete = async () => {
      const r = await adminApi.del(`/admin/coupons/${encodeURIComponent(c.code)}`);
      if (!r.ok) return Alert.alert("Delete failed", r.error);
      await load();
    };
    if (Platform.OS === "web") {
      if (typeof window !== "undefined" && window.confirm(`Delete coupon "${c.code}"? This cannot be undone.`)) doDelete();
      return;
    }
    Alert.alert("Delete coupon", `Delete "${c.code}"? This cannot be undone.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: doDelete },
    ]);
  };

  const toggleActive = async (c: Coupon) => {
    const r = await adminApi.put(`/admin/coupons/${encodeURIComponent(c.code)}`, { ...c, active: !c.active });
    if (!r.ok) return Alert.alert("Update failed", r.error);
    await load();
  };

  const discountLabel = (c: Coupon) =>
    c.discount_type === "percent" ? `${c.value}% off` : `$${(c.value / 100).toFixed(2)} off`;

  if (loading) return <AdminShell title="Coupons"><ActivityIndicator color={colors.primary} size="large" /></AdminShell>;

  return (
    <AdminShell title="Coupons">
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
        <Text style={styles.sectionTitle}>{coupons.length} COUPON{coupons.length === 1 ? "" : "S"}</Text>
        <TouchableOpacity testID="coupon-add" onPress={openNew} style={styles.addBtn}>
          <Ionicons name="add" size={18} color="#fff" />
          <Text style={styles.addBtnText}>New coupon</Text>
        </TouchableOpacity>
      </View>

      {coupons.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="pricetags-outline" size={40} color={colors.textMuted} />
          <Text style={styles.emptyText}>No coupons yet. Tap “New coupon” to create one.</Text>
        </View>
      ) : (
        <View style={{ gap: spacing.sm }}>
          {coupons.map((c) => (
            <View key={c.code} style={[styles.card, !c.active && { opacity: 0.7 }]}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                <View style={styles.codePill}>
                  <Text style={styles.codeText}>{c.code}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.discount}>{discountLabel(c)}</Text>
                  {!!c.description && <Text style={styles.desc} numberOfLines={2}>{c.description}</Text>}
                </View>
                <TouchableOpacity testID={`coupon-toggle-${c.code}`} onPress={() => toggleActive(c)}>
                  <Ionicons name={c.active ? "toggle" : "toggle-outline"} size={30} color={c.active ? colors.success : colors.textMuted} />
                </TouchableOpacity>
              </View>

              <View style={styles.badgeRow}>
                <View style={[styles.badge, c.active ? styles.badgeOn : styles.badgeOff]}>
                  <Text style={[styles.badgeText, { color: c.active ? colors.success : colors.textMuted }]}>
                    {c.active ? "Active" : "Inactive"}
                  </Text>
                </View>
                {c.first_time_only && (
                  <View style={[styles.badge, styles.badgeFirst]}>
                    <Ionicons name="sparkles-outline" size={12} color={colors.primary} />
                    <Text style={[styles.badgeText, { color: colors.primary }]}>First order only</Text>
                  </View>
                )}
                {c.min_order_cents > 0 && (
                  <View style={[styles.badge, styles.badgeMin]}>
                    <Text style={[styles.badgeText, { color: colors.text }]}>Min ${(c.min_order_cents / 100).toFixed(2)}</Text>
                  </View>
                )}
              </View>

              <View style={styles.actionRow}>
                <TouchableOpacity testID={`coupon-edit-${c.code}`} onPress={() => openEdit(c)} style={styles.actionBtn}>
                  <Ionicons name="create-outline" size={16} color={colors.text} />
                  <Text style={styles.actionText}>Edit</Text>
                </TouchableOpacity>
                <TouchableOpacity testID={`coupon-redemptions-${c.code}`} onPress={() => openRedemptions(c)} style={styles.actionBtn}>
                  <Ionicons name="people-outline" size={16} color={colors.text} />
                  <Text style={styles.actionText}>Redemptions</Text>
                </TouchableOpacity>
                <TouchableOpacity testID={`coupon-delete-${c.code}`} onPress={() => confirmDelete(c)} style={[styles.actionBtn, styles.deleteBtn]}>
                  <Ionicons name="trash-outline" size={16} color={colors.danger} />
                  <Text style={[styles.actionText, { color: colors.danger }]}>Delete</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Editor modal */}
      <Modal visible={!!form} transparent animationType="fade" onRequestClose={() => setForm(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{form?.origCode ? "Edit coupon" : "New coupon"}</Text>
              <TouchableOpacity testID="coupon-close" onPress={() => setForm(null)}>
                <Ionicons name="close" size={24} color={colors.textMuted} />
              </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.sm }} showsVerticalScrollIndicator={false}>
              {form && (
                <>
                  <Field label="COUPON CODE" testID="coupon-code" value={form.code}
                    onChange={(t: string) => setForm({ ...form, code: t.toUpperCase() })} placeholder="FIRST10" />

                  <View style={{ gap: 4 }}>
                    <Text style={styles.label}>DISCOUNT TYPE</Text>
                    <View style={{ flexDirection: "row", gap: spacing.sm }}>
                      {(["percent", "fixed"] as const).map((t) => (
                        <TouchableOpacity key={t} testID={`coupon-type-${t}`}
                          onPress={() => setForm({ ...form, discount_type: t })}
                          style={[styles.typeChip, form.discount_type === t && styles.typeChipActive]}>
                          <Ionicons name={t === "percent" ? "pricetag-outline" : "cash-outline"} size={16}
                            color={form.discount_type === t ? "#fff" : colors.text} />
                          <Text style={[styles.typeChipText, form.discount_type === t && { color: "#fff" }]}>
                            {t === "percent" ? "Percentage" : "Fixed amount"}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>

                  <Field
                    label={form.discount_type === "percent" ? "DISCOUNT (%)" : "DISCOUNT AMOUNT ($)"}
                    testID="coupon-value" value={form.valueStr} keyboardType="decimal-pad"
                    onChange={(t: string) => setForm({ ...form, valueStr: t })}
                    placeholder={form.discount_type === "percent" ? "10" : "5.00"} />

                  <Field label="MIN ORDER ($)" testID="coupon-min" value={form.minStr} keyboardType="decimal-pad"
                    onChange={(t: string) => setForm({ ...form, minStr: t })} placeholder="0.00" />

                  <Field label="DESCRIPTION" testID="coupon-desc" value={form.description} multiline
                    onChange={(t: string) => setForm({ ...form, description: t })}
                    placeholder="10% off your first order from the app" />

                  <TouchableOpacity testID="coupon-active" style={[styles.toggleRow, form.active && styles.toggleRowActive]}
                    onPress={() => setForm({ ...form, active: !form.active })}>
                    <Ionicons name={form.active ? "toggle" : "toggle-outline"} size={26} color={form.active ? colors.success : colors.textMuted} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.toggleTitle}>{form.active ? "Active" : "Inactive"}</Text>
                      <Text style={styles.toggleSub}>Customers can redeem this coupon</Text>
                    </View>
                  </TouchableOpacity>

                  <TouchableOpacity testID="coupon-first" style={[styles.toggleRow, form.first_time_only && styles.toggleRowActive]}
                    onPress={() => setForm({ ...form, first_time_only: !form.first_time_only })}>
                    <Ionicons name={form.first_time_only ? "toggle" : "toggle-outline"} size={26} color={form.first_time_only ? colors.success : colors.textMuted} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.toggleTitle}>First order only</Text>
                      <Text style={styles.toggleSub}>Auto-applies for logged-in first-time customers</Text>
                    </View>
                  </TouchableOpacity>
                </>
              )}
            </ScrollView>

            <TouchableOpacity testID="coupon-save" onPress={save} disabled={saving} style={styles.saveBtn}>
              {saving ? <ActivityIndicator color="#fff" /> : (
                <>
                  <Ionicons name="checkmark" size={18} color="#fff" />
                  <Text style={styles.saveBtnText}>{form?.origCode ? "Save changes" : "Create coupon"}</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Redemptions modal */}
      <Modal visible={!!redeem} transparent animationType="fade" onRequestClose={() => setRedeem(null)}>
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Redemptions · {redeem?.code}</Text>
              <TouchableOpacity testID="coupon-redemptions-close" onPress={() => setRedeem(null)}>
                <Ionicons name="close" size={24} color={colors.textMuted} />
              </TouchableOpacity>
            </View>

            {redeem?.loading ? (
              <ActivityIndicator color={colors.primary} style={{ paddingVertical: spacing.xl }} />
            ) : (
              <>
                <View style={styles.redeemStats}>
                  <Text style={styles.redeemStat}>{redeem?.data?.count ?? 0} redemption{(redeem?.data?.count === 1) ? "" : "s"}</Text>
                  <Text style={styles.redeemStatDot}>·</Text>
                  <Text style={styles.redeemStat}>{redeem?.data?.unique_customers ?? 0} customer{(redeem?.data?.unique_customers === 1) ? "" : "s"}</Text>
                  <Text style={styles.redeemStatDot}>·</Text>
                  <Text style={styles.redeemStat}>${(((redeem?.data?.total_discount_cents ?? 0)) / 100).toFixed(2)} given</Text>
                </View>
                <ScrollView style={{ maxHeight: 360 }} showsVerticalScrollIndicator={false}>
                  {(redeem?.data?.redemptions?.length ?? 0) === 0 ? (
                    <View style={styles.empty}>
                      <Ionicons name="people-outline" size={34} color={colors.textMuted} />
                      <Text style={styles.emptyText}>No one has redeemed this coupon yet.</Text>
                    </View>
                  ) : (
                    redeem!.data.redemptions.map((r: any, i: number) => (
                      <View key={r.order_id || i} style={styles.redeemRow} testID={`redemption-row-${i}`}>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.redeemName}>{r.name}</Text>
                          <Text style={styles.redeemSub}>{r.email || r.phone || "—"}</Text>
                          <Text style={styles.redeemMeta}>
                            {r.order_id} · {r.created_at ? new Date(r.created_at).toLocaleDateString() : ""} · {r.status}
                          </Text>
                        </View>
                        <View style={{ alignItems: "flex-end" }}>
                          <Text style={styles.redeemSaved}>-${(r.discount_cents / 100).toFixed(2)}</Text>
                          <Text style={styles.redeemSub}>${(r.total_cents / 100).toFixed(2)} total</Text>
                        </View>
                      </View>
                    ))
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

function Field({ label, value, onChange, multiline, keyboardType, testID, placeholder }: any) {
  return (
    <View style={{ flex: 1, gap: 4 }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput testID={testID} value={value} onChangeText={onChange} multiline={multiline} keyboardType={keyboardType}
        placeholder={placeholder} autoCapitalize="none" autoCorrect={false}
        style={[styles.input, multiline && { minHeight: 60 }]} placeholderTextColor={colors.textMuted} />
    </View>
  );
}

const styles = StyleSheet.create({
  sectionTitle: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill, ...shadows.soft },
  addBtnText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  empty: { alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.xl * 2 },
  emptyText: { color: colors.textMuted, fontSize: 14, textAlign: "center" },
  card: { backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.sm, ...shadows.soft },
  codePill: { backgroundColor: colors.accent, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.md },
  codeText: { color: "#fff", fontWeight: "800", fontSize: 14, letterSpacing: 1 },
  discount: { color: colors.text, fontWeight: "800", fontSize: 15 },
  desc: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, borderWidth: 1 },
  badgeOn: { backgroundColor: "#DCFCE7", borderColor: "#BBF7D0" },
  badgeOff: { backgroundColor: colors.surfaceAlt, borderColor: colors.border },
  badgeFirst: { backgroundColor: colors.surfaceAlt, borderColor: colors.primary },
  badgeMin: { backgroundColor: colors.surfaceAlt, borderColor: colors.border },
  badgeText: { fontSize: 11, fontWeight: "800" },
  actionRow: { flexDirection: "row", gap: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm },
  actionBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  deleteBtn: { borderColor: "#FECACA", backgroundColor: "#FEF2F2" },
  actionText: { color: colors.text, fontWeight: "700", fontSize: 13 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 480, maxHeight: "88%", backgroundColor: colors.background, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, ...shadows.card },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.text },
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14 },
  typeChip: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  typeChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  typeChipText: { color: colors.text, fontWeight: "700", fontSize: 13 },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  toggleRowActive: { backgroundColor: "#DCFCE7", borderColor: "#BBF7D0" },
  toggleTitle: { color: colors.text, fontWeight: "800", fontSize: 14 },
  toggleSub: { color: colors.textMuted, fontSize: 12 },
  saveBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.primary, paddingVertical: 15, borderRadius: radius.pill, ...shadows.card },
  saveBtnText: { color: "#fff", fontWeight: "800", fontSize: 15 },
  redeemStats: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  redeemStat: { color: colors.text, fontWeight: "800", fontSize: 12 },
  redeemStatDot: { color: colors.textMuted },
  redeemRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  redeemName: { color: colors.text, fontWeight: "800", fontSize: 14 },
  redeemSub: { color: colors.textMuted, fontSize: 12 },
  redeemMeta: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  redeemSaved: { color: colors.success, fontWeight: "800", fontSize: 14 },
});
