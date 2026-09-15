import React, { useState } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator, ScrollView,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { adminApi, setAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { BRAND } from "@/src/brand";

export default function AdminLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@bong-hneshel.ca");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setLoading(true); setError(null);
    const r = await adminApi.post<{ access_token: string }>("/admin/login", { email, password });
    setLoading(false);
    if (r.ok) { await setAdminToken(r.data.access_token); router.replace("/admin/dashboard"); }
    else setError(r.error || "Login failed");
  };

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.center}>
        <View style={styles.card} testID="admin-login-card">
          <View style={styles.brandRow}>
            <View style={styles.logo}><Text style={styles.logoText}>C</Text></View>
            <View>
              <Text style={styles.brand}>{BRAND.name}</Text>
              <Text style={styles.brandSub}>Admin Portal</Text>
            </View>
          </View>

          <Text style={styles.title}>Sign in</Text>
          <Text style={styles.desc}>Manage weekly menus, catering packages and orders.</Text>

          <View style={{ gap: spacing.md }}>
            <View>
              <Text style={styles.label}>Email</Text>
              <TextInput
                testID="admin-email"
                value={email} onChangeText={setEmail}
                autoCapitalize="none" keyboardType="email-address"
                placeholder="admin@bong-hneshel.ca" placeholderTextColor={colors.textMuted}
                style={styles.input}
              />
            </View>
            <View>
              <Text style={styles.label}>Password</Text>
              <TextInput
                testID="admin-password"
                value={password} onChangeText={setPassword}
                secureTextEntry
                placeholder="••••••••" placeholderTextColor={colors.textMuted}
                style={styles.input}
              />
            </View>
            {error && <Text style={styles.error} testID="admin-login-error">{error}</Text>}
            <TouchableOpacity
              testID="admin-login-submit"
              style={[styles.btn, loading && { opacity: 0.5 }]}
              onPress={submit}
              disabled={loading || !email || !password}
            >
              {loading ? <ActivityIndicator color="#fff" /> : (
                <>
                  <Text style={styles.btnText}>Sign in</Text>
                  <Ionicons name="arrow-forward" size={16} color="#fff" />
                </>
              )}
            </TouchableOpacity>
          </View>

          <Text style={styles.footer}>Default: admin@bong-hneshel.ca · password from server env</Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.accent },
  center: { flexGrow: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  card: { width: "100%", maxWidth: 440, backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.xxl, gap: spacing.lg, ...shadows.card },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  logo: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  logoText: { color: "#fff", fontWeight: "800", fontSize: 22 },
  brand: { fontSize: 18, fontWeight: "800", color: colors.text },
  brandSub: { color: colors.primary, letterSpacing: 3, fontSize: 10, fontWeight: "800" },
  title: { fontSize: 28, fontWeight: "800", color: colors.text, letterSpacing: -0.5 },
  desc: { color: colors.textMuted, fontSize: 13, lineHeight: 18 },
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800", marginBottom: 6 },
  input: { backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 14, color: colors.text, fontSize: 14 },
  error: { color: colors.danger, fontSize: 12, fontWeight: "600" },
  btn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.primary, paddingVertical: 16, borderRadius: radius.pill, ...shadows.card },
  btnText: { color: "#fff", fontWeight: "800", fontSize: 15 },
  footer: { color: colors.textMuted, fontSize: 11, textAlign: "center", marginTop: spacing.md },
});
