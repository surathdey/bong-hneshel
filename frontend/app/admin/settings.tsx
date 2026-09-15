import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator, ScrollView, Alert,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import AdminShell from "@/src/components/AdminShell";
import IntegrationsPanel from "@/src/components/IntegrationsPanel";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { buildOperatingHoursLabel } from "@/src/utils/format";

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

type PaymentMethodConfig = {
  enabled: boolean;
  tax_enabled: boolean;
  publishable_key?: string;
  secret_key?: string;
  client_id?: string;
  client_secret?: string;
  email?: string;
  instructions?: string;
};

type Settings = {
  business_name: string; kitchen_address: string; phone: string; email: string;
  operating_hours: string; delivery_areas: string[]; default_delivery_fee_cents: number;
  ordering_days?: number[]; delivery_days?: number[];
  minimum_order_cents: number; tax_enabled: boolean; tax_rate_bps: number; tax_label: string;
  currency: string; company_info: string;
  home_hero_tagline?: string;
  notify_email?: string;
  notify_phone?: string;
  delivery_fee_tiers?: { max_km: number; fee_cents: number }[];
  delivery_fee_over_max_cents?: number;
  payment_methods?: { stripe?: PaymentMethodConfig; paypal?: PaymentMethodConfig; cod?: PaymentMethodConfig; interac?: PaymentMethodConfig; };
};

const DEFAULT_METHODS: NonNullable<Settings["payment_methods"]> = {
  // Stripe disabled for MVP — flip back to `true` when Stripe is re-enabled.
  stripe:  { enabled: true,  tax_enabled: false, publishable_key: "", secret_key: "" },
  paypal:  { enabled: false, tax_enabled: true, client_id: "", client_secret: "" },
  cod:     { enabled: true,  tax_enabled: true },
  interac: { enabled: true,  tax_enabled: true, email: "orders@curryandco.ca", instructions: "Please note your order ID in the message field." },
};

