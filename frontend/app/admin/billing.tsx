/**
 * Admin Billing tab — Phase 3.
 *
 * Talks to /api/admin/billing/* which itself proxies to the central Suparna
 * Dey Platform (the hub owns Stripe). Handles four visible states:
 *
 *   1. `unconfigured`  – tenant not wired to the platform yet
 *   2. `not_implemented` – hub reachable but hasn't shipped billing endpoints
 *   3. `unreachable`   – hub is down / DNS / network
 *   4. Real states from Stripe: `none`, `trialing`, `active`, `past_due`,
 *                              `canceled`, `unpaid`, `incomplete`
 *
 * The Subscribe CTA and Manage-Billing button open Stripe-hosted URLs. On
 * return to this tab we force-refresh the summary (`?force=true`) so a
 * fresh subscription state shows up immediately without waiting on the
 * 5-min phone-home cycle.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ActivityIndicator, TouchableOpacity,
  ScrollView, Linking, Platform, RefreshControl, useWindowDimensions,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { BRAND } from "@/src/brand";

// ─── Types (mirrors backend billing_client.py) ──────────────────────────
type Invoice = {
  id: string;
  number?: string | null;
  amount_cents: number;
  currency: string;
  status: string;
  created_at?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  hosted_invoice_url?: string | null;
  invoice_pdf?: string | null;
};

type Plan = {
  id?: string;
  name?: string;
  price_cents?: number;
  currency?: string;
  interval?: "month" | "year" | string;
};

type Card = { brand?: string; last4?: string; exp_month?: number; exp_year?: number };

type BillingSummary = {
  status: string;                 // 'unconfigured' | 'not_implemented' | 'unreachable'
                                  // | 'none' | 'trialing' | 'active' | 'past_due' | 'canceled' | 'unpaid'
  message?: string;
  plan?: Plan | null;
  card?: Card | null;
  invoices?: Invoice[];
  current_period_end?: string | null;   // ISO
  trial_end?: string | null;             // ISO
  cancel_at_period_end?: boolean;
};

// ─── Small utils ────────────────────────────────────────────────────────
const money = (cents?: number, currency: string = "USD") => {
  if (cents == null) return "—";
  const s = (cents / 100).toFixed(2);
  return currency === "CAD" ? `CA$${s}` : currency === "USD" ? `$${s}` : `${currency} ${s}`;
};

const fmtDate = (iso?: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

const STATUS_COPY: Record<string, { label: string; color: string; hint: string }> = {
  active:     { label: "ACTIVE",     color: colors.success, hint: "Your platform subscription is in good standing." },
  trialing:   { label: "TRIAL",      color: "#0ea5e9",      hint: "Enjoy your free trial. Add a card to keep the app running after it ends." },
  past_due:   { label: "PAST DUE",   color: "#B45309",      hint: "Your last payment failed. Update your card to restore ordering." },
  unpaid:     { label: "UNPAID",     color: colors.danger,  hint: "The subscription is unpaid. Customer checkout is blocked." },
  canceled:   { label: "CANCELED",   color: colors.danger,  hint: "You cancelled the subscription. Resubscribe to reactivate." },
  incomplete: { label: "INCOMPLETE", color: "#B45309",      hint: "Payment setup is not finished. Complete checkout to activate." },
  none:       { label: "NOT SUBSCRIBED", color: colors.textMuted, hint: "Subscribe to enable customer checkout and driver logins." },
};

export default function AdminBilling() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const wide = width > 900;

  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [loading, setLoading]  = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [acting, setActing] = useState<"subscribe" | "portal" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (force = false) => {
    setError(null);
    const r = await adminApi.get<BillingSummary>(`/admin/billing/summary${force ? "?force=true" : ""}`);
    if (r.ok) setSummary(r.data);
    else if (r.status === 401) router.replace("/admin");
    else setError(r.error || "Could not load billing.");
  }, [router]);

  useEffect(() => {
    (async () => {
      const tok = await getAdminToken();
      if (!tok) { router.replace("/admin"); return; }
      await load(false);
      setLoading(false);
    })();
  }, [router, load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  }, [load]);

  const openUrl = async (url: string) => {
    if (Platform.OS === "web") {
      // Open in a NEW TAB so returning shows this admin page in the same window.
      (globalThis as any).window?.open?.(url, "_blank", "noopener,noreferrer");
    } else {
      await Linking.openURL(url);
    }
  };

  const currentPageUrl = () => {
    if (Platform.OS === "web") {
      return (globalThis as any).location?.href || "";
    }
    return `${BRAND.native?.customer?.deepLinkScheme || "curryandco"}://admin/billing`;
  };

  const handleSubscribe = async () => {
    setActing("subscribe");
    const returnHere = currentPageUrl();
    const r = await adminApi.post<{ url?: string; error?: string; message?: string }>(
      "/admin/billing/subscribe",
      { success_url: returnHere + (returnHere.includes("?") ? "&" : "?") + "billing=success",
        cancel_url:  returnHere + (returnHere.includes("?") ? "&" : "?") + "billing=cancel" },
    );
    setActing(null);
    if (r.ok && r.data?.url) await openUrl(r.data.url);
    else setError(r.ok ? (r.data?.message || "No checkout URL returned.") : (r.error || "Failed to start checkout."));
  };

  const handleManage = async () => {
    setActing("portal");
    const r = await adminApi.post<{ url?: string; error?: string; message?: string }>(
      "/admin/billing/portal",
      { return_url: currentPageUrl() },
    );
    setActing(null);
    if (r.ok && r.data?.url) await openUrl(r.data.url);
    else setError(r.ok ? (r.data?.message || "No portal URL returned.") : (r.error || "Failed to open billing portal."));
  };

  const statusMeta = useMemo(() => {
    if (!summary) return null;
    return STATUS_COPY[summary.status] || null;
  }, [summary]);

  const hasSubscription = summary && ["active", "trialing", "past_due", "unpaid", "canceled", "incomplete"].includes(summary.status);
  const canManage       = summary && ["active", "trialing", "past_due", "unpaid", "canceled"].includes(summary.status);

  return (
    <AdminShell title="Billing">
      <ScrollView
        contentContainerStyle={{ gap: spacing.lg, paddingBottom: spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        testID="admin-billing-scroll"
      >
        {loading ? (
          <View style={{ padding: spacing.xxl, alignItems: "center" }}>
            <ActivityIndicator color={colors.primary} size="large" />
          </View>
        ) : !summary ? (
          <EmptyMessage
            icon="cloud-offline-outline"
            title="Couldn't load billing"
            body={error || "Please try again in a moment."}
            actionLabel="Retry"
            onAction={() => { setLoading(true); load(true).finally(() => setLoading(false)); }}
          />
        ) : summary.status === "unconfigured" ? (
          <EmptyMessage
            icon="link-outline"
            title="Not connected to a platform"
            body={summary.message || "Set platform.tenant_id and platform.api_key in brand.json to enable billing."}
          />
        ) : summary.status === "unreachable" ? (
          <EmptyMessage
            icon="wifi-outline"
            title="Platform unreachable"
            body={summary.message || "Could not reach the Suparna Dey Platform."}
            actionLabel="Try again"
            onAction={onRefresh}
          />
        ) : summary.status === "not_implemented" ? (
          <EmptyMessage
            icon="construct-outline"
            title="Billing is coming soon"
            body="The Suparna Dey Platform hasn't enabled billing yet. Once it's live, you'll be able to subscribe and manage your card right here."
          />
        ) : (
          <>
            {/* ── Plan card ────────────────────────────────────────── */}
            <View style={[styles.card, wide && { flexDirection: "row", alignItems: "stretch" }]} testID="billing-plan-card">
              <View style={{ flex: 1, gap: spacing.sm }}>
                <View style={styles.row}>
                  {statusMeta && (
                    <View style={[styles.badge, { backgroundColor: statusMeta.color + "22", borderColor: statusMeta.color }]}>
                      <Text style={[styles.badgeText, { color: statusMeta.color }]}>{statusMeta.label}</Text>
                    </View>
                  )}
                  {summary.cancel_at_period_end && (
                    <View style={[styles.badge, { backgroundColor: "#FEE2E2", borderColor: colors.danger }]}>
                      <Text style={[styles.badgeText, { color: colors.danger }]}>ENDS AT PERIOD END</Text>
                    </View>
                  )}
                </View>

                <Text style={styles.planName} testID="billing-plan-name">
                  {summary.plan?.name || (hasSubscription ? "Platform Plan" : "No active plan")}
                </Text>

                {summary.plan?.price_cents != null && (
                  <Text style={styles.planPrice}>
                    {money(summary.plan.price_cents, summary.plan.currency || "USD")}
                    <Text style={styles.planPriceSuffix}> / {summary.plan.interval || "month"}</Text>
                  </Text>
                )}

                {statusMeta && (
                  <Text style={styles.planHint}>{summary.message || statusMeta.hint}</Text>
                )}

                <View style={styles.metaRow}>
                  {summary.status === "trialing" && summary.trial_end && (
                    <MetaItem icon="hourglass-outline" label="Trial ends" value={fmtDate(summary.trial_end)} />
                  )}
                  {summary.current_period_end && summary.status !== "canceled" && (
                    <MetaItem
                      icon="calendar-outline"
                      label={summary.cancel_at_period_end ? "Access ends" : "Next billing"}
                      value={fmtDate(summary.current_period_end)}
                    />
                  )}
                  {summary.card?.last4 && (
                    <MetaItem
                      icon="card-outline"
                      label="Card on file"
                      value={`${(summary.card.brand || "card").toUpperCase()} •••• ${summary.card.last4}`}
                    />
                  )}
                </View>
              </View>

              <View style={[styles.actions, wide && { justifyContent: "flex-end", marginLeft: spacing.lg }]}>
                {!hasSubscription && (
                  <PrimaryBtn testID="billing-subscribe" onPress={handleSubscribe} loading={acting === "subscribe"} label="Subscribe" icon="rocket-outline" />
                )}
                {canManage && (
                  <PrimaryBtn testID="billing-portal" onPress={handleManage} loading={acting === "portal"} label="Manage billing" icon="settings-outline" />
                )}
                <SecondaryBtn onPress={onRefresh} label="Refresh" icon="refresh-outline" />
              </View>
            </View>

            {/* ── Error surface for action failures ─────────────────── */}
            {error && (
              <View style={styles.errorBox} testID="billing-error">
                <Ionicons name="alert-circle" size={18} color={colors.danger} />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            )}

            {/* ── Invoices ─────────────────────────────────────────── */}
            <View style={styles.card} testID="billing-invoices-card">
              <Text style={styles.sectionTitle}>Invoice history</Text>
              {(!summary.invoices || summary.invoices.length === 0) ? (
                <Text style={styles.emptyText}>No invoices yet.</Text>
              ) : (
                <View style={{ gap: 4 }}>
                  <View style={[styles.invoiceRow, styles.invoiceHead]}>
                    <Text style={[styles.invCol, styles.invColDate, styles.invHeadText]}>Date</Text>
                    <Text style={[styles.invCol, styles.invColNum,  styles.invHeadText]}>Invoice</Text>
                    <Text style={[styles.invCol, styles.invColAmt,  styles.invHeadText]}>Amount</Text>
                    <Text style={[styles.invCol, styles.invColSt,   styles.invHeadText]}>Status</Text>
                    <Text style={[styles.invCol, styles.invColLink, styles.invHeadText]}> </Text>
                  </View>
                  {summary.invoices.map((inv) => (
                    <View key={inv.id} style={styles.invoiceRow} testID={`billing-invoice-${inv.id}`}>
                      <Text style={[styles.invCol, styles.invColDate]}>{fmtDate(inv.created_at)}</Text>
                      <Text style={[styles.invCol, styles.invColNum]} numberOfLines={1}>{inv.number || inv.id.slice(0, 12)}</Text>
                      <Text style={[styles.invCol, styles.invColAmt]}>{money(inv.amount_cents, inv.currency || "USD")}</Text>
                      <View style={[styles.invCol, styles.invColSt]}>
                        <View style={[styles.invStatus, { backgroundColor: (inv.status === "paid" ? colors.success : "#B45309") + "22" }]}>
                          <Text style={{ color: inv.status === "paid" ? colors.success : "#B45309", fontSize: 11, fontWeight: "800" }}>{(inv.status || "").toUpperCase()}</Text>
                        </View>
                      </View>
                      <View style={[styles.invCol, styles.invColLink]}>
                        {inv.hosted_invoice_url ? (
                          <TouchableOpacity onPress={() => openUrl(inv.hosted_invoice_url!)}>
                            <Text style={styles.invLink}>View</Text>
                          </TouchableOpacity>
                        ) : null}
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </View>

            {/* ── Footer help ──────────────────────────────────────── */}
            <View style={styles.helpBox}>
              <Ionicons name="information-circle-outline" size={18} color={colors.textMuted} />
              <Text style={styles.helpText}>
                Billing is managed by the Suparna Dey Platform. Card details are stored securely with Stripe — we never see them.
                {"\n"}Need help? Email <Text style={{ fontWeight: "700", color: colors.text }}>billing@suparnadey.com</Text>.
              </Text>
            </View>
          </>
        )}
      </ScrollView>
    </AdminShell>
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────
function MetaItem({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <View style={styles.metaItem}>
      <Ionicons name={icon} size={14} color={colors.textMuted} />
      <Text style={styles.metaLabel}>{label}</Text>
      <Text style={styles.metaValue}>{value}</Text>
    </View>
  );
}

function PrimaryBtn({ label, icon, onPress, loading, testID }: any) {
  return (
    <TouchableOpacity testID={testID} onPress={onPress} disabled={loading} style={[styles.btn, styles.btnPrimary, loading && { opacity: 0.6 }]}>
      {loading ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name={icon} size={16} color="#fff" />}
      <Text style={styles.btnPrimaryText}>{label}</Text>
    </TouchableOpacity>
  );
}

function SecondaryBtn({ label, icon, onPress }: any) {
  return (
    <TouchableOpacity onPress={onPress} style={[styles.btn, styles.btnGhost]}>
      <Ionicons name={icon} size={16} color={colors.text} />
      <Text style={styles.btnGhostText}>{label}</Text>
    </TouchableOpacity>
  );
}

function EmptyMessage({ icon, title, body, actionLabel, onAction }: any) {
  return (
    <View style={[styles.card, { alignItems: "center", padding: spacing.xxl, gap: spacing.md }]}>
      <View style={styles.emptyIcon}><Ionicons name={icon} size={28} color={colors.primary} /></View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyBody}>{body}</Text>
      {actionLabel && onAction && (
        <TouchableOpacity onPress={onAction} style={[styles.btn, styles.btnPrimary, { marginTop: spacing.sm }]}>
          <Text style={styles.btnPrimaryText}>{actionLabel}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

// ─── Styles ─────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border, padding: spacing.lg,
    ...shadows.soft, gap: spacing.md,
  },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center" },

  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1 },
  badgeText: { fontSize: 11, fontWeight: "800", letterSpacing: 1 },

  planName: { fontSize: 22, fontWeight: "800", color: colors.text, letterSpacing: -0.3 },
  planPrice: { fontSize: 28, fontWeight: "800", color: colors.primary, letterSpacing: -0.5 },
  planPriceSuffix: { fontSize: 14, fontWeight: "600", color: colors.textMuted },
  planHint: { fontSize: 13, color: colors.textMuted, lineHeight: 19 },

  metaRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg, marginTop: spacing.sm },
  metaItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  metaLabel: { fontSize: 12, color: colors.textMuted, fontWeight: "600" },
  metaValue: { fontSize: 12, color: colors.text, fontWeight: "700" },

  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md, alignItems: "center" },

  btn: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.md, minHeight: 44 },
  btnPrimary: { backgroundColor: colors.primary },
  btnPrimaryText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  btnGhost: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.border },
  btnGhostText: { color: colors.text, fontWeight: "700", fontSize: 13 },

  sectionTitle: { fontSize: 14, fontWeight: "800", color: colors.text, letterSpacing: 0.3, marginBottom: spacing.sm },
  emptyText: { color: colors.textMuted, fontSize: 13 },

  invoiceRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.border, gap: spacing.md },
  invoiceHead: { borderTopWidth: 0, paddingBottom: 6 },
  invHeadText: { color: colors.textMuted, fontSize: 11, fontWeight: "800", letterSpacing: 1 },
  invCol: { fontSize: 13, color: colors.text },
  invColDate: { flexBasis: 110, flexShrink: 0 },
  invColNum:  { flex: 1, minWidth: 120 },
  invColAmt:  { flexBasis: 90, textAlign: "right" },
  invColSt:   { flexBasis: 110, alignItems: "flex-start" },
  invColLink: { flexBasis: 60, alignItems: "flex-end" },
  invStatus: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill },
  invLink: { color: colors.primary, fontWeight: "700", fontSize: 13 },

  errorBox: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: "#FEE2E2", borderColor: colors.danger, borderWidth: 1,
    padding: spacing.md, borderRadius: radius.md,
  },
  errorText: { color: colors.danger, fontSize: 13, flex: 1 },

  helpBox: { flexDirection: "row", gap: spacing.sm, padding: spacing.md, backgroundColor: "#F5F5F5", borderRadius: radius.md },
  helpText: { color: colors.textMuted, fontSize: 12, lineHeight: 18, flex: 1 },

  emptyIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.primary + "18", alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontSize: 18, fontWeight: "800", color: colors.text, textAlign: "center" },
  emptyBody: { fontSize: 14, color: colors.textMuted, textAlign: "center", lineHeight: 20, maxWidth: 460 },
});
