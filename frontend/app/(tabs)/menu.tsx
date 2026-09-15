import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image,
  ActivityIndicator, RefreshControl, FlatList,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { useCart } from "@/src/cart";
import { api } from "@/src/api";
import { mediaUrl } from "@/src/utils/backendUrl";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD } from "@/src/utils/format";

type MenuItem = { item_id: string; name: string; description: string; price_cents: number; image_url: string; category: string; tags: string[]; is_featured: boolean; veg_type?: string; };
type WeeklyPackage = {
  package_id?: string; name: string; description?: string; price_cents: number;
  pick_count: number; eligible_master_ids: string[]; image_url?: string;
  pricing_mode?: string; veg_price_cents?: number; mixed_price_cents?: number; nonveg_price_cents?: number;
};
type Compl = { item_id: string; name: string; description: string; image_url: string; category: string; };
type WeeklyMenu = {
  menu_id: string; week_start: string; title: string; items: MenuItem[];
  alacarte_enabled?: boolean; package_enabled?: boolean; package?: WeeklyPackage | null;
  complimentary_items?: Compl[];
};

/** "2026-08-30" → "AUG 30 – SEP 5". The week is Sunday-anchored (7 days). */
function formatWeekRange(weekStartIso?: string): string {
  if (!weekStartIso) return "THIS WEEK";
  const start = new Date(weekStartIso + "T00:00:00");
  if (isNaN(start.getTime())) return "THIS WEEK";
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  const fmt = (d: Date) =>
    d.toLocaleDateString("en-US", { month: "short", day: "numeric" }).toUpperCase();
  return `${fmt(start)} – ${fmt(end)}`;
}

/** Classic Indian veg / non-veg / egg indicator: a bordered square with a dot. */
function VegMarker({ type }: { type?: string }) {
  const t = (type || "vegetarian").toLowerCase();
  const color = t === "non-vegetarian" ? "#C1272D" : t === "eggitarian" ? "#E6A700" : "#0A8F3C";
  return (
    <View style={[styles.vegMarker, { borderColor: color }]} testID={`veg-marker-${t}`}>
      <View style={[styles.vegDot, { backgroundColor: color }]} />
    </View>
  );
}

type Mode = "alacarte" | "package";

