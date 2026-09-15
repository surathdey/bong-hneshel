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
  const [eligible, setEligible] = React.useState(true);

  React.useEffect(() => {
    let alive = true;
    (async () => {
      if (user && user.role !== "guest") {
        const r = await api.get<any>("/coupons/first-time");
        if (alive) setEligible(!!(r.ok && r.data?.coupon));
      } else {
        if (alive) setEligible(true); // guests: entice them to sign in
      }
    })();
    return () => { alive = false; };
  }, [user]);

  if (hidden || !eligible) return null;

  const isGuest = !user || user.role === "guest";

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
          <Text style={styles.bold}>10% OFF</Text> your first order — code <Text style={styles.bold}>FIRST10</Text>
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
