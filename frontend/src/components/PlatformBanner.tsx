/**
 * PlatformBanner — shows a warning banner across the admin portal when the
 * Suparna Dey Platform reports a subscription issue (past-due, cancelled,
 * trial ending, or credentials rotated).
 *
 * Poll cadence matches the backend's 5-min phone-home. The banner never
 * blocks navigation — it just informs. Hard blocks (like hiding checkout
 * in the customer app) happen server-side via 402 responses.
 */
import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type PlatformStatus = {
  known: boolean;
  operational: boolean;
  hide_checkout: boolean;
  show_banner: boolean;
  banner_text: string;
  subscription_status: string | null;
};

export function PlatformBanner() {
  const router = useRouter();
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const r = await api.get("/platform/status");
      if (!cancelled && r.ok) setStatus(r.data);
    };
    load();
    // Refresh every 5 min — same cadence as the backend phone-home.
    const iv = setInterval(load, 300_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  // Hide when: not known (dev), no enforcement asked, or user tapped X.
  if (!status || !status.known || !status.show_banner || dismissed) return null;

  const isCritical = !status.operational || status.hide_checkout;
  const tone = isCritical ? styles.critical : styles.warning;
  const iconName = isCritical ? "alert-circle" : "warning";

  return (
    <View style={[styles.wrap, tone]} testID="platform-banner">
      <Ionicons name={iconName} size={16} color="#fff" />
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>Suparna Dey Platform</Text>
        <Text style={styles.subtitle} numberOfLines={2}>
          {status.banner_text || `Subscription status: ${status.subscription_status || "unknown"}`}
        </Text>
      </View>
      <TouchableOpacity
        onPress={() => router.push("/admin/billing" as any)}
        style={styles.actionBtn}
        testID="platform-banner-fix-billing"
      >
        <Text style={styles.actionText}>Fix billing</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={() => setDismissed(true)} style={styles.dismissBtn}>
        <Ionicons name="close" size={14} color="#fff" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: radius.md,
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
  },
  warning:  { backgroundColor: "#B45309" },   // amber-700
  critical: { backgroundColor: colors.danger }, // red-700
  title:    { color: "#fff", fontWeight: "800", fontSize: 12, letterSpacing: 0.5 },
  subtitle: { color: "rgba(255,255,255,0.95)", fontSize: 13, marginTop: 1 },
  actionBtn: {
    backgroundColor: "rgba(255,255,255,0.18)",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  actionText: { color: "#fff", fontWeight: "700", fontSize: 12 },
  dismissBtn: {
    width: 24, height: 24, borderRadius: 12,
    alignItems: "center", justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.18)",
  },
});
