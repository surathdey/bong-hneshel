import React from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator,
  KeyboardAvoidingView, Platform, ScrollView, Alert,
} from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useAuth } from "@/src/auth";
import { api } from "@/src/api";
import { colors, spacing, radius, shadows } from "@/src/theme";

type Mode = "login" | "signup" | "forgot" | "reset";

const TITLES: Record<Mode, string> = {
  login: "Welcome back",
  signup: "Create your account",
  forgot: "Reset your password",
  reset: "Enter your code",
};
const SUBTITLES: Record<Mode, string> = {
  login: "Sign in with your email and password.",
  signup: "Order faster and keep your loyalty points.",
  forgot: "We'll email you a 6-digit code to reset your password.",
  reset: "Enter the code we emailed you and choose a new password.",
};

export default function EmailAuthScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ ref?: string }>();
  const { signInWithEmail, signUpWithEmail } = useAuth();

  const [mode, setMode] = React.useState<Mode>("login");
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [referralCode, setReferralCode] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  // Prefill referral code from an invite deep link (?ref=CODE) and jump to signup.
  React.useEffect(() => {
    const ref = (params.ref || "").toString().toUpperCase();
    if (ref) {
      setReferralCode(ref);
      setMode("signup");
    }
  }, [params.ref]);

  const reset = (m: Mode) => { setMode(m); setError(null); setNotice(null); };

  const onSubmit = async () => {
    setError(null); setNotice(null);
    const e = email.trim();
    if (mode !== "reset" && !/^\S+@\S+\.\S+$/.test(e)) {
      setError("Please enter a valid email address."); return;
    }
    setBusy(true);
    try {
      if (mode === "login") {
        const r = await signInWithEmail(e, password);
        if (r.ok) router.replace("/(tabs)");
        else setError(r.error || "Incorrect email or password.");
      } else if (mode === "signup") {
        if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
        const r = await signUpWithEmail(e, password, name, phone, referralCode);
        if (r.ok) router.replace("/(tabs)");
        else setError(r.error || "Could not create account.");
      } else if (mode === "forgot") {
        const r = await api.post<{ message: string }>("/auth/forgot-password", { email: e });
        if (r.ok) {
          reset("reset");
          setNotice("If an account exists, a 6-digit code was emailed. Enter it below.");
        } else setError(r.error || "Something went wrong.");
      } else if (mode === "reset") {
        if (!/^\d{6}$/.test(code.trim())) { setError("Enter the 6-digit code from your email."); return; }
        if (password.length < 8) { setError("New password must be at least 8 characters."); return; }
        const r = await api.post<{ message: string }>("/auth/reset-password", {
          email: e, code: code.trim(), password,
        });
        if (r.ok) {
          Alert.alert("Password updated", "You can now sign in with your new password.");
          setCode(""); setPassword("");
          reset("login");
        } else setError(r.error || "Invalid or expired code.");
      }
    } finally {
      setBusy(false);
    }
  };

  const btnLabel = mode === "login" ? "Sign in"
    : mode === "signup" ? "Create account"
    : mode === "forgot" ? "Send code"
    : "Reset password";

  return (
    <SafeAreaView style={styles.root} edges={["top", "bottom"]} testID="email-auth-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <TouchableOpacity
            testID="email-auth-back"
            onPress={() => router.back()}
            style={styles.back}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          >
            <Ionicons name="chevron-back" size={24} color={colors.text} />
          </TouchableOpacity>

          <Text style={styles.title}>{TITLES[mode]}</Text>
          <Text style={styles.subtitle}>{SUBTITLES[mode]}</Text>

          {(mode === "login" || mode === "signup") && (
            <View style={styles.segment}>
              <TouchableOpacity
                testID="email-auth-tab-login"
                style={[styles.segBtn, mode === "login" && styles.segBtnActive]}
                onPress={() => reset("login")}
              >
                <Text style={[styles.segText, mode === "login" && styles.segTextActive]}>Sign in</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="email-auth-tab-signup"
                style={[styles.segBtn, mode === "signup" && styles.segBtnActive]}
                onPress={() => reset("signup")}
              >
                <Text style={[styles.segText, mode === "signup" && styles.segTextActive]}>Create account</Text>
              </TouchableOpacity>
            </View>
          )}

          {mode === "signup" && (
            <View style={styles.field}>
              <Text style={styles.label}>Name (optional)</Text>
              <TextInput
                testID="email-auth-name"
                value={name}
                onChangeText={setName}
                placeholder="Your name"
                placeholderTextColor={colors.textMuted}
                style={styles.input}
                autoCapitalize="words"
              />
            </View>
          )}

          <View style={styles.field}>
            <Text style={styles.label}>Email</Text>
            <TextInput
              testID="email-auth-email"
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor={colors.textMuted}
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              editable={mode !== "reset"}
            />
          </View>

          {mode === "signup" && (
            <View style={styles.field}>
              <Text style={styles.label}>Mobile number <Text style={styles.optional}>*optional</Text></Text>
              <TextInput
                testID="email-auth-phone"
                value={phone}
                onChangeText={setPhone}
                placeholder="+1 (416) 555-0100"
                placeholderTextColor={colors.textMuted}
                style={styles.input}
                keyboardType="phone-pad"
                autoCorrect={false}
              />
              <Text style={styles.hint}>
                * Optional, but add your mobile number to become eligible to earn loyalty
                points and redeem them for discounts on future orders.
              </Text>
            </View>
          )}

          {mode === "signup" && (
            <View style={styles.field}>
              <Text style={styles.label}>Referral code <Text style={styles.optional}>*optional</Text></Text>
              <TextInput
                testID="email-auth-referral"
                value={referralCode}
                onChangeText={(t) => setReferralCode(t.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8))}
                placeholder="Enter a friend's code"
                placeholderTextColor={colors.textMuted}
                style={[styles.input, { letterSpacing: 2, fontWeight: "700" }]}
                autoCapitalize="characters"
                autoCorrect={false}
              />
              <Text style={styles.hint}>Have a friend’s invite code? Enter it to get a discount on your first order.</Text>
            </View>
          )}

          {mode === "reset" && (
            <View style={styles.field}>
              <Text style={styles.label}>6-digit code</Text>
              <TextInput
                testID="email-auth-code"
                value={code}
                onChangeText={(t) => setCode(t.replace(/[^0-9]/g, "").slice(0, 6))}
                placeholder="123456"
                placeholderTextColor={colors.textMuted}
                style={[styles.input, { letterSpacing: 6, fontWeight: "700" }]}
                keyboardType="number-pad"
                maxLength={6}
              />
            </View>
          )}

          {mode !== "forgot" && (
            <View style={styles.field}>
              <Text style={styles.label}>{mode === "reset" ? "New password" : "Password"}</Text>
              <View style={styles.pwRow}>
                <TextInput
                  testID="email-auth-password"
                  value={password}
                  onChangeText={setPassword}
                  placeholder={mode === "signup" || mode === "reset" ? "At least 8 characters" : "Your password"}
                  placeholderTextColor={colors.textMuted}
                  style={[styles.input, { flex: 1, marginBottom: 0 }]}
                  secureTextEntry={!showPw}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <TouchableOpacity onPress={() => setShowPw((s) => !s)} style={styles.eye} testID="email-auth-toggle-pw">
                  <Ionicons name={showPw ? "eye-off-outline" : "eye-outline"} size={20} color={colors.textMuted} />
                </TouchableOpacity>
              </View>
            </View>
          )}

          {mode === "login" && (
            <TouchableOpacity testID="email-auth-forgot-link" onPress={() => reset("forgot")} style={styles.forgotLink}>
              <Text style={styles.forgotText}>Forgot password?</Text>
            </TouchableOpacity>
          )}

          {!!error && <Text style={styles.error} testID="email-auth-error">{error}</Text>}
          {!!notice && <Text style={styles.notice} testID="email-auth-notice">{notice}</Text>}

          <TouchableOpacity
            testID="email-auth-submit"
            onPress={onSubmit}
            disabled={busy}
            activeOpacity={0.85}
            style={[styles.primaryBtn, busy && { opacity: 0.7 }]}
          >
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>{btnLabel}</Text>}
          </TouchableOpacity>

          {mode === "forgot" && (
            <TouchableOpacity testID="email-auth-have-code" onPress={() => reset("reset")} style={styles.altLink}>
              <Text style={styles.altText}>I already have a code</Text>
            </TouchableOpacity>
          )}
          {mode === "reset" && (
            <TouchableOpacity testID="email-auth-back-login" onPress={() => reset("login")} style={styles.altLink}>
              <Text style={styles.altText}>Back to sign in</Text>
            </TouchableOpacity>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.xl, paddingTop: spacing.lg, flexGrow: 1 },
  back: { width: 40, height: 40, justifyContent: "center", marginBottom: spacing.md, marginLeft: -8 },
  title: { fontSize: 28, fontWeight: "800", color: colors.text, letterSpacing: -0.5 },
  subtitle: { fontSize: 15, color: colors.textMuted, marginTop: spacing.xs, marginBottom: spacing.xl, lineHeight: 21 },
  segment: {
    flexDirection: "row", backgroundColor: colors.surfaceAlt, borderRadius: radius.pill,
    padding: 4, marginBottom: spacing.xl,
  },
  segBtn: { flex: 1, paddingVertical: 10, borderRadius: radius.pill, alignItems: "center" },
  segBtnActive: { backgroundColor: colors.surface, ...shadows.soft },
  segText: { fontSize: 14, fontWeight: "700", color: colors.textMuted },
  segTextActive: { color: colors.text },
  field: { marginBottom: spacing.lg },
  label: { fontSize: 13, fontWeight: "700", color: colors.text, marginBottom: 6 },
  optional: { fontSize: 12, fontWeight: "600", color: colors.primary },
  hint: { fontSize: 12, color: colors.textMuted, marginTop: 6, lineHeight: 17 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14,
    fontSize: 16, color: colors.text,
  },
  pwRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  eye: {
    width: 48, height: 50, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
  },
  forgotLink: { alignSelf: "flex-end", paddingVertical: spacing.xs, marginBottom: spacing.sm },
  forgotText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
  error: { color: colors.danger, fontSize: 14, marginBottom: spacing.md, fontWeight: "600" },
  notice: { color: colors.success, fontSize: 14, marginBottom: spacing.md, fontWeight: "600" },
  primaryBtn: {
    backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 16,
    alignItems: "center", justifyContent: "center", marginTop: spacing.sm, ...shadows.card,
  },
  primaryBtnText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  altLink: { alignItems: "center", paddingVertical: spacing.lg },
  altText: { color: colors.primary, fontWeight: "700", fontSize: 14 },
});
