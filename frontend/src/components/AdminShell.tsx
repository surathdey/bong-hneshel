/**
 * Shared admin shell — sidebar navigation + content area.
 * Renders inline (no separate layout stack), used by dashboard/menu/catering/orders pages.
 */
import React from "react";
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, useWindowDimensions, Platform } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter, usePathname } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { clearAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { BRAND } from "@/src/brand";
import { PlatformBanner } from "./PlatformBanner";

const NAV = [
  { key: "/admin/dashboard", label: "Overview", icon: "grid-outline" as const },
  { key: "/admin/master-menu", label: "Master Menu", icon: "library-outline" as const },
  { key: "/admin/menu", label: "Weekly Menu", icon: "restaurant-outline" as const },
  { key: "/admin/catering", label: "Catering", icon: "people-outline" as const },
  { key: "/admin/orders", label: "Orders", icon: "bag-handle-outline" as const },
  { key: "/admin/coupons", label: "Coupons", icon: "pricetag-outline" as const },
  { key: "/admin/reviews", label: "Reviews", icon: "star-outline" as const },
  { key: "/admin/referrals", label: "Referrals", icon: "gift-outline" as const },
  { key: "/admin/customers", label: "Customers", icon: "person-circle-outline" as const },
  { key: "/admin/delivery", label: "Delivery", icon: "bicycle-outline" as const },
  { key: "/admin/billing", label: "Billing", icon: "card-outline" as const },
  { key: "/admin/settings", label: "Settings", icon: "settings-outline" as const },
];

export default function AdminShell({ children, title }: { children: React.ReactNode; title: string }) {
  const router = useRouter();
  const path = usePathname();
  const { width } = useWindowDimensions();
  const wide = width > 900;

  const doLogout = async () => {
    await clearAdminToken();
    router.replace("/admin");
  };

  const nav = (
    <View style={[styles.nav, wide ? styles.navWide : styles.navMobile]}>
      <View style={styles.brandRow}>
        <View style={styles.logo}><Text style={styles.logoText}>{(BRAND.name || "B").trim().charAt(0).toUpperCase()}</Text></View>
        {wide && (
          <View>
            <Text style={styles.brand}>{BRAND.name}</Text>
            <Text style={styles.brandSub}>ADMIN</Text>
          </View>
        )}
      </View>
      <View style={[wide ? { marginTop: spacing.xl, gap: 4 } : { flexDirection: "row", gap: 4, flexShrink: 0 }]}>
        {NAV.map((n) => {
          const active = path === n.key;
          return (
            <TouchableOpacity
              key={n.key}
              testID={`admin-nav-${n.key.split("/").pop()}`}
              onPress={() => router.replace(n.key as any)}
              style={[styles.navItem, active && styles.navItemActive, !wide && { flex: 1 }]}
            >
              <Ionicons name={n.icon} size={18} color={active ? "#fff" : colors.text} />
              {wide && <Text style={[styles.navText, active && styles.navTextActive]}>{n.label}</Text>}
            </TouchableOpacity>
          );
        })}
      </View>
      <View style={{ flex: wide ? 1 : 0 }} />
      <TouchableOpacity testID="admin-logout" onPress={doLogout} style={styles.logoutBtn}>
        <Ionicons name="log-out-outline" size={16} color={colors.danger} />
        {wide && <Text style={styles.logoutText}>Sign out</Text>}
      </TouchableOpacity>
    </View>
  );

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.root}>
      <View style={[styles.body, wide && { flexDirection: "row" }]}>
        {nav}
        <View style={{ flex: 1 }}>
          <View style={styles.topBar}>
            <Text style={styles.pageTitle}>{title}</Text>
          </View>
          <PlatformBanner />
          <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
            {children}
          </ScrollView>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  body: { flex: 1 },
  nav: { backgroundColor: colors.accent, padding: spacing.lg, gap: spacing.md },
  navWide: { width: 240, gap: spacing.md },
  navMobile: { flexDirection: "row", alignItems: "center", flexWrap: "wrap" },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  logo: { width: 36, height: 36, borderRadius: radius.pill, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  logoText: { color: "#fff", fontWeight: "800", fontSize: 18 },
  brand: { color: "#fff", fontSize: 15, fontWeight: "800" },
  brandSub: { color: colors.secondary, letterSpacing: 3, fontSize: 9, fontWeight: "800" },
  navItem: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.md },
  navItemActive: { backgroundColor: colors.primary },
  navText: { color: "#F0E7D8", fontWeight: "600", fontSize: 14 },
  navTextActive: { color: "#fff", fontWeight: "800" },
  logoutBtn: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.06)" },
  logoutText: { color: colors.danger, fontWeight: "700" },
  topBar: { padding: spacing.xl, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface, ...(Platform.OS === "web" ? { position: "sticky" as any, top: 0, zIndex: 10 } : {}), ...shadows.soft },
  pageTitle: { fontSize: 24, fontWeight: "800", color: colors.text, letterSpacing: -0.3 },
});
