import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, Modal, ScrollView, ActivityIndicator, Platform,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, spacing, radius, shadows } from "@/src/theme";

/** Compact inline rating pill shown on menu cards. Renders nothing when there
 * are no approved reviews yet. */
export function RatingBadge({ avg, count }: { avg?: number; count?: number }) {
  if (!count || count <= 0) return null;
  return (
    <View style={styles.badge} testID="rating-badge">
      <Ionicons name="star" size={12} color="#F5A623" />
      <Text style={styles.badgeText}>{Number(avg || 0).toFixed(1)}</Text>
      <Text style={styles.badgeCount}>({count})</Text>
    </View>
  );
}

function Stars({ n, size = 14 }: { n: number; size?: number }) {
  return (
    <View style={{ flexDirection: "row", gap: 1 }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Ionicons key={i} name={i <= Math.round(n) ? "star" : "star-outline"} size={size} color="#F5A623" />
      ))}
    </View>
  );
}

type ReviewRow = { review_id: string; rating: number; comment: string; customer_name: string; created_at?: string };

/** Bottom-sheet style modal listing a dish's approved reviews. */
export function ReviewsModal({
  itemId, itemName, visible, onClose,
}: { itemId: string | null; itemName: string; visible: boolean; onClose: () => void }) {
  const [loading, setLoading] = useState(true);
  const [avg, setAvg] = useState(0);
  const [count, setCount] = useState(0);
  const [rows, setRows] = useState<ReviewRow[]>([]);

  useEffect(() => {
    if (!visible || !itemId) return;
    setLoading(true);
    (async () => {
      const r = await api.get<{ avg_rating: number; review_count: number; reviews: ReviewRow[] }>(
        `/menu-items/${itemId}/reviews`
      );
      if (r.ok) {
        setAvg(r.data.avg_rating || 0);
        setCount(r.data.review_count || 0);
        setRows(r.data.reviews || []);
      }
      setLoading(false);
    })();
  }, [visible, itemId]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.sheet}>
          <View style={styles.sheetHead}>
            <View style={{ flex: 1 }}>
              <Text style={styles.sheetTitle} numberOfLines={1}>{itemName}</Text>
              {count > 0 && (
                <View style={styles.summaryRow}>
                  <Stars n={avg} />
                  <Text style={styles.summaryText}>{avg.toFixed(1)} · {count} review{count === 1 ? "" : "s"}</Text>
                </View>
              )}
            </View>
            <TouchableOpacity testID="reviews-modal-close" onPress={onClose} style={styles.closeBtn}>
              <Ionicons name="close" size={22} color={colors.text} />
            </TouchableOpacity>
          </View>

          {loading ? (
            <ActivityIndicator color={colors.primary} size="large" style={{ marginVertical: 40 }} />
          ) : rows.length === 0 ? (
            <View style={styles.empty}>
              <Ionicons name="chatbubble-ellipses-outline" size={36} color={colors.textMuted} />
              <Text style={styles.emptyText}>No reviews yet — be the first to order &amp; review!</Text>
            </View>
          ) : (
            <ScrollView contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.xl }}>
              {rows.map((rv) => (
                <View key={rv.review_id} style={styles.reviewRow}>
                  <View style={styles.reviewTop}>
                    <Stars n={rv.rating} size={13} />
                    <Text style={styles.reviewName}>{rv.customer_name || "Verified customer"}</Text>
                  </View>
                  {rv.comment ? <Text style={styles.reviewComment}>{rv.comment}</Text> : null}
                </View>
              ))}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  badge: { flexDirection: "row", alignItems: "center", gap: 2 },
  badgeText: { fontSize: 12, fontWeight: "800", color: colors.text },
  badgeCount: { fontSize: 11, color: colors.textMuted },
  overlay: { flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg, maxHeight: "80%", ...shadows.card, ...(Platform.OS === "web" ? { maxWidth: 560, width: "100%", alignSelf: "center" } : {}) },
  sheetHead: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, marginBottom: spacing.md },
  sheetTitle: { fontSize: 19, fontWeight: "800", color: colors.text },
  summaryRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 },
  summaryText: { fontSize: 13, color: colors.textMuted, fontWeight: "600" },
  closeBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surfaceAlt, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", gap: 8, marginVertical: 36 },
  emptyText: { color: colors.textMuted, fontSize: 14, textAlign: "center", paddingHorizontal: spacing.xl },
  reviewRow: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, gap: 6, backgroundColor: colors.background },
  reviewTop: { flexDirection: "row", alignItems: "center", gap: 8 },
  reviewName: { fontSize: 13, fontWeight: "700", color: colors.text },
  reviewComment: { fontSize: 14, color: colors.text, lineHeight: 20 },
});
