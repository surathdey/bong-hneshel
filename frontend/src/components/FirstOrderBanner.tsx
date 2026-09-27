import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { colors } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { api } from "@/src/api";

/**
 * Slim, dismissible marketing strip promoting the first-order 10% coupon.
 * Shown on every customer tab. Hidden automatically for logged-in customers
 * who have already placed an order (no longer eligible).
 */
export default function FirstOrderBanner() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [hidden, setHidden] = React.useState(false);
  const [coupon, setCoupon] = React.useState<any>(null);

  React.useEffect(() => {
    let alive = true;
    (async () => {
      // Logged-in customers get the eligibility-aware endpoint (null once they've ordered);
      // everyone else (guests / logged out) gets the public promo coupon.
      const path = user && user.role !== "guest" ? "/coupons/first-time" : "/coupons/promo";
      const r = await api.get<any>(path);
      if (alive) setCoupon(r.ok ? r.data?.coupon ?? null : null);
    })();
    return () => { alive = false; };
  }, [user]);

  if (hidden || !coupon) return null;

  const isGuest = !user || user.role === "guest";
  const discountLabel = coupon.discount_type === "percent"
    ? `${coupon.value}% OFF`
    : `$${(Number(coupon.value) / 100).toFixed(2)} OFF`;

  return (
    <LinearGradient
      colors={[colors.primary, colors.primaryDark]}
      start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }}
      style={[styles.wrap, { paddingTop: insets.top + 8 }]}
    >
      <TouchableOpacity
        testID="first-order-banner"
        activeOpacity={0.9}
        style={styles.row}
        onPress={() => router.push(isGuest ? "/login" : "/(tabs)/menu")}
      >
        <Ionicons name="gift" size={18} color="#FFFFFF" />
        <Text style={styles.text} numberOfLines={1}>
          <Text style={styles.bold}>{discountLabel}</Text> your first order — code <Text style={styles.bold}>{coupon.code}</Text>
        </Text>
        <View style={styles.cta}>
          <Text style={styles.ctaText}>{isGuest ? "Sign in" : "Order"}</Text>
        </View>
        <TouchableOpacity testID="first-order-banner-close" hitSlop={10} onPress={() => setHidden(true)}>
          <Ionicons name="close" size={18} color="rgba(255,255,255,0.85)" />
        </TouchableOpacity>
      </TouchableOpacity>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingBottom: 10, paddingHorizontal: 14 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  text: { flex: 1, color: "#FFFFFF", fontSize: 13 },
  bold: { fontWeight: "800" },
  cta: { backgroundColor: "rgba(255,255,255,0.22)", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  ctaText: { color: "#FFFFFF", fontWeight: "800", fontSize: 12 },
});