export default function AdminSettings() {
  const router = useRouter();
  const [s, setS] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feeStr, setFeeStr] = useState("");
  const [minStr, setMinStr] = useState("");
  const [rateStr, setRateStr] = useState("");
  const [areas, setAreas] = useState("");
  // Distance-based delivery fee tiers (edited as strings; km + CAD).
  const [tiers, setTiers] = useState<{ kmStr: string; feeStr: string }[]>([]);
  const [overStr, setOverStr] = useState("15.00");

  const load = useCallback(async () => {
    const r = await adminApi.get<Settings>("/admin/settings");
    if (r.status === 401) return router.replace("/admin");
    if (r.ok) {
      // Ensure payment_methods is fully hydrated even if the DB doc is missing fields.
      const pm = r.data.payment_methods || {};
      r.data.payment_methods = {
        stripe:  { ...DEFAULT_METHODS.stripe,  ...(pm.stripe  || {}) },
        paypal:  { ...DEFAULT_METHODS.paypal,  ...(pm.paypal  || {}) },
        cod:     { ...DEFAULT_METHODS.cod,     ...(pm.cod     || {}) },
        interac: { ...DEFAULT_METHODS.interac, ...(pm.interac || {}) },
      };
      // Hydrate schedule defaults (backend used to not have these fields)
      if (!Array.isArray(r.data.ordering_days)) r.data.ordering_days = [0, 1, 2, 3, 4];
      if (!Array.isArray(r.data.delivery_days)) r.data.delivery_days = [5, 6];
      // Keep operating_hours label in sync with the structured fields on load.
      r.data.operating_hours = buildOperatingHoursLabel(r.data.ordering_days, r.data.delivery_days);
      setS(r.data);
      setFeeStr(((r.data.default_delivery_fee_cents ?? 0) / 100).toFixed(2));
      setMinStr(((r.data.minimum_order_cents ?? 0) / 100).toFixed(2));
      setRateStr(((r.data.tax_rate_bps ?? 0) / 100).toFixed(2));
      setAreas((r.data.delivery_areas || []).join(", "));
      const tierList = Array.isArray(r.data.delivery_fee_tiers) && r.data.delivery_fee_tiers.length
        ? r.data.delivery_fee_tiers
        : [{ max_km: 20, fee_cents: 0 }, { max_km: 40, fee_cents: 500 }, { max_km: 75, fee_cents: 1000 }];
      setTiers(tierList.map(t => ({ kmStr: String(t.max_km ?? ""), feeStr: ((t.fee_cents ?? 0) / 100).toFixed(2) })));
      setOverStr(((r.data.delivery_fee_over_max_cents ?? 1500) / 100).toFixed(2));
    }
    setLoading(false);
  }, [router]);

  useEffect(() => { (async () => {
    const t = await getAdminToken(); if (!t) return router.replace("/admin");
    await load();
  })(); }, [router, load]);

  const save = async () => {
    if (!s) return;
    setSaving(true);
    const body: Settings = {
      ...s,
      default_delivery_fee_cents: Math.round((parseFloat(feeStr) || 0) * 100),
      minimum_order_cents: Math.round((parseFloat(minStr) || 0) * 100),
      tax_rate_bps: Math.round((parseFloat(rateStr) || 0) * 100),
      delivery_areas: areas.split(",").map(a => a.trim()).filter(Boolean),
      delivery_fee_tiers: tiers
        .map(t => ({ max_km: parseFloat(t.kmStr) || 0, fee_cents: Math.round((parseFloat(t.feeStr) || 0) * 100) }))
        .filter(t => t.max_km > 0)
        .sort((a, b) => a.max_km - b.max_km),
      delivery_fee_over_max_cents: Math.round((parseFloat(overStr) || 0) * 100),
    };
    const r = await adminApi.put("/admin/settings", body);
    setSaving(false);
    if (r.ok) Alert.alert("Saved", "Settings updated.");
    else Alert.alert("Save failed", r.error);
  };

  if (loading || !s) return <AdminShell title="Settings"><ActivityIndicator color={colors.primary} size="large" /></AdminShell>;

  const pm = s.payment_methods || DEFAULT_METHODS;
  const patchMethod = (key: keyof typeof DEFAULT_METHODS, patch: Partial<PaymentMethodConfig>) => {
    setS({ ...s, payment_methods: { ...(s.payment_methods || DEFAULT_METHODS), [key]: { ...(s.payment_methods || DEFAULT_METHODS)[key], ...patch } } });
  };
  const enabledCount = (["stripe","paypal","cod","interac"] as const).filter(k => pm[k]?.enabled).length;

  return (
    <AdminShell title="Settings">
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Business Information</Text>
        <View style={styles.card}>
          <Field label="Business Name" testID="set-name" value={s.business_name} onChange={t => setS({ ...s, business_name: t })} />
          <Field label="Kitchen Address" testID="set-address" value={s.kitchen_address} onChange={t => setS({ ...s, kitchen_address: t })} multiline />
          <View style={styles.row}>
            <Field label="Phone" value={s.phone} onChange={t => setS({ ...s, phone: t })} keyboardType="phone-pad" />
            <Field label="Email" value={s.email} onChange={t => setS({ ...s, email: t })} keyboardType="email-address" />
          </View>
          <Field label="Operating Hours (auto-generated)" testID="set-hours" value={s.operating_hours} onChange={t => setS({ ...s, operating_hours: t })} />
          <Field
            label="Customer app tagline"
            testID="set-hero-tagline"
            value={s.home_hero_tagline || ""}
            onChange={t => setS({ ...s, home_hero_tagline: t })}
            multiline
            placeholder="e.g. Order anytime this week — we deliver every weekend."
          />
          <Text style={styles.hint}>
            Shown on the customer app home screen right under the brand name. Keep it one sentence — explain when you take orders and when you deliver.
          </Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Ordering & Delivery Schedule</Text>
        <View style={styles.card}>
          <Text style={styles.label}>ORDERING DAYS</Text>
          <Text style={styles.helperText}>Days customers can place new orders. Others show as “closed” in the app.</Text>
          <View style={styles.dayRow}>
            {DAY_LABELS.map((lbl, idx) => {
              const on = (s.ordering_days || []).includes(idx);
              return (
                <TouchableOpacity
                  key={`ord-${idx}`}
                  testID={`set-order-day-${idx}`}
                  onPress={() => {
                    const cur = new Set(s.ordering_days || []);
                    if (on) cur.delete(idx); else cur.add(idx);
                    const nextOrd = Array.from(cur).sort((a, b) => a - b);
                    setS({ ...s, ordering_days: nextOrd, operating_hours: buildOperatingHoursLabel(nextOrd, s.delivery_days || []) });
                  }}
                  style={[styles.dayChip, on && styles.dayChipActive]}
                >
                  <Text style={[styles.dayChipText, on && styles.dayChipTextActive]}>{lbl}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={[styles.label, { marginTop: spacing.md }]}>DELIVERY DAYS</Text>
          <Text style={styles.helperText}>Days when drivers deliver those orders. Shown as available slots at checkout.</Text>
          <View style={styles.dayRow}>
            {DAY_LABELS.map((lbl, idx) => {
              const on = (s.delivery_days || []).includes(idx);
              return (
                <TouchableOpacity
                  key={`del-${idx}`}
                  testID={`set-deliver-day-${idx}`}
                  onPress={() => {
                    const cur = new Set(s.delivery_days || []);
                    if (on) cur.delete(idx); else cur.add(idx);
                    const nextDel = Array.from(cur).sort((a, b) => a - b);
                    setS({ ...s, delivery_days: nextDel, operating_hours: buildOperatingHoursLabel(s.ordering_days || [], nextDel) });
                  }}
                  style={[styles.dayChip, on && styles.dayChipActiveAlt]}
                >
                  <Text style={[styles.dayChipText, on && styles.dayChipTextActive]}>{lbl}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Delivery</Text>
        <View style={styles.card}>
          <Field label="Delivery Areas (comma-separated)" testID="set-areas" value={areas} onChange={setAreas} />
          <View style={styles.row}>
            <Field label={`Fallback Delivery Fee (${s.currency})`} testID="set-fee" value={feeStr} onChange={setFeeStr} keyboardType="decimal-pad" />
            <Field label={`Minimum Order (${s.currency})`} testID="set-min" value={minStr} onChange={setMinStr} keyboardType="decimal-pad" />
          </View>
          <Text style={styles.hint}>Fallback fee is used only if Google Maps is unavailable. Otherwise the distance tiers below apply.</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Distance-based Delivery Fees</Text>
        <View style={styles.card}>
          <Text style={styles.hint}>
            Driving distance is measured from the Kitchen Address (set above). A customer is charged the first tier
            their distance fits within. Enter the upper limit (km) and the fee for each tier.
          </Text>
          <View style={[styles.row, { marginTop: 4 }]}>
            <Text style={[styles.label, { flex: 1 }]}>UP TO (KM)</Text>
            <Text style={[styles.label, { flex: 1 }]}>FEE ({s.currency})</Text>
            <View style={{ width: 36 }} />
          </View>
          {tiers.map((t, i) => (
            <View key={`tier-${i}`} style={styles.row} testID={`tier-row-${i}`}>
              <TextInput testID={`tier-km-${i}`} value={t.kmStr} keyboardType="decimal-pad"
                onChangeText={v => setTiers(prev => prev.map((x, idx) => idx === i ? { ...x, kmStr: v } : x))}
                placeholder="20" placeholderTextColor={colors.textMuted} style={[styles.input, { flex: 1 }]} />
              <TextInput testID={`tier-fee-${i}`} value={t.feeStr} keyboardType="decimal-pad"
                onChangeText={v => setTiers(prev => prev.map((x, idx) => idx === i ? { ...x, feeStr: v } : x))}
                placeholder="0.00" placeholderTextColor={colors.textMuted} style={[styles.input, { flex: 1 }]} />
              <TouchableOpacity testID={`tier-remove-${i}`} onPress={() => setTiers(prev => prev.filter((_, idx) => idx !== i))}
                style={styles.tierRemove}>
                <Ionicons name="trash-outline" size={18} color={colors.danger} />
              </TouchableOpacity>
            </View>
          ))}
          <TouchableOpacity testID="tier-add" onPress={() => setTiers(prev => [...prev, { kmStr: "", feeStr: "0.00" }])} style={styles.tierAdd}>
            <Ionicons name="add" size={16} color={colors.primary} />
            <Text style={styles.tierAddText}>Add tier</Text>
          </TouchableOpacity>
          <View style={{ marginTop: 4 }}>
            <Field label={`Beyond last tier — fee (${s.currency})`} testID="set-over" value={overStr} onChange={setOverStr} keyboardType="decimal-pad" />
            <Text style={styles.hint}>Charged when the distance is greater than the largest tier above.</Text>
          </View>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Owner Notifications</Text>
        <View style={styles.card}>
          <Field label="Owner Email (order & delivery alerts)" testID="set-notify-email"
            value={s.notify_email || ""} onChange={(t: string) => setS({ ...s, notify_email: t })} keyboardType="email-address" placeholder="owner@restaurant.com" />
          <Field label="Owner Phone (SMS alerts — optional)" testID="set-notify-phone"
            value={s.notify_phone || ""} onChange={(t: string) => setS({ ...s, notify_phone: t })} keyboardType="phone-pad" placeholder="+14370000000" />
          <Text style={styles.hint}>A copy of every new order and every completed delivery is sent to the owner email (and SMS if a phone is set).</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Tax Configuration (fallback)</Text>
        <View style={styles.card}>
          <TouchableOpacity
            testID="set-tax-toggle"
            style={[styles.toggleRow, s.tax_enabled && styles.toggleRowActive]}
            onPress={() => setS({ ...s, tax_enabled: !s.tax_enabled })}
          >
            <Ionicons name={s.tax_enabled ? "toggle" : "toggle-outline"} size={30} color={s.tax_enabled ? colors.success : colors.textMuted} />
            <View style={{ flex: 1 }}>
              <Text style={styles.toggleTitle}>Default: charge tax at checkout</Text>
              <Text style={styles.toggleSub}>{"Only used when a payment method doesn't specify its own "}{s.tax_label}{" setting below."}</Text>
            </View>
          </TouchableOpacity>
          <View style={styles.row}>
            <Field label="Tax Label (e.g. HST, GST)" testID="set-tax-label" value={s.tax_label} onChange={t => setS({ ...s, tax_label: t })} />
            <Field label="Tax Rate (%)" testID="set-tax-rate" value={rateStr} onChange={setRateStr} keyboardType="decimal-pad" />
          </View>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Payment Methods · {enabledCount} enabled</Text>

        <PaymentCard
          testIDPrefix="pm-stripe"
          title="Stripe (Card + Google Pay + Apple Pay)"
          icon="card"
          brand="#635BFF"
          desc="Visa/Mastercard/Amex plus Google Pay & Apple Pay. Secret key is set securely on the server."
          cfg={pm.stripe || DEFAULT_METHODS.stripe}
          onPatch={p => patchMethod("stripe", p)}
          taxLabel={s.tax_label}
        />

        <PaymentCard
          testIDPrefix="pm-paypal"
          title="PayPal"
          icon="logo-paypal"
          brand="#0070BA"
          desc="Config-ready — checkout wire-up will happen in a follow-up release."
          cfg={pm.paypal || DEFAULT_METHODS.paypal}
          onPatch={p => patchMethod("paypal", p)}
          taxLabel={s.tax_label}
        >
          <Field label="PayPal Client ID"     testID="pm-paypal-id"     value={pm.paypal?.client_id || ""}     onChange={t => patchMethod("paypal", { client_id: t })} />
          <Field label="PayPal Client Secret" testID="pm-paypal-secret" value={pm.paypal?.client_secret || ""} onChange={t => patchMethod("paypal", { client_secret: t })} secureTextEntry />
        </PaymentCard>

        <PaymentCard
          testIDPrefix="pm-cod"
          title="Cash on Delivery"
          icon="cash"
          brand="#166534"
          desc="Driver collects cash at the door — no extra configuration needed."
          cfg={pm.cod || DEFAULT_METHODS.cod}
          onPatch={p => patchMethod("cod", p)}
          taxLabel={s.tax_label}
        />

        <PaymentCard
          testIDPrefix="pm-interac"
          title="Interac e-Transfer"
          icon="mail"
          brand="#F9B233"
          desc="Customer sees your Interac email at checkout and sends the e-Transfer manually."
          cfg={pm.interac || DEFAULT_METHODS.interac}
          onPatch={p => patchMethod("interac", p)}
          taxLabel={s.tax_label}
        >
          <Field label="Interac e-Transfer Email"    testID="pm-interac-email" value={pm.interac?.email || ""}         onChange={t => patchMethod("interac", { email: t })} keyboardType="email-address" />
          <Field label="Instructions to customer"    testID="pm-interac-note"  value={pm.interac?.instructions || ""}  onChange={t => patchMethod("interac", { instructions: t })} multiline />
        </PaymentCard>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Company Info</Text>
        <View style={styles.card}>
          <Field label="Company / Legal Info (footer)" testID="set-company" value={s.company_info} onChange={t => setS({ ...s, company_info: t })} multiline />
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Integrations · Exports</Text>
        <IntegrationsPanel />
      </View>

      <TouchableOpacity testID="set-save" style={styles.saveBtn} onPress={save} disabled={saving}>
        {saving ? <ActivityIndicator color="#fff" /> : (
          <>
            <Ionicons name="checkmark-circle" size={18} color="#fff" />
            <Text style={styles.saveBtnText}>Save settings</Text>
          </>
        )}
      </TouchableOpacity>
    </AdminShell>
  );
}

function Field({ label, value, onChange, multiline, keyboardType, testID, secureTextEntry, placeholder }: any) {
  return (
    <View style={{ flex: 1, gap: 4 }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput testID={testID} value={value} onChangeText={onChange} multiline={multiline} keyboardType={keyboardType} secureTextEntry={secureTextEntry} placeholder={placeholder} autoCapitalize="none" autoCorrect={false} style={[styles.input, multiline && { minHeight: 60 }]} placeholderTextColor={colors.textMuted} />
    </View>
  );
}

function PaymentCard({ title, icon, brand, desc, cfg, onPatch, taxLabel, testIDPrefix, children }: any) {
  return (
    <View style={[styles.card, { gap: spacing.sm, marginBottom: spacing.sm, borderLeftWidth: 4, borderLeftColor: brand }]}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
        <View style={[styles.brandDot, { backgroundColor: brand }]}>
          <Ionicons name={icon} size={16} color="#fff" />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.pmTitle}>{title}</Text>
          <Text style={styles.pmDesc}>{desc}</Text>
        </View>
      </View>

      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <TouchableOpacity
          testID={`${testIDPrefix}-enabled`}
          style={[styles.toggleRow, { flex: 1 }, cfg.enabled && styles.toggleRowActive]}
          onPress={() => onPatch({ enabled: !cfg.enabled })}
        >
          <Ionicons name={cfg.enabled ? "toggle" : "toggle-outline"} size={26} color={cfg.enabled ? colors.success : colors.textMuted} />
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleTitle}>{cfg.enabled ? "Enabled" : "Disabled"}</Text>
            <Text style={styles.toggleSub}>Show at checkout</Text>
          </View>
        </TouchableOpacity>

        <TouchableOpacity
          testID={`${testIDPrefix}-tax`}
          style={[styles.toggleRow, { flex: 1 }, cfg.tax_enabled && styles.toggleRowActive]}
          onPress={() => onPatch({ tax_enabled: !cfg.tax_enabled })}
        >
          <Ionicons name={cfg.tax_enabled ? "toggle" : "toggle-outline"} size={26} color={cfg.tax_enabled ? colors.success : colors.textMuted} />
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleTitle}>Charge {taxLabel}</Text>
            <Text style={styles.toggleSub}>Add {taxLabel} to this method</Text>
          </View>
        </TouchableOpacity>
      </View>

      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: 6 },
  sectionTitle: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  card: { backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.sm, ...shadows.soft },
  row: { flexDirection: "row", gap: spacing.sm },
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  hint: { color: colors.textMuted, fontSize: 11, lineHeight: 15, marginTop: -2, fontStyle: "italic" },
  input: { backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14 },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  toggleRowActive: { backgroundColor: "#DCFCE7", borderColor: "#BBF7D0" },
  toggleTitle: { color: colors.text, fontWeight: "800", fontSize: 14 },
  toggleSub: { color: colors.textMuted, fontSize: 12 },
  brandDot: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  pmTitle: { color: colors.text, fontWeight: "800", fontSize: 14 },
  pmDesc: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  saveBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.primary, paddingVertical: 16, borderRadius: radius.pill, ...shadows.card, alignSelf: "center", paddingHorizontal: 40 },
  saveBtnText: { color: "#fff", fontWeight: "800", fontSize: 15 },
  helperText: { color: colors.textMuted, fontSize: 12, marginTop: -2, marginBottom: 4 },
  dayRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  dayChip: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border, minWidth: 54, alignItems: "center" },
  dayChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  dayChipActiveAlt: { backgroundColor: colors.success, borderColor: colors.success },
  dayChipText: { color: colors.text, fontWeight: "700", fontSize: 13 },
  dayChipTextActive: { color: "#fff" },
  tierRemove: { width: 36, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignSelf: "flex-end" },
  tierAdd: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", paddingVertical: 8, paddingHorizontal: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.primary },
  tierAddText: { color: colors.primary, fontWeight: "800", fontSize: 13 },
});