export default function MenuTab() {
  const [current, setCurrent] = useState<WeeklyMenu | null>(null);
  const [anytime, setAnytime] = useState<MenuItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [mode, setMode] = useState<Mode>("alacarte");
  const { add, count } = useCart();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const load = async () => {
    const r = await api.get<WeeklyMenu>("/menu/current");
    if (r.ok) setCurrent(r.data);
    const a = await api.get<MenuItem[]>("/menu/anytime");
    if (a.ok) setAnytime(a.data || []);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  // Auto-live: refresh menu + always-available every 15s while screen is mounted.
  useEffect(() => {
    const id = setInterval(() => { load(); }, 15000);
    return () => clearInterval(id);
  }, []);

  const alacarteOn = current?.alacarte_enabled ?? true;
  const packageOn = (current?.package_enabled ?? false) && !!current?.package;
  const showSegment = alacarteOn && packageOn;

  // If only package is enabled, force mode=package.
  useEffect(() => {
    if (packageOn && !alacarteOn) setMode("package");
    else if (alacarteOn && !packageOn) setMode("alacarte");
  }, [packageOn, alacarteOn]);

  const items = useMemo(() => current?.items ?? [], [current]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.primary} size="large" /></View>;

  const activeMode: Mode = showSegment ? mode : (packageOn ? "package" : "alacarte");

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <SafeAreaView edges={["top"]} style={styles.header}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.eyebrow}>{activeMode === "package" ? "WEEKLY PACKAGE" : "À LA CARTE"}</Text>
            <Text style={styles.title}>{"This week\u2019s menu"}</Text>
            <Text style={styles.sub}>{formatWeekRange(current?.week_start)}</Text>
          </View>
          <TouchableOpacity testID="menu-cart-button" style={styles.cartBtn} onPress={() => router.push("/(tabs)/orders")}>
            <Ionicons name="bag-handle-outline" size={22} color={colors.text} />
            {count > 0 && <View style={styles.cartDot}><Text style={styles.cartDotText}>{count}</Text></View>}
          </TouchableOpacity>
        </View>

        {showSegment && (
          <View style={styles.segmentWrap}>
            <TouchableOpacity
              testID="mode-alacarte"
              style={[styles.segment, activeMode === "alacarte" && styles.segmentActive]}
              onPress={() => setMode("alacarte")}
            >
              <Ionicons name="restaurant-outline" size={14} color={activeMode === "alacarte" ? "#fff" : colors.text} />
              <Text style={[styles.segmentText, activeMode === "alacarte" && styles.segmentTextActive]}>À la carte</Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID="mode-package"
              style={[styles.segment, activeMode === "package" && styles.segmentActive]}
              onPress={() => setMode("package")}
            >
              <Ionicons name="gift-outline" size={14} color={activeMode === "package" ? "#fff" : colors.text} />
              <Text style={[styles.segmentText, activeMode === "package" && styles.segmentTextActive]}>Weekly Package</Text>
            </TouchableOpacity>
          </View>
        )}
      </SafeAreaView>

      {activeMode === "package" ? (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 + insets.bottom, gap: spacing.md }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          testID="menu-package-scroll"
        >
          <PackageHero
            pkg={current!.package!}
            weeklyMenu={current!}
            eligibleCount={
              (current!.package!.eligible_master_ids?.length ?? 0) || (current!.items?.length ?? 0)
            }
            onOpen={() => router.push(`/menu/package/${current!.menu_id}`)}
          />
          {current?.complimentary_items && current.complimentary_items.length > 0 && (
            <View style={styles.compPreview} testID="menu-complimentary-preview">
              <Ionicons name="gift" size={14} color={colors.secondary} />
              <Text style={styles.compPreviewText}>
                Free with every plan: {current.complimentary_items.map(c => c.name).join(" · ")}
              </Text>
            </View>
          )}
          <AnytimeSection items={anytime} onAdd={(it) => add({ kind: "menu", ref_id: it.item_id, name: it.name, price_cents: it.price_cents, image_url: it.image_url })} />
        </ScrollView>
      ) : (
        <FlatList
          testID="menu-list"
          data={items}
          keyExtractor={i => i.item_id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 + insets.bottom, gap: spacing.md }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          ListFooterComponent={<AnytimeSection items={anytime} onAdd={(it) => add({ kind: "menu", ref_id: it.item_id, name: it.name, price_cents: it.price_cents, image_url: it.image_url })} />}
          renderItem={({ item }) => (
            <View style={styles.row} testID={`menu-row-${item.item_id}`}>
              <Image source={{ uri: mediaUrl(item.image_url) }} style={styles.rowImg} />
              <View style={{ flex: 1, padding: spacing.md, gap: 4 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <VegMarker type={item.veg_type} />
                  <Text style={styles.rowName} numberOfLines={1}>{item.name}</Text>
                  {item.is_featured && <View style={styles.tagFeat}><Text style={styles.tagFeatText}>SIGNATURE</Text></View>}
                </View>
                <Text style={styles.rowDesc} numberOfLines={2}>{item.description}</Text>
                <View style={styles.rowFoot}>
                  <Text style={styles.rowPrice}>{centsToCAD(item.price_cents)}</Text>
                  <TouchableOpacity
                    testID={`menu-add-${item.item_id}`}
                    style={styles.addBtn}
                    onPress={() => add({ kind: "menu", ref_id: item.item_id, name: item.name, price_cents: item.price_cents, image_url: item.image_url })}
                  >
                    <Ionicons name="add" size={14} color="#fff" />
                    <Text style={styles.addText}>Add</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          )}
          ListEmptyComponent={<Text style={{ textAlign: "center", color: colors.textMuted, marginTop: 40 }}>No items available this week.</Text>}
        />
      )}
    </View>
  );
}

