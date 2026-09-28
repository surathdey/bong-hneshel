import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { colors } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { api } from "@/src/api";

/**
 * Slim, non-interactive marketing strip promoting the first-order coupon.
 * Shown on every customer tab. Hidden automatically for logged-in customers
 * who have already placed an order (no longer eligible) or when no coupon exists.
 */
export default function FirstOrderBanner() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
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

  if (!coupon) return null;

  const discountLabel = coupon.discount_type === "percent"
    ? `${coupon.value}% OFF`
    : `$${(Number(coupon.value) / 100).toFixed(2)} OFF`;

  return (
    <LinearGradient
      colors={[colors.primary, colors.primaryDark]}
      start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }}
      style={[styles.wrap, { paddingTop: insets.top + 10 }]}
    >
      <View testID="first-order-banner" style={styles.row}>
        <Ionicons name="gift" size={22} color="#FFFFFF" />
        <Text style={styles.text}>
          <Text style={styles.bold}>{discountLabel}</Text> your first order — use code{" "}
          <Text style={styles.code}>{coupon.code}</Text>
        </Text>
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingBottom: 12, paddingHorizontal: 16 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10 },
  text: { flexShrink: 1, color: "#FFFFFF", fontSize: 16, lineHeight: 22, textAlign: "center" },
  bold: { fontWeight: "900" },
  code: { fontWeight: "900", letterSpacing: 1 },
});
