import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";

type Stats = { total_orders: number; delivered: number; active: number; users: number; revenue_cents: number; };

export default function AdminDashboard() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const tok = await getAdminToken();
      if (!tok) { router.replace("/admin"); return; }
      const r = await adminApi.get<Stats>("/admin/stats");
      if (r.ok) setStats(r.data);
      else if (r.status === 401) router.replace("/admin");
      setLoading(false);
    })();
  }, [router]);

  return (
    <AdminShell title="Overview">
      {loading ? (
        <ActivityIndicator color={colors.primary} size="large" />
      ) : stats ? (
        <>
          <View style={styles.grid}>
            <Stat testID="stat-revenue" icon="cash-outline" label="GROSS REVENUE" value={`CA$${(stats.revenue_cents / 100).toFixed(2)}`} color={colors.success} />
            <Stat testID="stat-orders" icon="bag-handle-outline" label="ALL ORDERS" value={String(stats.total_orders)} color={colors.primary} />
            <Stat testID="stat-active" icon="flame-outline" label="ACTIVE NOW" value={String(stats.active)} color={colors.secondary} />
            <Stat testID="stat-delivered" icon="checkmark-done-outline" label="DELIVERED" value={String(stats.delivered)} color={colors.accent} />
            <Stat testID="stat-users" icon="people-outline" label="CUSTOMERS" value={String(stats.users)} color="#6d28d9" />
          </View>
          <View style={styles.tipBox} testID="admin-tip">
            <Ionicons name="sparkles" size={18} color={colors.secondary} />
            <Text style={styles.tipText}>
              Use the sidebar to publish next week&apos;s menu, tune catering packages, or move orders through the kitchen queue.
            </Text>
          </View>
        </>
      ) : (
        <Text style={{ color: colors.textMuted }}>No data yet.</Text>
      )}
    </AdminShell>
  );
}

function Stat({ icon, label, value, color, testID }: any) {
  return (
    <View style={[styles.statCard, { borderLeftColor: color }]} testID={testID}>
      <View style={styles.statHead}>
        <Text style={styles.statLabel}>{label}</Text>
        <Ionicons name={icon} size={20} color={color} />
      </View>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  statCard: {
    flexGrow: 1, flexBasis: 200, minWidth: 180,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: spacing.lg, borderWidth: 1, borderColor: colors.border,
    borderLeftWidth: 4, ...shadows.soft, gap: spacing.sm,
  },
  statHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  statLabel: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  statValue: { fontSize: 26, fontWeight: "800", letterSpacing: -0.5 },
  tipBox: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: "#FFF7E6", borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: "#FCD9A5" },
  tipText: { flex: 1, color: "#7C4A03", fontSize: 13, lineHeight: 19 },
});
