import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ImageBackground,
  ActivityIndicator, RefreshControl, Linking, Alert,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { useCart } from "@/src/cart";
import { api } from "@/src/api";
import { mediaUrl } from "@/src/utils/backendUrl";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD } from "@/src/utils/format";

type ChoiceGroup = {
  group_id: string; title: string; subtitle?: string;
  min_select: number; max_select: number;
  option_master_ids: string[];
};

type UpgradeTier = {
  tier_id: string; title: string; subtitle?: string;
  per_person_cents: number; is_default: boolean;
  group_overrides: Record<string, { min_select?: number; max_select?: number }>;
};

type PremiumItem = { master_item_id: string; upcharge_per_person_cents: number };

export type CateringPackage = {
  package_id: string; name: string; tagline?: string; description: string;
  emoji?: string; perfect_for?: string;
  price_cents: number; min_guests: number; image_url: string;
  includes: string[];
  included_master_ids: string[];
  choice_groups: ChoiceGroup[];
  upgrade_tiers: UpgradeTier[];
  premium_items: PremiumItem[];
  is_custom_quote: boolean;
  contact_email?: string; contact_phone?: string;
  is_featured: boolean;
  sort_order: number;
};

export default function CateringTab() {
  const [items, setItems] = useState<CateringPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { count } = useCart();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const load = async () => {
    const r = await api.get<CateringPackage[]>("/catering");
    if (r.ok) setItems(r.data || []);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const onOpen = (p: CateringPackage) => {
    router.push(`/catering/${p.package_id}`);
  };

  const onQuoteContact = (p: CateringPackage) => {
    const email = p.contact_email || "orders@curryandco.ca";
    const phone = p.contact_phone || "";
    Alert.alert(
      "Request Custom Quote",
      `${p.name}\n\nMinimum ${p.min_guests} guests. Our team will design your menu.\n\nContact us:`,
      [
        ...(phone ? [{ text: `📞 ${phone}`, onPress: () => Linking.openURL(`tel:${phone.replace(/\s+/g,'')}`) }] : []),
        { text: `✉️ ${email}`, onPress: () => Linking.openURL(`mailto:${email}?subject=Custom%20Quote%20-%20${encodeURIComponent(p.name)}`) },
        { text: "Fill form", onPress: () => router.push(`/catering/${p.package_id}?quote=1`) },
        { text: "Cancel", style: "cancel" },
      ],
    );
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.primary} size="large" /></View>;

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <SafeAreaView edges={["top"]} style={styles.header}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.eyebrow}>CATERING</Text>
            <Text style={styles.title}>Feasts for gatherings</Text>
            <Text style={styles.sub}>Bengali spreads priced per person. Pick your dishes & guest count.</Text>
          </View>
          <TouchableOpacity testID="catering-cart-button" style={styles.cartBtn} onPress={() => router.push("/(tabs)/orders")}>
            <Ionicons name="bag-handle-outline" size={22} color={colors.text} />
            {count > 0 && <View style={styles.cartDot}><Text style={styles.cartDotText}>{count}</Text></View>}
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      <ScrollView
        testID="catering-scroll"
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 + insets.bottom, gap: spacing.lg }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={colors.primary} />}
      >
        {items.map((p) => {
          const isCustom = p.is_custom_quote;
          const priceLabel = isCustom
            ? "Custom Quote"
            : p.upgrade_tiers?.length > 0
              ? `From ${centsToCAD(p.upgrade_tiers[0].per_person_cents)}`
              : centsToCAD(p.price_cents);
          return (
            <View key={p.package_id} style={styles.card} testID={`catering-pack-${p.package_id}`}>
              <ImageBackground source={{ uri: mediaUrl(p.image_url) }} style={styles.img} imageStyle={{ borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg }}>
                <LinearGradient colors={["transparent", "rgba(0,0,0,0.85)"]} style={StyleSheet.absoluteFill} />
                <View style={styles.imgBody}>
                  <View style={styles.imgTopRow}>
                    <View style={styles.minChip}>
                      <Ionicons name="people" size={12} color="#1a1a1a" />
                      <Text style={styles.minText}>MINIMUM {p.min_guests} GUESTS</Text>
                    </View>
                    {isCustom && (
                      <View style={styles.premiumChip}>
                        <Ionicons name="star" size={11} color="#fff" />
                        <Text style={styles.premiumChipText}>SIGNATURE</Text>
                      </View>
                    )}
                  </View>
                  {p.emoji ? <Text style={styles.emoji}>{p.emoji}</Text> : null}
                  <Text style={styles.cardName}>{p.name}</Text>
                  {p.tagline ? <Text style={styles.tagline}>{p.tagline}</Text> : null}
                  <Text style={styles.perPerson}>
                    {priceLabel}
                    {!isCustom && <Text style={styles.perPersonSub}> / person</Text>}
                  </Text>
                </View>
              </ImageBackground>
              <View style={styles.body}>
                {p.perfect_for ? (
                  <View style={styles.perfectForRow}>
                    <Ionicons name="sparkles" size={13} color={colors.secondary} />
                    <Text style={styles.perfectForText}>{p.perfect_for}</Text>
                  </View>
                ) : null}
                <Text style={styles.desc}>{p.description}</Text>
                <View style={styles.includesBox}>
                  <Text style={styles.includesTitle}>WHAT'S INSIDE</Text>
                  {p.includes.map((x, i) => (
                    <View key={i} style={styles.includeRow}>
                      <Ionicons name="checkmark-circle" size={14} color={colors.primary} />
                      <Text style={styles.includeText}>{x}</Text>
                    </View>
                  ))}
                </View>
                {isCustom ? (
                  <TouchableOpacity
                    testID={`catering-quote-${p.package_id}`}
                    style={styles.quoteBtn}
                    onPress={() => onQuoteContact(p)}
                  >
                    <Ionicons name="mail" size={16} color="#fff" />
                    <Text style={styles.customizeBtnText}>Request Custom Quote</Text>
                    <Ionicons name="arrow-forward" size={14} color="#fff" />
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity
                    testID={`catering-customize-${p.package_id}`}
                    style={styles.customizeBtn}
                    onPress={() => onOpen(p)}
                  >
                    <Ionicons name="options" size={16} color="#fff" />
                    <Text style={styles.customizeBtnText}>Customize & Add to Bag</Text>
                    <Ionicons name="arrow-forward" size={14} color="#fff" />
                  </TouchableOpacity>
                )}
              </View>
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  header: { backgroundColor: colors.background, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerRow: { flexDirection: "row", alignItems: "center", padding: spacing.xl, gap: spacing.md },
  eyebrow: { color: colors.primary, letterSpacing: 3, fontSize: 11, fontWeight: "800" },
  title: { fontSize: 26, fontWeight: "800", color: colors.text, marginTop: 4, letterSpacing: -0.3 },
  sub: { color: colors.textMuted, fontSize: 13, marginTop: 4 },
  cartBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  cartDot: { position: "absolute", top: 4, right: 4, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", paddingHorizontal: 4 },
  cartDotText: { color: "#fff", fontSize: 10, fontWeight: "800" },

  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, overflow: "hidden", ...shadows.soft },
  img: { height: 260, justifyContent: "flex-end" },
  imgBody: { padding: spacing.lg, gap: 6 },
  imgTopRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  minChip: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.secondary, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  minText: { color: "#1a1a1a", fontSize: 10, fontWeight: "900", letterSpacing: 2 },
  premiumChip: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.primary, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  premiumChipText: { color: "#fff", fontSize: 10, fontWeight: "900", letterSpacing: 2 },
  emoji: { fontSize: 22, marginTop: 2 },
  cardName: { color: "#fff", fontSize: 22, fontWeight: "800", letterSpacing: -0.3 },
  tagline: { color: "rgba(255,255,255,0.85)", fontSize: 12, fontStyle: "italic" },
  perPerson: { color: "#fff", fontSize: 20, fontWeight: "800", marginTop: 4 },
  perPersonSub: { fontSize: 12, fontWeight: "600", color: "rgba(255,255,255,0.75)" },
  body: { padding: spacing.lg, gap: spacing.md },
  perfectForRow: { flexDirection: "row", alignItems: "flex-start", gap: 6 },
  perfectForText: { flex: 1, fontSize: 11, color: colors.text, fontWeight: "700", letterSpacing: 0.3 },
  desc: { color: colors.textMuted, fontSize: 13, lineHeight: 19 },
  includesBox: { backgroundColor: colors.surfaceAlt, padding: spacing.md, borderRadius: radius.md, gap: 4 },
  includesTitle: { color: colors.text, fontSize: 10, letterSpacing: 2, fontWeight: "800", marginBottom: 4 },
  includeRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  includeText: { color: colors.text, fontSize: 12, flex: 1 },
  customizeBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 14, borderRadius: radius.pill, justifyContent: "center", ...shadows.soft },
  quoteBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.accent, paddingHorizontal: 18, paddingVertical: 14, borderRadius: radius.pill, justifyContent: "center", ...shadows.soft },
  customizeBtnText: { color: "#fff", fontSize: 14, fontWeight: "800", flex: 1, textAlign: "center" },
});
