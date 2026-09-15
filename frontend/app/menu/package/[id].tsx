import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, ActivityIndicator,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { mediaUrl } from "@/src/utils/backendUrl";
import { useCart } from "@/src/cart";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD } from "@/src/utils/format";

type Item = { item_id: string; name: string; description: string; price_cents: number; image_url: string; category: string; tags: string[]; is_featured: boolean; veg_type?: string; };
type WeeklyPackage = {
  package_id: string; name: string; description?: string; price_cents: number;
  pick_count: number; eligible_master_ids: string[]; image_url?: string;
  item_surcharges_cents?: Record<string, number>;
  pricing_mode?: string;
  veg_price_cents?: number; mixed_price_cents?: number; nonveg_price_cents?: number;
  complimentary_master_ids?: string[];
};
type Compl = { item_id: string; name: string; description: string; image_url: string; category: string; };
type WeeklyMenu = {
  menu_id: string; week_start: string; title: string; items: Item[];
  package_enabled?: boolean; package?: WeeklyPackage | null;
  complimentary_items?: Compl[];
};

export default function PackageCustomize() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { add } = useCart();

  const [wm, setWm] = useState<WeeklyMenu | null>(null);
  const [loading, setLoading] = useState(true);
  // NEW: map of master_item_id → quantity picked. Sum(values) === pickCount when valid.
  const [qty, setQty] = useState<Record<string, number>>({});

  useEffect(() => {
    (async () => {
      // Since we currently only allow a package on the CURRENT week, use /menu/current.
      const r = await api.get<WeeklyMenu>("/menu/current");
      if (r.ok && r.data) {
        // Sanity: menu_id must match id from param (or accept any current)
        setWm(r.data);
      }
      setLoading(false);
    })();
  }, [id]);

  const pkg = wm?.package;
  const pickCount = pkg?.pick_count || 0;

  const eligibleItems: Item[] = useMemo(() => {
    if (!wm || !pkg) return [];
    const eligible = pkg.eligible_master_ids && pkg.eligible_master_ids.length > 0
      ? new Set(pkg.eligible_master_ids)
      : null;
    return wm.items.filter(i => !eligible || eligible.has(i.item_id));
  }, [wm, pkg]);

  const totalPicked = useMemo(() => Object.values(qty).reduce((a, b) => a + b, 0), [qty]);
  const remaining = Math.max(0, pickCount - totalPicked);

  const isComposition = pkg?.pricing_mode === "composition";

  // Count non-veg portions among picks (egg counts as non-veg).
  const vegTypeOf = (mid: string) => wm?.items.find(x => x.item_id === mid)?.veg_type || "vegetarian";
  const nonVegPicked = useMemo(() => {
    let s = 0;
    for (const [mid, q] of Object.entries(qty)) if (vegTypeOf(mid) !== "vegetarian") s += q;
    return s;
  }, [qty, wm]);

  // Total per-portion surcharges from the customer's picks (flat mode only).
  const surchargeMap = pkg?.item_surcharges_cents || {};
  const surchargeTotal = useMemo(() => {
    let s = 0;
    for (const [mid, q] of Object.entries(qty)) s += (surchargeMap[mid] || 0) * q;
    return s;
  }, [qty, surchargeMap]);

  // Composition price for the CURRENT selection (only meaningful when all picked).
  const compositionKind: "all-veg" | "mixed" | "all-non-veg" =
    nonVegPicked === 0 ? "all-veg" : nonVegPicked === totalPicked ? "all-non-veg" : "mixed";
  const compositionPrice = (kind: "all-veg" | "mixed" | "all-non-veg") =>
    kind === "all-veg" ? (pkg?.veg_price_cents || 0)
    : kind === "all-non-veg" ? (pkg?.nonveg_price_cents || 0)
    : (pkg?.mixed_price_cents || 0);

  const effectiveTotal = isComposition
    ? compositionPrice(compositionKind)
    : (pkg?.price_cents || 0) + surchargeTotal;

  const inc = (mid: string) => {
    if (totalPicked >= pickCount) return;
    setQty(prev => ({ ...prev, [mid]: (prev[mid] || 0) + 1 }));
  };
  const dec = (mid: string) => {
    setQty(prev => {
      const cur = prev[mid] || 0;
      if (cur <= 0) return prev;
      const next = { ...prev, [mid]: cur - 1 };
      if (next[mid] === 0) delete next[mid];
      return next;
    });
  };

  const alacarteTotal = useMemo(() => {
    let s = 0;
    for (const [mid, q] of Object.entries(qty)) {
      const it = wm?.items.find(x => x.item_id === mid);
      s += (it?.price_cents || 0) * q;
    }
    return s;
  }, [qty, wm]);
  const savings = Math.max(0, alacarteTotal - effectiveTotal);

  const isValid = totalPicked === pickCount && pickCount > 0;

  const onAdd = () => {
    if (!wm || !pkg || !isValid) return;

    // Expanded id list preserves quantities for the backend / kitchen ticket.
    const expandedIds: string[] = [];
    // Human-readable, aggregated for display: "Biryani × 3", "Rasgulla × 2"
    const displayLines: string[] = [];
    for (const [mid, q] of Object.entries(qty)) {
      const it = wm.items.find(x => x.item_id === mid);
      const name = it?.name || mid;
      for (let i = 0; i < q; i++) expandedIds.push(mid);
      displayLines.push(q > 1 ? `${name} × ${q}` : name);
    }

    add({
      kind: "weekly_package",
      ref_id: wm.menu_id,
      name: pkg.name,
      price_cents: effectiveTotal,     // base + selected surcharges (server re-computes for safety)
      image_url: pkg.image_url || wm.items[0]?.image_url || "",
      package_selections: expandedIds,
      package_selection_names: displayLines,
      package_pick_count: pickCount,
      weekly_menu_id: wm.menu_id,
      selection_labels: [{ title: `Pick ${pickCount}`, items: displayLines }],
    });
    router.replace("/cart");
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.primary} size="large" /></View>;
  if (!wm || !pkg) {
    return (
      <View style={styles.center}>
        <Text style={styles.err}>No weekly package is available.</Text>
        <TouchableOpacity onPress={() => router.back()} style={styles.backCta}><Text style={styles.backCtaText}>Go back</Text></TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView edges={["top"]} style={styles.hdr}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="pkg-back">
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.hdrTitle} numberOfLines={1}>Weekly Combo</Text>
          <Text style={styles.hdrSub} numberOfLines={1}>{pkg.name}</Text>
        </View>
      </SafeAreaView>

      <ScrollView contentContainerStyle={{ paddingBottom: 220 + insets.bottom }} showsVerticalScrollIndicator={false}>
        <Image source={{ uri: mediaUrl(pkg.image_url || eligibleItems[0]?.image_url) }} style={styles.hero} />
        <View style={styles.headBlock}>
          <Text style={styles.packName}>{pkg.name}</Text>
          {pkg.description ? <Text style={styles.packTagline}>{pkg.description}</Text> : null}
          {isComposition ? (
            <View style={{ gap: 6, marginTop: 4 }}>
              <Text style={styles.packMeta}>Pick {pickCount} dishes · price depends on your veg / non-veg mix</Text>
              <View style={styles.tierRow} testID="pkg-pricing-tiers">
                <View style={styles.tierChip}><Text style={styles.tierChipLabel}>5 Veg</Text><Text style={styles.tierChipPrice}>{centsToCAD(pkg.veg_price_cents || 0)}</Text></View>
                <View style={styles.tierChip}><Text style={styles.tierChipLabel}>Mixed</Text><Text style={styles.tierChipPrice}>{centsToCAD(pkg.mixed_price_cents || 0)}</Text></View>
                <View style={styles.tierChip}><Text style={styles.tierChipLabel}>5 Non-Veg</Text><Text style={styles.tierChipPrice}>{centsToCAD(pkg.nonveg_price_cents || 0)}</Text></View>
              </View>
            </View>
          ) : (
            <View style={styles.summaryRow}>
              <Text style={styles.packPrice}>{centsToCAD(pkg.price_cents)}</Text>
              <Text style={styles.packMeta}>total · pick {pickCount} portions · repeats allowed</Text>
            </View>
          )}
        </View>

        <View style={styles.stickyProgress}>
          <View style={{ flex: 1 }}>
            <Text style={styles.progressTitle}>
              {isValid ? "All set!" : remaining === 1 ? "Pick 1 more" : `Pick ${remaining} more`}
            </Text>
            <Text style={styles.progressSub}>
              {totalPicked} / {pickCount} selected
              {isComposition && totalPicked > 0
                ? `  ·  ${totalPicked - nonVegPicked} veg / ${nonVegPicked} non-veg`
                : ""}
            </Text>
            {isComposition && totalPicked > 0 && (
              <Text style={styles.progressPrice} testID="pkg-live-price">
                {isValid ? `Total ${centsToCAD(effectiveTotal)}` : `Now ${centsToCAD(compositionPrice(compositionKind))}`}
              </Text>
            )}
          </View>
          {savings > 0 && (
            <View style={styles.savingsBadge}>
              <Ionicons name="pricetag" size={12} color="#fff" />
              <Text style={styles.savingsText}>Save {centsToCAD(savings)}</Text>
            </View>
          )}
        </View>

        <View style={{ padding: spacing.lg, gap: spacing.sm }}>
          {eligibleItems.map(it => {
            const n = qty[it.item_id] || 0;
            const on = n > 0;
            const canInc = totalPicked < pickCount;
            const surcharge = surchargeMap[it.item_id] || 0;
            return (
              <View
                key={it.item_id}
                testID={`pkg-option-${it.item_id}`}
                style={[styles.optRow, on && styles.optRowActive]}
              >
                <Image source={{ uri: mediaUrl(it.image_url) }} style={styles.optImg} />
                <View style={{ flex: 1, gap: 2 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={styles.optName} numberOfLines={1}>{it.name}</Text>
                    {it.is_featured && <View style={styles.tagFeat}><Text style={styles.tagFeatText}>★</Text></View>}
                    {surcharge > 0 && (
                      <View style={styles.surTag} testID={`pkg-surcharge-tag-${it.item_id}`}>
                        <Ionicons name="add" size={10} color="#fff" />
                        <Text style={styles.surTagText}>{centsToCAD(surcharge)}</Text>
                      </View>
                    )}
                  </View>
                  <Text style={styles.optDesc} numberOfLines={2}>{it.description}</Text>
                  <Text style={styles.optPrice}>
                    À la carte {centsToCAD(it.price_cents)}
                    {surcharge > 0 ? ` · +${centsToCAD(surcharge)} per portion in combo` : ""}
                  </Text>
                </View>

                {/* Qty stepper */}
                <View style={styles.qtyBox}>
                  <TouchableOpacity
                    testID={`pkg-dec-${it.item_id}`}
                    disabled={!on}
                    onPress={() => dec(it.item_id)}
                    style={[styles.qtyBtn, !on && styles.qtyBtnDisabled]}
                  >
                    <Ionicons name="remove" size={18} color={on ? colors.text : colors.textMuted} />
                  </TouchableOpacity>
                  <Text style={[styles.qtyText, on && styles.qtyTextActive]}>{n}</Text>
                  <TouchableOpacity
                    testID={`pkg-inc-${it.item_id}`}
                    disabled={!canInc}
                    onPress={() => inc(it.item_id)}
                    style={[styles.qtyBtn, canInc ? styles.qtyBtnAdd : styles.qtyBtnDisabled]}
                  >
                    <Ionicons name="add" size={18} color={canInc ? "#fff" : colors.textMuted} />
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
          {eligibleItems.length === 0 && (
            <Text style={styles.err}>No eligible items available in this week&apos;s menu.</Text>
          )}
        </View>

        {wm.complimentary_items && wm.complimentary_items.length > 0 && (
          <View style={styles.compWrap} testID="pkg-complimentary">
            <View style={styles.compHead}>
              <Ionicons name="gift-outline" size={16} color={colors.secondary} />
              <Text style={styles.compTitle}>Complimentary this week</Text>
              <View style={styles.compFreeTag}><Text style={styles.compFreeText}>FREE</Text></View>
            </View>
            <Text style={styles.compSub}>Included with every weekly plan — no selection needed.</Text>
            {wm.complimentary_items.map(c => (
              <View key={c.item_id} style={styles.compRow} testID={`pkg-comp-${c.item_id}`}>
                <Image source={{ uri: mediaUrl(c.image_url) }} style={styles.compImg} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.compName} numberOfLines={1}>{c.name}</Text>
                  {!!c.description && <Text style={styles.compDesc} numberOfLines={2}>{c.description}</Text>}
                </View>
                <Ionicons name="checkmark-circle" size={20} color={colors.success} />
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Sticky footer */}
      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.footerLabel}>Package total</Text>
          <Text style={styles.footerTotal} testID="pkg-total">{centsToCAD(effectiveTotal)}</Text>
          {isComposition && isValid && (
            <Text style={styles.footerBreakdown} testID="pkg-composition-line">
              {compositionKind === "all-veg" ? "5 Veg plan"
                : compositionKind === "all-non-veg" ? "5 Non-Veg plan"
                : `Mixed plan · ${totalPicked - nonVegPicked} veg + ${nonVegPicked} non-veg`}
            </Text>
          )}
          {!isComposition && surchargeTotal > 0 && (
            <Text style={styles.footerBreakdown} testID="pkg-surcharge-line">
              {centsToCAD(pkg.price_cents)} combo + {centsToCAD(surchargeTotal)} premium picks
            </Text>
          )}
          {savings > 0 && (
            <Text style={styles.footerSavings}>You save {centsToCAD(savings)} vs à la carte</Text>
          )}
        </View>
        <TouchableOpacity
          testID="pkg-add-to-bag"
          style={[styles.addBtn, !isValid && { opacity: 0.5 }]}
          disabled={!isValid}
          onPress={onAdd}
        >
          <Ionicons name="bag-add" size={18} color="#fff" />
          <Text style={styles.addBtnText}>Add to Bag</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background, padding: spacing.lg, gap: spacing.md },
  err: { color: colors.textMuted, textAlign: "center" },
  backCta: { backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 10, borderRadius: radius.pill },
  backCtaText: { color: "#fff", fontWeight: "800" },

  hdr: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border },
  backBtn: { width: 40, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceAlt },
  hdrTitle: { fontSize: 12, letterSpacing: 3, fontWeight: "800", color: colors.primary },
  hdrSub: { fontSize: 15, fontWeight: "800", color: colors.text, marginTop: 2 },

  hero: { width: "100%", height: 200, backgroundColor: colors.surfaceAlt },
  headBlock: { padding: spacing.lg, gap: 6 },
  packName: { fontSize: 22, fontWeight: "800", color: colors.text, letterSpacing: -0.3 },
  packTagline: { fontSize: 13, color: colors.textMuted, lineHeight: 19 },
  summaryRow: { flexDirection: "row", alignItems: "baseline", gap: spacing.sm, marginTop: 4, flexWrap: "wrap" },
  packPrice: { fontSize: 22, fontWeight: "800", color: colors.primary },
  packMeta: { fontSize: 12, color: colors.textMuted },

  stickyProgress: { flexDirection: "row", alignItems: "center", padding: spacing.md, marginHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  progressTitle: { fontSize: 14, fontWeight: "800", color: colors.text },
  progressSub: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  progressPrice: { fontSize: 13, color: colors.primary, fontWeight: "800", marginTop: 2 },
  tierRow: { flexDirection: "row", gap: spacing.sm },
  tierChip: { flex: 1, backgroundColor: colors.surfaceAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingVertical: 8, alignItems: "center" },
  tierChipLabel: { fontSize: 11, color: colors.textMuted, fontWeight: "700" },
  tierChipPrice: { fontSize: 15, color: colors.text, fontWeight: "800", marginTop: 2 },
  compWrap: { marginHorizontal: spacing.lg, marginTop: spacing.sm, padding: spacing.md, backgroundColor: "#FFFBF2", borderRadius: radius.md, borderWidth: 1, borderColor: colors.secondary, gap: spacing.sm },
  compHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  compTitle: { fontSize: 14, fontWeight: "800", color: colors.text, flex: 1 },
  compFreeTag: { backgroundColor: colors.success, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  compFreeText: { color: "#fff", fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  compSub: { fontSize: 12, color: colors.textMuted, marginTop: -2 },
  compRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.sm, borderWidth: 1, borderColor: colors.border },
  compImg: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt },
  compName: { fontSize: 14, fontWeight: "700", color: colors.text },
  compDesc: { fontSize: 12, color: colors.textMuted, lineHeight: 16 },
  savingsBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.success, paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  savingsText: { color: "#fff", fontSize: 12, fontWeight: "800" },

  optRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  optRowActive: { borderColor: colors.primary, backgroundColor: "#FFF7F3" },
  optImg: { width: 64, height: 64, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt },
  optName: { fontSize: 14, fontWeight: "800", color: colors.text, flex: 1 },
  optDesc: { fontSize: 12, color: colors.textMuted, lineHeight: 16 },
  optPrice: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  tagFeat: { backgroundColor: colors.secondary, paddingHorizontal: 4, borderRadius: 4 },
  tagFeatText: { color: "#1a1a1a", fontSize: 10, fontWeight: "900" },
  surTag: { flexDirection: "row", alignItems: "center", backgroundColor: colors.primary, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  surTagText: { color: "#fff", fontSize: 10, fontWeight: "800" },

  qtyBox: { flexDirection: "row", alignItems: "center", gap: 6 },
  qtyBtn: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceAlt },
  qtyBtnAdd: { backgroundColor: colors.primary, borderColor: colors.primary },
  qtyBtnDisabled: { opacity: 0.4 },
  qtyText: { minWidth: 20, textAlign: "center", color: colors.textMuted, fontWeight: "800", fontSize: 14 },
  qtyTextActive: { color: colors.text },

  footer: { position: "absolute", bottom: 0, left: 0, right: 0, flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, ...shadows.card },
  footerLabel: { fontSize: 11, color: colors.textMuted, letterSpacing: 1, fontWeight: "700" },
  footerTotal: { fontSize: 22, fontWeight: "800", color: colors.primary, marginTop: 2 },
  footerSavings: { fontSize: 11, color: colors.success, fontWeight: "700" },
  footerBreakdown: { fontSize: 11, color: colors.textMuted, fontWeight: "600", marginTop: 1 },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 22, paddingVertical: 14, borderRadius: radius.pill, ...shadows.soft },
  addBtnText: { color: "#fff", fontSize: 14, fontWeight: "800" },
});