export function PackageHero({ pkg, weeklyMenu, eligibleCount, onOpen }: {
  pkg: WeeklyPackage; weeklyMenu: WeeklyMenu; eligibleCount: number; onOpen: () => void;
}) {
  // Compute rough savings: pick_count × average à la carte price - package price
  const avg = weeklyMenu.items && weeklyMenu.items.length > 0
    ? weeklyMenu.items.reduce((s, i) => s + (i.price_cents || 0), 0) / weeklyMenu.items.length
    : 0;
  const isComp = pkg.pricing_mode === "composition";
  const minPrice = isComp
    ? Math.min(pkg.veg_price_cents || 0, pkg.mixed_price_cents || 0, pkg.nonveg_price_cents || 0)
    : pkg.price_cents;
  const estimatedAlacarte = Math.round(avg * pkg.pick_count);
  const savings = isComp ? 0 : Math.max(0, estimatedAlacarte - pkg.price_cents);

  return (
    <View style={styles.pkgHero} testID="package-hero">
      <View style={styles.pkgHeroImgWrap}>
        <Image
          source={{ uri: mediaUrl(pkg.image_url || weeklyMenu.items?.[0]?.image_url) }}
          style={styles.pkgHeroImg}
        />
        <View style={styles.pkgHeroBadge}>
          <Ionicons name="gift" size={11} color="#fff" />
          <Text style={styles.pkgHeroBadgeText}>WEEKLY COMBO</Text>
        </View>
      </View>
      <View style={{ padding: spacing.lg, gap: spacing.sm }}>
        <Text style={styles.pkgHeroTitle}>{pkg.name}</Text>
        {pkg.description ? <Text style={styles.pkgHeroDesc}>{pkg.description}</Text> : null}
        <View style={styles.pkgHeroPricingRow}>
          <View>
            <Text style={styles.pkgHeroPrice}>{isComp ? `from ${centsToCAD(minPrice)}` : centsToCAD(pkg.price_cents)}</Text>
            <Text style={styles.pkgHeroPriceSub}>{isComp ? `pick ${pkg.pick_count} · price by veg / non-veg mix` : `total · pick ${pkg.pick_count} dishes`}</Text>
          </View>
          {savings > 0 && (
            <View style={styles.savingsChip}>
              <Ionicons name="pricetag" size={11} color="#fff" />
              <Text style={styles.savingsChipText}>Save ~{centsToCAD(savings)}</Text>
            </View>
          )}
        </View>
        <View style={styles.pkgHeroStats}>
          <View style={styles.pkgHeroStatRow}>
            <Ionicons name="restaurant-outline" size={14} color={colors.textMuted} />
            <Text style={styles.pkgHeroStatText}>{eligibleCount} dishes to choose from this week</Text>
          </View>
          <View style={styles.pkgHeroStatRow}>
            <Ionicons name="flash-outline" size={14} color={colors.textMuted} />
            <Text style={styles.pkgHeroStatText}>
              {isComp
                ? `5 Veg ${centsToCAD(pkg.veg_price_cents || 0)} · Mixed ${centsToCAD(pkg.mixed_price_cents || 0)} · 5 Non-Veg ${centsToCAD(pkg.nonveg_price_cents || 0)}`
                : `Pick exactly ${pkg.pick_count} — one flat price`}
            </Text>
          </View>
        </View>
        <TouchableOpacity testID="pkg-hero-cta" style={styles.pkgHeroBtn} onPress={onOpen}>
          <Ionicons name="options" size={16} color="#fff" />
          <Text style={styles.pkgHeroBtnText}>Build your combo</Text>
          <Ionicons name="arrow-forward" size={14} color="#fff" />
        </TouchableOpacity>
      </View>
    </View>
  );
}

