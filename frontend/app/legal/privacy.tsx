import React from "react";
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, Linking } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter, Stack } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { colors, spacing, radius } from "@/src/theme";
import { BRAND } from "@/src/brand";

/**
 * Minimal in-app Privacy & Terms page.
 * Apple + Google both accept an in-app privacy summary as long as a hosted
 * URL is ALSO provided in the store listing. This screen doubles as the
 * "click-through" from the profile screen.
 */
export default function PrivacyScreen() {
  const router = useRouter();
  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView edges={["top"]} style={styles.hdr}>
        <TouchableOpacity onPress={() => router.back()} style={styles.back}>
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>Privacy & Terms</Text>
      </SafeAreaView>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
        <Text style={styles.h2}>Privacy Policy</Text>
        <Text style={styles.p}>
          {BRAND.name} respects your privacy. This app collects only the data required to fulfil your orders and improve your experience.
        </Text>

        <Text style={styles.h3}>Data we collect</Text>
        <Text style={styles.p}>
          • <Text style={styles.b}>Contact:</Text> Name, email, phone — used to place orders and send delivery updates.{"\n"}
          • <Text style={styles.b}>Address:</Text> Delivery address & location, used only for route optimisation and ETA.{"\n"}
          • <Text style={styles.b}>Purchases:</Text> Order history — used for receipts, loyalty rewards and support.{"\n"}
          • <Text style={styles.b}>Diagnostics:</Text> Anonymous crash logs so we can fix bugs.
        </Text>

        <Text style={styles.h3}>Payments</Text>
        <Text style={styles.p}>
          Card payments are processed by Stripe. We never see or store your card number.
        </Text>

        <Text style={styles.h3}>Third-party services</Text>
        <Text style={styles.p}>
          Stripe (payments), Google Maps (delivery routes), Emergent (notifications). Each is bound by its own privacy policy.
        </Text>

        <Text style={styles.h3}>Your rights</Text>
        <Text style={styles.p}>
          You can delete your account and all associated personal data at any time via <Text style={styles.b}>Profile → Delete my account</Text>.
          Past orders are anonymised (kept only for tax and legal records).
        </Text>

        <Text style={styles.h3}>Contact</Text>
        <Text style={styles.p}>
          Email <Text style={styles.link} onPress={() => Linking.openURL(`mailto:${BRAND.support.email}`)}>{BRAND.support.email}</Text> for any privacy question or GDPR/PIPEDA request.
        </Text>

        <Text style={[styles.h2, { marginTop: spacing.xl }]}>Terms of Service</Text>
        <Text style={styles.p}>
          By using {BRAND.name} you agree to receive food-preparation and delivery-related messages, pay for orders you place, and treat our couriers with respect. Weekly menus, prices and delivery windows are set by the kitchen and may change without notice. All food is prepared in a facility that also processes dairy, gluten, nuts and seafood — please review the allergen tags before ordering.
        </Text>

        <Text style={styles.p}>
          For the full legally-binding version of these terms, visit{" "}
          <Text style={styles.link} onPress={() => Linking.openURL("https://curryandco.ca/privacy")}>
            curryandco.ca/privacy
          </Text>.
        </Text>

        <Text style={styles.footer}>Last updated: {new Date().toLocaleDateString()}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceAlt },
  title: { fontSize: 17, fontWeight: "800", color: colors.text },
  h2: { fontSize: 20, fontWeight: "800", color: colors.text, marginTop: spacing.sm },
  h3: { fontSize: 14, fontWeight: "800", color: colors.text, marginTop: spacing.sm, letterSpacing: 0.3 },
  p: { fontSize: 13, color: colors.textMuted, lineHeight: 20 },
  b: { fontWeight: "800", color: colors.text },
  link: { color: colors.primary, fontWeight: "700", textDecorationLine: "underline" },
  footer: { fontSize: 11, color: colors.textMuted, marginTop: spacing.xl, textAlign: "center" },
});
