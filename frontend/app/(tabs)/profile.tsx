import React from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, Alert, Platform,
  Modal, TextInput, KeyboardAvoidingView,
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
  const [loyalty, setLoyalty] = React.useState<{ enabled: boolean; earn: number; redeem: number }>({ enabled: true, earn: 1, redeem: 100 });
  React.useEffect(() => { (async () => {
    const r = await api.get<any>("/settings");
    if (r.ok) setLoyalty({
      enabled: r.data.loyalty_enabled !== false,
      earn: r.data.loyalty_earn_points_per_dollar ?? 1,
      redeem: r.data.loyalty_redeem_points_per_dollar ?? 100,
    });
  })(); }, []);

  const enablePush = async () => {    if (Platform.OS === "web") { Alert.alert("Not available", "Push works on device builds only."); return; }
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

  const [editVisible, setEditVisible] = React.useState(false);
  const [nameInput, setNameInput] = React.useState("");
  const [phoneInput, setPhoneInput] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  const openEdit = () => {
    setNameInput(user?.name || "");
    setPhoneInput(user?.phone || "");
    setEditVisible(true);
  };

  const saveProfile = async () => {
    setSaving(true);
    try {
      const r = await api.post("/me/profile", { name: nameInput, phone: phoneInput });
      if (r.ok) {
        await refresh();
        setEditVisible(false);
      } else {
        Alert.alert("Could not save", (r as any).error || "Please try again.");
      }
    } finally {
      setSaving(false);
    }
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

        {loyalty.enabled && user.role !== "guest" && (
        <View style={styles.section}>
          <View style={styles.loyaltyCard} testID="loyalty-card">
            <View style={styles.loyaltyHead}>
              <Text style={styles.loyaltyLabel}>LOYALTY BALANCE</Text>
              <Ionicons name="sparkles" size={16} color={colors.secondary} />
            </View>
            <Text style={styles.loyaltyPoints}>{points} <Text style={styles.loyaltyPointsSub}>pts</Text></Text>
            <Text style={styles.loyaltyHint}>
              {`Earn ${loyalty.earn} point${loyalty.earn === 1 ? "" : "s"} per $1 spent. Redeem ${loyalty.redeem} points = $1 off future orders.`}
            </Text>
          </View>
        </View>
        )}

        {user.role !== "guest" && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Your details</Text>
          <TouchableOpacity testID="profile-edit-phone" style={styles.linkRow} onPress={openEdit}>
            <Ionicons name="call-outline" size={20} color={colors.text} />
            <View style={{ flex: 1 }}>
              <Text style={styles.linkText}>Mobile number</Text>
              <Text style={styles.linkSub}>
                {user.phone ? user.phone : "Add your number to earn & redeem loyalty points"}
              </Text>
            </View>
            <Text style={styles.editLabel}>{user.phone ? "Edit" : "Add"}</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="profile-invite" style={styles.linkRow} onPress={() => router.push("/invite")}>
            <Ionicons name="gift-outline" size={20} color={colors.text} />
            <View style={{ flex: 1 }}>
              <Text style={styles.linkText}>Invite friends & earn</Text>
              <Text style={styles.linkSub}>Share your code — friends save, you earn points</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        </View>
        )}

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

      <Modal visible={editVisible} transparent animationType="slide" onRequestClose={() => setEditVisible(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalRoot}>
          <TouchableOpacity style={styles.modalBackdrop} activeOpacity={1} onPress={() => setEditVisible(false)} />
          <View style={styles.modalCard} testID="profile-edit-modal">
            <Text style={styles.modalTitle}>Edit your details</Text>
            <Text style={styles.modalLabel}>Name</Text>
            <TextInput
              testID="profile-edit-name-input"
              value={nameInput}
              onChangeText={setNameInput}
              placeholder="Your name"
              placeholderTextColor={colors.textMuted}
              style={styles.modalInput}
              autoCapitalize="words"
            />
            <Text style={styles.modalLabel}>Mobile number</Text>
            <TextInput
              testID="profile-edit-phone-input"
              value={phoneInput}
              onChangeText={setPhoneInput}
              placeholder="+1 (416) 555-0100"
              placeholderTextColor={colors.textMuted}
              style={styles.modalInput}
              keyboardType="phone-pad"
            />
            <Text style={styles.modalHint}>
              Adding your mobile number makes you eligible to earn loyalty points and redeem them on future orders.
            </Text>
            <TouchableOpacity testID="profile-edit-save" style={[styles.saveBtn, saving && { opacity: 0.7 }]} onPress={saveProfile} disabled={saving}>
              <Text style={styles.saveBtnText}>{saving ? "Saving…" : "Save"}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setEditVisible(false)} style={styles.cancelBtn}>
              <Text style={styles.cancelBtnText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
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
  editLabel: { fontSize: 13, fontWeight: "800", color: colors.primary },
  modalRoot: { flex: 1, justifyContent: "flex-end" },
  modalBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: colors.overlay },
  modalCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl,
    padding: spacing.xl, gap: spacing.xs,
  },
  modalTitle: { fontSize: 20, fontWeight: "800", color: colors.text, marginBottom: spacing.sm },
  modalLabel: { fontSize: 13, fontWeight: "700", color: colors.text, marginTop: spacing.sm, marginBottom: 4 },
  modalInput: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.lg, paddingVertical: 12, fontSize: 16, color: colors.text,
  },
  modalHint: { fontSize: 12, color: colors.textMuted, marginTop: spacing.sm, lineHeight: 17 },
  saveBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 15, alignItems: "center", marginTop: spacing.lg },
  saveBtnText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  cancelBtn: { alignItems: "center", paddingVertical: spacing.md },
  cancelBtnText: { color: colors.textMuted, fontSize: 14, fontWeight: "700" },
  signOutBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, padding: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.danger, backgroundColor: colors.surface },
  signOutText: { color: colors.danger, fontWeight: "700" },
  deleteAccountBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, padding: spacing.sm, borderRadius: radius.pill, backgroundColor: "transparent" },
  deleteAccountText: { color: colors.textMuted, fontSize: 12, fontWeight: "600", textDecorationLine: "underline" },
  privacyLink: { color: colors.textMuted, fontSize: 11, textAlign: "center", marginTop: spacing.sm, textDecorationLine: "underline" },
});
