import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image,
  ActivityIndicator, TextInput, Platform,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { mediaUrl } from "@/src/utils/backendUrl";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { BRAND } from "@/src/brand";

type ReviewItem = { item_id: string; name: string; image_url: string };
type RequestData = { business_name: string; customer_name: string; items: ReviewItem[]; already_submitted: boolean };

function Stars({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <View style={styles.starsRow}>
      {[1, 2, 3, 4, 5].map((n) => (
        <TouchableOpacity
          key={n}
          testID={`star-${n}`}
          onPress={() => onChange(n)}
          hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
        >
          <Ionicons
            name={n <= value ? "star" : "star-outline"}
            size={34}
            color={n <= value ? "#F5A623" : colors.border}
          />
        </TouchableOpacity>
      ))}
    </View>
  );
}

export default function ReviewScreen() {
  const { token } = useLocalSearchParams<{ token: string }>();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<RequestData | null>(null);
  const [error, setError] = useState<string>("");
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    (async () => {
      if (!token) return;
      const r = await api.get<RequestData>(`/reviews/request/${token}`);
      if (r.ok) {
        setData(r.data);
        if (r.data.already_submitted) setDone(true);
      } else {
        setError(r.error || "This review link is invalid or has expired.");
      }
      setLoading(false);
    })();
  }, [token]);

  const submit = async () => {
    if (!data) return;
    const reviews = data.items
      .filter((it) => (ratings[it.item_id] || 0) >= 1)
      .map((it) => ({ item_id: it.item_id, rating: ratings[it.item_id], comment: comments[it.item_id] || "" }));
    if (reviews.length === 0) {
      setError("Please tap the stars to rate at least one dish.");
      return;
    }
    setError("");
    setSubmitting(true);
    const r = await api.post(`/reviews/submit`, { token, reviews });
    setSubmitting(false);
    if (r.ok) setDone(true);
    else setError(r.error || "Something went wrong. Please try again.");
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator color={colors.primary} size="large" />
      </SafeAreaView>
    );
  }

  if (error && !data) {
    return (
      <SafeAreaView style={styles.center}>
        <Ionicons name="alert-circle-outline" size={48} color={colors.textMuted} />
        <Text style={styles.errTitle}>Link unavailable</Text>
        <Text style={styles.errText}>{error}</Text>
      </SafeAreaView>
    );
  }

  if (done) {
    return (
      <SafeAreaView style={styles.center} testID="review-success">
        <View style={styles.successBadge}>
          <Ionicons name="checkmark" size={44} color="#fff" />
        </View>
        <Text style={styles.successTitle}>Thank you! 🎉</Text>
        <Text style={styles.successText}>
          Your review has been posted. We really appreciate you taking the time — it helps us keep cooking great food.
        </Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>{(data?.business_name || BRAND.name || "B").trim().charAt(0).toUpperCase()}</Text>
          </View>
          <Text style={styles.brand}>{data?.business_name || BRAND.name}</Text>
          <Text style={styles.title}>
            {data?.customer_name ? `Hi ${data.customer_name.split(" ")[0]}, how was your order?` : "How was your order?"}
          </Text>
          <Text style={styles.subtitle}>Tap the stars to rate each dish. A quick note is optional.</Text>
        </View>

        {data?.items.map((it) => (
          <View key={it.item_id} style={styles.card} testID={`review-item-${it.item_id}`}>
            <View style={styles.cardTop}>
              {it.image_url ? (
                <Image source={{ uri: mediaUrl(it.image_url) }} style={styles.itemImg} />
              ) : (
                <View style={[styles.itemImg, styles.itemImgPlaceholder]}>
                  <Ionicons name="restaurant-outline" size={22} color={colors.textMuted} />
                </View>
              )}
              <Text style={styles.itemName} numberOfLines={2}>{it.name}</Text>
            </View>
            <Stars
              value={ratings[it.item_id] || 0}
              onChange={(n) => setRatings((p) => ({ ...p, [it.item_id]: n }))}
            />
            <TextInput
              testID={`comment-${it.item_id}`}
              style={styles.input}
              placeholder="Add a comment (optional)"
              placeholderTextColor={colors.textMuted}
              value={comments[it.item_id] || ""}
              onChangeText={(t) => setComments((p) => ({ ...p, [it.item_id]: t }))}
              multiline
            />
          </View>
        ))}

        {error ? <Text style={styles.inlineErr}>{error}</Text> : null}

        <TouchableOpacity
          testID="submit-review"
          style={[styles.submitBtn, submitting && { opacity: 0.6 }]}
          onPress={submit}
          disabled={submitting}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="send" size={16} color="#fff" />
              <Text style={styles.submitText}>Post my review</Text>
            </>
          )}
        </TouchableOpacity>
        <Text style={styles.footNote}>No login required · Your feedback goes straight to the kitchen.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background, padding: spacing.xl, gap: spacing.md },
  content: { padding: spacing.lg, paddingBottom: 48, gap: spacing.md, maxWidth: 560, width: "100%", alignSelf: "center" },
  header: { alignItems: "center", gap: 6, marginBottom: spacing.sm, marginTop: spacing.md },
  logo: { width: 56, height: 56, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", ...shadows.soft },
  logoText: { color: "#fff", fontWeight: "800", fontSize: 26 },
  brand: { fontSize: 13, fontWeight: "800", color: colors.primary, letterSpacing: 1, marginTop: 4 },
  title: { fontSize: 22, fontWeight: "800", color: colors.text, textAlign: "center", letterSpacing: -0.3, marginTop: 4 },
  subtitle: { fontSize: 13, color: colors.textMuted, textAlign: "center" },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.md, ...shadows.soft },
  cardTop: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  itemImg: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  itemImgPlaceholder: { alignItems: "center", justifyContent: "center" },
  itemName: { flex: 1, fontSize: 16, fontWeight: "700", color: colors.text },
  starsRow: { flexDirection: "row", gap: spacing.sm, alignSelf: "center" },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, minHeight: 44, color: colors.text, backgroundColor: colors.background, fontSize: 14 },
  submitBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.primary, paddingVertical: 15, borderRadius: radius.pill, marginTop: spacing.sm, ...shadows.soft },
  submitText: { color: "#fff", fontSize: 15, fontWeight: "800" },
  inlineErr: { color: colors.danger, fontSize: 13, textAlign: "center" },
  footNote: { color: colors.textMuted, fontSize: 11, textAlign: "center", marginTop: 4 },
  errTitle: { fontSize: 20, fontWeight: "800", color: colors.text },
  errText: { fontSize: 14, color: colors.textMuted, textAlign: "center" },
  successBadge: { width: 84, height: 84, borderRadius: 42, backgroundColor: colors.success, alignItems: "center", justifyContent: "center", ...shadows.card },
  successTitle: { fontSize: 24, fontWeight: "800", color: colors.text },
  successText: { fontSize: 15, color: colors.textMuted, textAlign: "center", lineHeight: 22 },
});
