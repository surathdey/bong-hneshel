/**
 * Admin Referrals leaderboard — ranks top referrers by friends who ordered.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius } from "@/src/theme";

type Row = {
  referrer_id: string; name: string; email: string; code: string;
  invited: number; rewarded: number; points_earned: number; loyalty_points: number;
};

export default function AdminReferrals() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [rewardPts, setRewardPts] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const r = await adminApi.get<{ leaderboard: Row[]; reward_points: number }>("/admin/referrals/leaderboard");
    if (r.status === 401) return router.replace("/admin");
    if (r.ok) { setRows(r.data.leaderboard || []); setRewardPts(r.data.reward_points || 0); }
    setLoading(false);
  }, [router]);

  useEffect(() => { (async () => {
    const t = await getAdminToken(); if (!t) return router.replace("/admin");
    await load();
  })(); }, [router, load]);

  const totalInvited = rows.reduce((s, r) => s + r.invited, 0);
  const totalOrdered = rows.reduce((s, r) => s + r.rewarded, 0);
  const totalPts = rows.reduce((s, r) => s + r.points_earned, 0);

  if (loading) return <AdminShell title="Referrals"><ActivityIndicator color={colors.primary} size="large" /></AdminShell>;

  return (
    <AdminShell title="Referrals">
      <View style={styles.statsRow} testID="admin-referrals-stats">
        <Stat label="Total invited" value={String(totalInvited)} />
        <Stat label="Friends ordered" value={String(totalOrdered)} />
        <Stat label="Points awarded" value={String(totalPts)} />
      </View>
      <Text style={styles.note}>Referrers earn {rewardPts} points each time an invited friend places their first order.</Text>

      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={{ minWidth: 620 }}>
          <View style={[styles.tr, styles.head]}>
            <Text style={[styles.th, { width: 44 }]}>#</Text>
            <Text style={[styles.th, { flex: 2 }]}>Referrer</Text>
            <Text style={[styles.th, { width: 90 }]}>Code</Text>
            <Text style={[styles.th, { width: 80, textAlign: "right" }]}>Invited</Text>
            <Text style={[styles.th, { width: 80, textAlign: "right" }]}>Ordered</Text>
            <Text style={[styles.th, { width: 90, textAlign: "right" }]}>Points</Text>
          </View>
          {rows.length === 0 ? (
            <View style={styles.empty}><Ionicons name="gift-outline" size={28} color={colors.textMuted} /><Text style={styles.emptyText}>No referrals yet.</Text></View>
          ) : rows.map((r, i) => (
            <View key={r.referrer_id} style={styles.tr} testID={`admin-referral-row-${i}`}>
              <Text style={[styles.td, { width: 44, fontWeight: "800" }]}>{i + 1}</Text>
              <View style={{ flex: 2 }}>
                <Text style={styles.tdName}>{r.name}</Text>
                <Text style={styles.tdSub}>{r.email}</Text>
              </View>
              <Text style={[styles.td, styles.code, { width: 90 }]}>{r.code || "—"}</Text>
              <Text style={[styles.td, { width: 80, textAlign: "right" }]}>{r.invited}</Text>
              <Text style={[styles.td, { width: 80, textAlign: "right", fontWeight: "800", color: colors.success }]}>{r.rewarded}</Text>
              <Text style={[styles.td, { width: 90, textAlign: "right", fontWeight: "800" }]}>{r.points_earned}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </AdminShell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statVal}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  statsRow: { flexDirection: "row", gap: spacing.md },
  stat: { flex: 1, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  statVal: { fontSize: 26, fontWeight: "900", color: colors.text },
  statLabel: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  note: { fontSize: 13, color: colors.textMuted },
  tr: { flexDirection: "row", alignItems: "center", paddingVertical: 12, paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, gap: spacing.sm },
  head: { backgroundColor: colors.surfaceAlt, borderTopLeftRadius: radius.md, borderTopRightRadius: radius.md },
  th: { fontSize: 12, fontWeight: "800", color: colors.textMuted, letterSpacing: 0.5 },
  td: { fontSize: 14, color: colors.text },
  tdName: { fontSize: 14, fontWeight: "700", color: colors.text },
  tdSub: { fontSize: 12, color: colors.textMuted },
  code: { fontWeight: "800", letterSpacing: 1, color: colors.primary },
  empty: { alignItems: "center", padding: spacing.xl, gap: spacing.sm },
  emptyText: { color: colors.textMuted },
});
