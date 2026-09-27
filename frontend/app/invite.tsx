import React from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView, Share, Alert, TextInput,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Clipboard from "expo-clipboard";
import { api } from "@/src/api";
import { colors, spacing, radius, shadows } from "@/src/theme";

type ReferralInfo = {
  code: string | null;
  enabled: boolean;
  reward_points: number;
  friend_discount_label: string;
  invited_count: number;
  rewarded_count: number;
  points_earned: number;
  can_redeem: boolean;
};

export default function InviteScreen() {
  const router = useRouter();
  const [info, setInfo] = React.useState<ReferralInfo | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [copied, setCopied] = React.useState(false);
  const [redeemCode, setRedeemCode] = React.useState("");
  const [redeeming, setRedeeming] = React.useState(false);

  const load = React.useCallback(async () => {
    const r = await api.get<ReferralInfo>("/referrals/me");
    if (r.ok) setInfo(r.data);
    setLoading(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const shareLink = info?.code
    ? `${process.env.EXPO_PUBLIC_BACKEND_URL || ""}/email-auth?ref=${info.code}`
    : "";
  const shareMessage = info
    ? `Join me on Bong Hneshel — authentic Bengali home cooking delivered across the GTA! Use my code ${info.code} for ${info.friend_discount_label} your first order.${shareLink ? `\n\n${shareLink}` : ""}`
    : "";

  const onShare = async () => {
    if (!info?.code) return;
    try {
      await Share.share({ message: shareMessage });
    } catch { /* user dismissed */ }
  };

  const onCopy = async () => {
    if (!info?.code) return;
    await Clipboard.setStringAsync(info.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const onRedeem = async () => {
    const c = redeemCode.trim().toUpperCase();
    if (!c) return;
    setRedeeming(true);
    try {
      const r = await api.post<{ friend_discount_label: string }>("/referrals/redeem", { code: c });
      if (r.ok) {
        Alert.alert("Code applied! 🎉", `You'll get ${r.data.friend_discount_label} your first order.`);
        setRedeemCode("");
        load();
      } else {
        Alert.alert("Couldn't apply code", (r as any).error || "Please check the code and try again.");
      }
    } finally {
      setRedeeming(false);
    }
  };

  return (
    <SafeAreaView style={styles.root} edges={["top", "bottom"]} testID="invite-screen">
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.back} hitSlop={10} testID="invite-back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Invite friends</Text>
        <View style={{ width: 40 }} />
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.primary} /></View>
      ) : !info ? (
        <View style={styles.center}><Text style={styles.muted}>Sign in to get your invite code.</Text></View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll}>
          <View style={styles.hero}>
            <Ionicons name="gift" size={40} color={colors.primary} />
            <Text style={styles.heroTitle}>Give {info.friend_discount_label}, get {info.reward_points} points</Text>
            <Text style={styles.heroSub}>
              Share your code with friends. They get {info.friend_discount_label} their first order, and you earn{" "}
              {info.reward_points} loyalty points once they order.
            </Text>
          </View>

          <View style={styles.codeCard}>
            <Text style={styles.codeLabel}>YOUR INVITE CODE</Text>
            <Text style={styles.code} testID="invite-code">{info.code}</Text>
            <TouchableOpacity onPress={onCopy} style={styles.copyRow} testID="invite-copy">
              <Ionicons name={copied ? "checkmark-circle" : "copy-outline"} size={16} color={colors.primary} />
              <Text style={styles.copyText}>{copied ? "Copied!" : "Copy code"}</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={styles.shareBtn} onPress={onShare} activeOpacity={0.85} testID="invite-share">
            <Ionicons name="share-social-outline" size={20} color="#fff" />
            <Text style={styles.shareText}>Share invite</Text>
          </TouchableOpacity>

          <View style={styles.stats}>
            <View style={styles.statBox}>
              <Text style={styles.statNum}>{info.invited_count}</Text>
              <Text style={styles.statLabel}>Invited</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statNum}>{info.rewarded_count}</Text>
              <Text style={styles.statLabel}>Ordered</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statNum}>{info.points_earned}</Text>
              <Text style={styles.statLabel}>Points earned</Text>
            </View>
          </View>

          {info.can_redeem && (
            <View style={styles.redeemCard} testID="invite-redeem-card">
              <Text style={styles.redeemTitle}>Were you invited?</Text>
              <Text style={styles.redeemSub}>Enter a friend’s code to get {info.friend_discount_label} your first order.</Text>
              <View style={styles.redeemRow}>
                <TextInput
                  testID="invite-redeem-input"
                  value={redeemCode}
                  onChangeText={(t) => setRedeemCode(t.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8))}
                  placeholder="FRIEND CODE"
                  placeholderTextColor={colors.textMuted}
                  style={styles.redeemInput}
                  autoCapitalize="characters"
                />
                <TouchableOpacity style={[styles.redeemBtn, redeeming && { opacity: 0.7 }]} onPress={onRedeem} disabled={redeeming} testID="invite-redeem-submit">
                  <Text style={styles.redeemBtnText}>{redeeming ? "…" : "Apply"}</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 18, fontWeight: "800", color: colors.text },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  muted: { color: colors.textMuted, fontSize: 15 },
  scroll: { padding: spacing.xl, gap: spacing.lg },
  hero: { alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  heroTitle: { fontSize: 22, fontWeight: "800", color: colors.text, textAlign: "center" },
  heroSub: { fontSize: 14, color: colors.textMuted, textAlign: "center", lineHeight: 20 },
  codeCard: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 2, borderColor: colors.primary, borderStyle: "dashed", paddingVertical: spacing.xl, alignItems: "center", ...shadows.soft },
  codeLabel: { fontSize: 11, fontWeight: "800", color: colors.textMuted, letterSpacing: 1 },
  code: { fontSize: 40, fontWeight: "900", color: colors.text, letterSpacing: 8, marginVertical: spacing.sm },
  copyRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  copyText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  shareBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 16, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, ...shadows.card },
  shareText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  stats: { flexDirection: "row", gap: spacing.md },
  statBox: { flex: 1, backgroundColor: colors.surface, borderRadius: radius.md, paddingVertical: spacing.lg, alignItems: "center", borderWidth: 1, borderColor: colors.border },
  statNum: { fontSize: 24, fontWeight: "900", color: colors.text },
  statLabel: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  redeemCard: { backgroundColor: colors.surfaceAlt, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  redeemTitle: { fontSize: 16, fontWeight: "800", color: colors.text },
  redeemSub: { fontSize: 13, color: colors.textMuted, lineHeight: 18 },
  redeemRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  redeemInput: { flex: 1, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 12, fontSize: 15, fontWeight: "700", letterSpacing: 2, color: colors.text },
  redeemBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingHorizontal: spacing.xl, alignItems: "center", justifyContent: "center" },
  redeemBtnText: { color: "#fff", fontWeight: "800", fontSize: 15 },
});
