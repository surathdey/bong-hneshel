import React from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, Alert, Platform,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/auth";
import { useCart } from "@/src/cart";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { BRAND } from "@/src/brand";
import * as Notifications from "expo-notifications";
import { api, BACKEND_URL } from "@/src/api";

export default function ProfileTab() {
  const { user, signOut, refresh } = useAuth();
  const { clear: clearCart } = useCart();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const enablePush = async () => {
    if (Platform.OS === "web") { Alert.alert("Not available", "Push works on device builds only."); return; }
    try {
      const { status } = await Notifications.requestPermissionsAsync();
      if (status !== "granted") { Alert.alert("Permission required", "Please enable notifications in Settings."); return; }
      const tok = await Notifications.getDevicePushTokenAsync();
      await fetch(`${BACKEND_URL}/api/register-push`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user?.user_id, platform: Platform.OS, device_token: tok.data }),
      });
      Alert.alert("All set", "You'll receive order updates on this device.");
    } catch (e: any) {
      Alert.alert("Could not enable", e?.message || "Try again later.");
    }
  };

  const doSignOut = async () => {
    await clearCart();
    await signOut();
    router.replace("/login");
  };

  const doDeleteAccount = async () => {
    // Two-step confirmation as required by both Apple and Google review guidelines.
    const proceed = await new Promise<boolean>(resolve => {
      Alert.alert(
        "Delete your account?",
        BRAND.copy.deleteWarning,
        [
          { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
          { text: "Continue", style: "destructive", onPress: () => resolve(true) },
        ],
        { cancelable: true, onDismiss: () => resolve(false) }
      );
    });
    if (!proceed) return;
    const finalConfirm = await new Promise<boolean>(resolve => {
      Alert.alert(
        "Are you absolutely sure?",
        "Type 'DELETE' in the next prompt to confirm.",
        [
          { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
          { text: "Yes, delete forever", style: "destructive", onPress: () => resolve(true) },
        ]
      );
    });
    if (!finalConfirm) return;

    const r = await api.del<{ ok: boolean }>("/user/me");
    if (r.ok) {
      Alert.alert("Account deleted", BRAND.copy.deleteFarewell);
      await clearCart();
      await signOut();
      router.replace("/login");
    } else {
      Alert.alert("Delete failed", (r as any).error || "Please email support@curryandco.ca to request deletion.");
    }
  };

  if (!user) return null;

  const points = user.loyalty_points || 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 140 + insets.bottom }} testID="profile-scroll">
        <SafeAreaView edges={["top"]} style={styles.header}>
          <Text style={styles.eyebrow}>ACCOUNT</Text>
          <View style={styles.userRow}>
            {user.picture ? (
              <Image source={{ uri: user.picture }} style={styles.avatar} />
            ) : (
              <View style={[styles.avatar, styles.avatarPh]}>
                <Text style={styles.avatarText}>{user.name?.charAt(0)?.toUpperCase() || "?"}</Text>
              </View>
            )}
            <View style={{ flex: 1 }}>
              <Text style={styles.name} testID="profile-name">{user.name}</Text>
              <Text style={styles.email}>{user.email}</Text>
            </View>
          </View>
        </SafeAreaView>

        <View style={styles.section}>
          <View style={styles.loyaltyCard} testID="loyalty-card">
            <View style={styles.loyaltyHead}>
              <Text style={styles.loyaltyLabel}>LOYALTY BALANCE</Text>
              <Ionicons name="sparkles" size={16} color={colors.secondary} />
            </View>
            <Text style={styles.loyaltyPoints}>{points} <Text style={styles.loyaltyPointsSub}>pts</Text></Text>
            <Text style={styles.loyaltyHint}>
              Earn 1 point per $1 spent. Redeem 100 points = $1 off future orders.
            </Text>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Preferences</Text>
          <TouchableOpacity testID="profile-enable-push" style={styles.linkRow} onPress={enablePush}>
            <Ionicons name="notifications-outline" size={20} color={colors.text} />
            <Text style={styles.linkText}>Enable push notifications</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </TouchableOpacity>
          <TouchableOpacity testID="profile-refresh" style={styles.linkRow} onPress={refresh}>
            <Ionicons name="refresh-outline" size={20} color={colors.text} />
            <Text style={styles.linkText}>Refresh profile</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{BRAND.name}</Text>
          <TouchableOpacity testID="profile-delivery-partner" style={styles.linkRow} onPress={() => router.push("/delivery-partner")}>
            <Ionicons name="bicycle-outline" size={20} color={colors.text} />
            <View style={{ flex: 1 }}>
              <Text style={styles.linkText}>Become a delivery partner</Text>
              <Text style={styles.linkSub}>Earn flexible weekend income across GTA</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </TouchableOpacity>
          <TouchableOpacity testID="profile-about" style={styles.linkRow} onPress={() => Alert.alert("About", BRAND.copy.aboutBlurb)}>
            <Ionicons name="information-circle-outline" size={20} color={colors.text} />
            <Text style={styles.linkText}>About</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <TouchableOpacity testID="profile-signout" style={styles.signOutBtn} onPress={doSignOut}>
            <Ionicons name="log-out-outline" size={18} color={colors.danger} />
            <Text style={styles.signOutText}>Sign out</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="profile-delete-account" style={styles.deleteAccountBtn} onPress={doDeleteAccount}>
            <Ionicons name="trash-outline" size={16} color={colors.textMuted} />
            <Text style={styles.deleteAccountText}>Delete my account</Text>
          </TouchableOpacity>
          <Text style={styles.privacyLink} testID="profile-privacy-link" onPress={() => router.push("/legal/privacy")}>
            Privacy Policy · Terms of Service
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { padding: spacing.xl, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.background },
  eyebrow: { color: colors.primary, letterSpacing: 3, fontSize: 11, fontWeight: "800" },
  userRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.md },
  avatar: { width: 64, height: 64, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt },
  avatarPh: { alignItems: "center", justifyContent: "center" },
  avatarText: { fontSize: 26, fontWeight: "800", color: colors.primary },
  name: { fontSize: 22, fontWeight: "800", color: colors.text, letterSpacing: -0.3 },
  email: { color: colors.textMuted, fontSize: 13, marginTop: 2 },
  section: { padding: spacing.lg, gap: spacing.sm },
  sectionTitle: { color: colors.textMuted, letterSpacing: 2, fontSize: 11, fontWeight: "800", marginBottom: 4 },
  loyaltyCard: { backgroundColor: colors.accent, padding: spacing.xl, borderRadius: radius.lg, ...shadows.card },
  loyaltyHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  loyaltyLabel: { color: "#F0E7D8", letterSpacing: 3, fontSize: 10, fontWeight: "800" },
  loyaltyPoints: { color: "#fff", fontSize: 48, fontWeight: "800", marginTop: 6, letterSpacing: -1 },
  loyaltyPointsSub: { fontSize: 20, fontWeight: "600", color: "rgba(255,255,255,0.7)" },
  loyaltyHint: { color: "rgba(255,255,255,0.8)", fontSize: 12, marginTop: 4 },
  linkRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  linkText: { flex: 1, fontSize: 14, fontWeight: "600", color: colors.text },
  linkSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  signOutBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, padding: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.danger, backgroundColor: colors.surface },
  signOutText: { color: colors.danger, fontWeight: "700" },
  deleteAccountBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, padding: spacing.sm, borderRadius: radius.pill, backgroundColor: "transparent" },
  deleteAccountText: { color: colors.textMuted, fontSize: 12, fontWeight: "600", textDecorationLine: "underline" },
  privacyLink: { color: colors.textMuted, fontSize: 11, textAlign: "center", marginTop: spacing.sm, textDecorationLine: "underline" },
});
