import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Alert, Platform,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as DocumentPicker from "expo-document-picker";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { getBackendUrl } from "@/src/utils/backendUrl";
import { colors, spacing, radius, shadows } from "@/src/theme";

type Review = {
  review_id: string;
  item_id: string;
  item_name: string;
  rating: number;
  comment: string;
  customer_name: string;
  status: string;
  source: string;
  created_at?: string;
  order_id?: string | null;
};
type Counts = { pending: number; approved: number; rejected: number };
type Tab = "pending" | "approved" | "rejected";

function StarRow({ n }: { n: number }) {
  return (
    <View style={{ flexDirection: "row", gap: 1 }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Ionicons key={i} name={i <= n ? "star" : "star-outline"} size={15} color="#F5A623" />
      ))}
    </View>
  );
}

export default function AdminReviews() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("pending");
  const [reviews, setReviews] = useState<Review[]>([]);
  const [counts, setCounts] = useState<Counts>({ pending: 0, approved: 0, rejected: 0 });
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async (t: Tab) => {
    setLoading(true);
    const r = await adminApi.get<{ reviews: Review[]; counts: Counts }>(`/admin/reviews?status=${t}`);
    if (!r.ok) {
      if (r.status === 401) return router.replace("/admin");
      setLoading(false);
      return;
    }
    setReviews(r.data.reviews || []);
    setCounts(r.data.counts || { pending: 0, approved: 0, rejected: 0 });
    setLoading(false);
  }, [router]);

  useEffect(() => { load(tab); }, [tab, load]);

  const moderate = async (r: Review, action: "approve" | "reject") => {
    const res = await adminApi.post(`/admin/reviews/${r.review_id}/moderate`, { action });
    if (res.ok) load(tab);
    else Alert.alert("Failed", res.error);
  };

  const remove = async (r: Review) => {
    const doDel = async () => {
      const res = await adminApi.del(`/admin/reviews/${r.review_id}`);
      if (res.ok) load(tab);
      else Alert.alert("Failed", res.error);
    };
    if (Platform.OS === "web") {
      // eslint-disable-next-line no-alert
      if (typeof window !== "undefined" && window.confirm("Delete this review permanently?")) doDel();
    } else {
      Alert.alert("Delete review", "Delete this review permanently?", [
        { text: "Cancel", style: "cancel" },
        { text: "Delete", style: "destructive", onPress: doDel },
      ]);
    }
  };

  const bulkUpload = async () => {
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ["text/csv", "text/comma-separated-values", "application/vnd.ms-excel", "*/*"],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (picked.canceled || !picked.assets?.length) return;
      const asset = picked.assets[0];
      setUploading(true);
      const form = new FormData();
      if (Platform.OS === "web") {
        // web: DocumentPicker exposes the native File on `asset.file`
        const f = (asset as any).file as File | undefined;
        if (f) form.append("file", f, asset.name || "reviews.csv");
        else {
          const blob = await (await fetch(asset.uri)).blob();
          form.append("file", blob as any, asset.name || "reviews.csv");
        }
      } else {
        form.append("file", { uri: asset.uri, name: asset.name || "reviews.csv", type: "text/csv" } as any);
      }
      const token = await getAdminToken();
      const res = await fetch(`${getBackendUrl()}/api/admin/reviews/bulk-upload`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: form,
      });
      const data = await res.json();
      setUploading(false);
      if (!res.ok) { Alert.alert("Upload failed", data?.detail || "Error"); return; }
      const msg = `Imported ${data.inserted} review(s).` + (data.error_count ? `\n${data.error_count} row(s) skipped.` : "");
      Alert.alert("Bulk upload complete", msg + (data.errors?.length ? `\n\n${data.errors.slice(0, 5).join("\n")}` : ""));
      load(tab);
    } catch (e: any) {
      setUploading(false);
      Alert.alert("Upload failed", e?.message || "Could not read file");
    }
  };

  const TABS: { key: Tab; label: string }[] = [
    { key: "pending", label: `Pending (${counts.pending})` },
    { key: "approved", label: `Approved (${counts.approved})` },
    { key: "rejected", label: `Rejected (${counts.rejected})` },
  ];

  return (
    <AdminShell title="Reviews">
      <View style={styles.section}>
        <View style={styles.headRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>Customer reviews</Text>
            <Text style={styles.sub}>
              Customer reviews land here for approval — only approved reviews show on the app.
            </Text>
          </View>
          <TouchableOpacity testID="bulk-upload-btn" style={styles.uploadBtn} onPress={bulkUpload} disabled={uploading}>
            {uploading ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="cloud-upload-outline" size={16} color="#fff" />}
            <Text style={styles.uploadText}>Bulk upload (CSV)</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.csvHint}>
          <Ionicons name="information-circle-outline" size={14} color={colors.textMuted} />
          <Text style={styles.csvHintText}>
            CSV columns: item_id (or item_name), rating (1-5), comment, customer_name. Imported reviews go live immediately.
          </Text>
        </View>
      </View>

      <View style={styles.tabsRow}>
        {TABS.map((t) => (
          <TouchableOpacity
            key={t.key}
            testID={`reviews-tab-${t.key}`}
            style={[styles.tab, tab === t.key && styles.tabActive]}
            onPress={() => setTab(t.key)}
          >
            <Text style={[styles.tabText, tab === t.key && styles.tabTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator color={colors.primary} size="large" style={{ marginTop: 40 }} />
      ) : reviews.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="star-outline" size={40} color={colors.textMuted} />
          <Text style={styles.emptyText}>No {tab} reviews.</Text>
        </View>
      ) : (
        <View style={{ gap: spacing.md }}>
          {reviews.map((r) => (
            <View key={r.review_id} style={styles.card} testID={`review-card-${r.review_id}`}>
              <View style={styles.cardHead}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemName}>{r.item_name}</Text>
                  <View style={styles.metaRow}>
                    <StarRow n={r.rating} />
                    <Text style={styles.metaText}>· {r.customer_name || "Customer"}</Text>
                    {r.source === "admin_bulk" && <View style={styles.badge}><Text style={styles.badgeText}>IMPORTED</Text></View>}
                  </View>
                </View>
              </View>
              {r.comment ? <Text style={styles.comment}>&ldquo;{r.comment}&rdquo;</Text> : null}
              <View style={styles.actions}>
                {tab !== "approved" && (
                  <TouchableOpacity testID={`approve-${r.review_id}`} style={[styles.actBtn, styles.approve]} onPress={() => moderate(r, "approve")}>
                    <Ionicons name="checkmark" size={15} color="#fff" />
                    <Text style={styles.actText}>Approve</Text>
                  </TouchableOpacity>
                )}
                {tab !== "rejected" && (
                  <TouchableOpacity testID={`reject-${r.review_id}`} style={[styles.actBtn, styles.reject]} onPress={() => moderate(r, "reject")}>
                    <Ionicons name="close" size={15} color="#fff" />
                    <Text style={styles.actText}>Reject</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity testID={`delete-${r.review_id}`} style={[styles.actBtn, styles.del]} onPress={() => remove(r)}>
                  <Ionicons name="trash-outline" size={15} color={colors.danger} />
                  <Text style={[styles.actText, { color: colors.danger }]}>Delete</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </View>
      )}
    </AdminShell>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm },
  headRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: colors.text },
  sub: { fontSize: 13, color: colors.textMuted, marginTop: 2 },
  uploadBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill },
  uploadText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  csvHint: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surfaceAlt, padding: spacing.md, borderRadius: radius.md },
  csvHintText: { flex: 1, fontSize: 12, color: colors.textMuted },
  tabsRow: { flexDirection: "row", gap: 6, backgroundColor: colors.surfaceAlt, padding: 5, borderRadius: radius.pill, alignSelf: "flex-start" },
  tab: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: radius.pill },
  tabActive: { backgroundColor: colors.primary },
  tabText: { fontSize: 13, fontWeight: "700", color: colors.text },
  tabTextActive: { color: "#fff" },
  empty: { alignItems: "center", gap: 8, marginTop: 48 },
  emptyText: { color: colors.textMuted, fontSize: 14 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.sm, ...shadows.soft },
  cardHead: { flexDirection: "row", alignItems: "flex-start" },
  itemName: { fontSize: 15, fontWeight: "800", color: colors.text },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4, flexWrap: "wrap" },
  metaText: { fontSize: 12, color: colors.textMuted },
  badge: { backgroundColor: colors.accent, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  badgeText: { color: "#fff", fontSize: 9, fontWeight: "900", letterSpacing: 1 },
  comment: { fontSize: 14, color: colors.text, fontStyle: "italic", lineHeight: 20 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: 4, flexWrap: "wrap" },
  actBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  approve: { backgroundColor: colors.success, borderColor: colors.success },
  reject: { backgroundColor: colors.textMuted, borderColor: colors.textMuted },
  del: { backgroundColor: colors.surface },
  actText: { color: "#fff", fontSize: 12, fontWeight: "700" },
});