function AnytimeSection({ items, onAdd }: { items: MenuItem[]; onAdd: (it: MenuItem) => void; }) {
  if (!items || items.length === 0) return null;
  return (
    <View style={styles.anytimeWrap} testID="menu-anytime">
      <View style={styles.anytimeHead}>
        <Ionicons name="time-outline" size={16} color={colors.primary} />
        <Text style={styles.anytimeTitle}>Always Available</Text>
      </View>
      <Text style={styles.anytimeSub}>Order any time — biryani, rolls, breads &amp; more.</Text>
      {items.map(it => (
        <View key={it.item_id} style={styles.row} testID={`anytime-row-${it.item_id}`}>
          <Image source={{ uri: mediaUrl(it.image_url) }} style={styles.rowImg} />
          <View style={{ flex: 1, padding: spacing.md, gap: 4 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <VegMarker type={it.veg_type} />
              <Text style={styles.rowName} numberOfLines={1}>{it.name}</Text>
            </View>
            <Text style={styles.rowDesc} numberOfLines={2}>{it.description}</Text>
            <View style={styles.rowFoot}>
              <Text style={styles.rowPrice}>{centsToCAD(it.price_cents)}</Text>
              <TouchableOpacity testID={`anytime-add-${it.item_id}`} style={styles.addBtn} onPress={() => onAdd(it)}>
                <Ionicons name="add" size={14} color="#fff" />
                <Text style={styles.addText}>Add</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  anytimeWrap: { marginTop: spacing.lg, gap: spacing.sm },
  anytimeHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  anytimeTitle: { fontSize: 18, fontWeight: "800", color: colors.text },
  anytimeSub: { fontSize: 12, color: colors.textMuted, marginTop: -2, marginBottom: 4 },
  compPreview: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: spacing.md, padding: spacing.md, backgroundColor: "#FFFBF2", borderRadius: radius.md, borderWidth: 1, borderColor: colors.secondary },
  compPreviewText: { flex: 1, fontSize: 12, color: colors.text, fontWeight: "600" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  header: { backgroundColor: colors.background, borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: spacing.lg },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: spacing.xl, paddingBottom: 0 },
  eyebrow: { color: colors.primary, letterSpacing: 3, fontSize: 11, fontWeight: "800" },
  title: { fontSize: 26, fontWeight: "800", color: colors.text, marginTop: 4, letterSpacing: -0.3 },
  sub: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  cartBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  cartDot: { position: "absolute", top: 4, right: 4, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", paddingHorizontal: 4 },
  cartDotText: { color: "#fff", fontSize: 10, fontWeight: "800" },

  segmentWrap: { flexDirection: "row", gap: 6, padding: 6, backgroundColor: colors.surfaceAlt, marginHorizontal: spacing.xl, marginTop: spacing.md, borderRadius: radius.pill },
  segment: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 8, borderRadius: radius.pill },
  segmentActive: { backgroundColor: colors.primary },
  segmentText: { fontSize: 13, fontWeight: "700", color: colors.text },
  segmentTextActive: { color: "#fff" },

  chip: { flexShrink: 0, height: 36, paddingHorizontal: 16, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontWeight: "600", fontSize: 13 },
  chipTextActive: { color: "#fff" },
  vegMarker: { width: 15, height: 15, borderWidth: 1.5, borderRadius: 3, alignItems: "center", justifyContent: "center" },
  vegDot: { width: 7, height: 7, borderRadius: 4 },

  row: { flexDirection: "row", backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: colors.border, ...shadows.soft },
  rowImg: { width: 110, height: 110, backgroundColor: colors.surfaceAlt },
  rowName: { fontSize: 15, fontWeight: "700", color: colors.text, flexShrink: 1 },
  rowDesc: { color: colors.textMuted, fontSize: 12, lineHeight: 16 },
  rowFoot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  rowPrice: { color: colors.primary, fontWeight: "800", fontSize: 16 },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill },
  addText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  tagFeat: { backgroundColor: colors.secondary, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  tagFeatText: { color: "#1a1a1a", fontSize: 9, fontWeight: "900", letterSpacing: 1 },

  pkgHero: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: colors.border, ...shadows.soft },
  pkgHeroImgWrap: { position: "relative" },
  pkgHeroImg: { width: "100%", height: 200, backgroundColor: colors.surfaceAlt },
  pkgHeroBadge: { position: "absolute", top: spacing.md, left: spacing.md, flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.primary, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  pkgHeroBadgeText: { color: "#fff", fontSize: 10, fontWeight: "900", letterSpacing: 2 },
  pkgHeroTitle: { fontSize: 22, fontWeight: "800", color: colors.text, letterSpacing: -0.3 },
  pkgHeroDesc: { color: colors.textMuted, fontSize: 13, lineHeight: 19 },
  pkgHeroPricingRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  pkgHeroPrice: { fontSize: 28, fontWeight: "800", color: colors.primary, letterSpacing: -0.5 },
  pkgHeroPriceSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  savingsChip: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.success, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill },
  savingsChipText: { color: "#fff", fontSize: 12, fontWeight: "800" },
  pkgHeroStats: { backgroundColor: colors.surfaceAlt, padding: spacing.md, borderRadius: radius.md, gap: 6 },
  pkgHeroStatRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  pkgHeroStatText: { color: colors.text, fontSize: 12, fontWeight: "600" },
  pkgHeroBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.pill, ...shadows.soft },
  pkgHeroBtnText: { color: "#fff", fontSize: 14, fontWeight: "800", flex: 1, textAlign: "center" },
});
