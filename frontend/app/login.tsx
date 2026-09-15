import React from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Image,
} from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "@/src/auth";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { BRAND } from "@/src/brand";

const MASCOT = require("../assets/brand/mascot.png");
const LOGIN_BG = require("../assets/brand/login-bg.png");

// Each word of the brand name gets its own colour (readable on the dark photo).
const WORD_COLORS = ["#FFFFFF", colors.primary, "#F5D06B"];

export default function LoginScreen() {
  const { signIn, signInAsGuest, loading, user } = useAuth();
  const router = useRouter();
  const [signingIn, setSigningIn] = React.useState(false);
  const [guestLoading, setGuestLoading] = React.useState(false);

  React.useEffect(() => {
    if (!loading && user) router.replace("/(tabs)");
  }, [loading, user, router]);

  const onSignIn = async () => {
    setSigningIn(true);
    try { await signIn(); } finally { setSigningIn(false); }
  };

  const onGuest = async () => {
    setGuestLoading(true);
    try { await signInAsGuest(); } finally { setGuestLoading(false); }
  };

  const words = (BRAND.name || "").trim().split(/\s+/);

  return (
    <View style={styles.root} testID="login-screen">
      <Image
        source={LOGIN_BG}
        blurRadius={3}
        style={StyleSheet.absoluteFill}
        resizeMode="cover"
      />
      <LinearGradient
        colors={["rgba(0,0,0,0.20)", "rgba(0,0,0,0.55)", "rgba(0,0,0,0.90)"]}
        locations={[0, 0.5, 1]}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView edges={["top", "bottom"]} style={styles.safeInner}>
        <View style={styles.brandRow}>
          <View style={styles.logoBadge}>
            <Image source={MASCOT} style={styles.logoImg} resizeMode="cover" />
          </View>
          <Text style={styles.brand} testID="login-brand-name">
            {words.map((w, i) => (
              <Text key={i} style={{ color: WORD_COLORS[i % WORD_COLORS.length] }}>
                {w}{i < words.length - 1 ? " " : ""}
              </Text>
            ))}
          </Text>
        </View>

        <View style={styles.bottom}>
          <Text style={styles.eyebrow} testID="login-tagline">EXOTIC FLAVORS OF INDIA</Text>
          <Text style={styles.title}>Slow-cooked{"\n"}stories on your plate.</Text>
          <Text style={styles.subtitle}>
            A rotating weekly menu of exotic Indian classics, delivered fresh every Friday evening
            and Saturday morning across the Greater Toronto Area.
          </Text>

          <TouchableOpacity
            testID="login-google-button"
            onPress={onSignIn}
            disabled={signingIn || guestLoading}
            activeOpacity={0.85}
            style={styles.googleBtn}
          >
            {signingIn ? (
              <ActivityIndicator color="#000" />
            ) : (
              <>
                <Ionicons name="logo-google" size={20} color="#000" />
                <Text style={styles.googleBtnText}>Continue with Google</Text>
              </>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            testID="login-guest-button"
            onPress={onGuest}
            disabled={signingIn || guestLoading}
            activeOpacity={0.85}
            style={styles.guestBtn}
          >
            {guestLoading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="person-outline" size={18} color="#fff" />
                <Text style={styles.guestBtnText}>Continue as guest</Text>
              </>
            )}
          </TouchableOpacity>

          <Text style={styles.legal}>By continuing you agree to our Terms & Privacy Policy.</Text>

          <TouchableOpacity
            testID="delivery-partner-entry"
            onPress={() => router.push("/delivery-partner")}
            style={styles.deliveryLink}
          >
            <Ionicons name="bicycle-outline" size={14} color="rgba(255,255,255,0.9)" />
            <Text style={styles.deliveryLinkText}>Delivery partner? Sign in here →</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#000" },
  safeInner: { flex: 1, justifyContent: "space-between", padding: spacing.xl },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  logoBadge: {
    width: 48, height: 48, borderRadius: radius.pill,
    overflow: "hidden", backgroundColor: "#F5B23C",
    borderWidth: 1.5, borderColor: "rgba(255,255,255,0.55)",
    ...shadows.card,
  },
  logoImg: { width: "100%", height: "100%" },
  brand: { fontSize: 22, fontWeight: "800", letterSpacing: 0.3 },
  bottom: { gap: spacing.md },
  eyebrow: { color: colors.primary, letterSpacing: 3, fontSize: 11, fontWeight: "800" },
  title: { color: "#fff", fontSize: 40, fontWeight: "800", lineHeight: 44, letterSpacing: -0.5 },
  subtitle: { color: "rgba(255,255,255,0.82)", fontSize: 15, lineHeight: 22, marginTop: spacing.sm },
  googleBtn: {
    marginTop: spacing.xl,
    backgroundColor: "#fff",
    borderRadius: radius.pill,
    paddingVertical: 16,
    paddingHorizontal: spacing.xl,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.md,
    ...shadows.card,
  },
  googleBtnText: { fontSize: 16, fontWeight: "700", color: "#111" },
  guestBtn: {
    marginTop: spacing.md,
    backgroundColor: "rgba(255,255,255,0.14)",
    borderRadius: radius.pill,
    paddingVertical: 14,
    paddingHorizontal: spacing.xl,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.4)",
  },
  guestBtnText: { fontSize: 15, fontWeight: "700", color: "#fff" },
  deliveryLink: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginTop: spacing.md, paddingVertical: 10 },
  deliveryLinkText: { color: "rgba(255,255,255,0.92)", fontSize: 13, fontWeight: "800", textDecorationLine: "underline" },
  legal: {
    color: "rgba(255,255,255,0.6)", fontSize: 11, textAlign: "center", marginTop: spacing.md,
  },
});
