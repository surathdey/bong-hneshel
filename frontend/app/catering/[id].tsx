import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, ActivityIndicator,
  Alert, TextInput, Platform, KeyboardAvoidingView,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { mediaUrl } from "@/src/utils/backendUrl";
import { useCart, CateringSelection } from "@/src/cart";
import { useAuth } from "@/src/auth";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD } from "@/src/utils/format";

type ChoiceGroup = {
  group_id: string; title: string; subtitle?: string;
  min_select: number; max_select: number;
  option_master_ids: string[]; display_order?: number;
};
type UpgradeTier = {
  tier_id: string; title: string; subtitle?: string;
  per_person_cents: number; is_default: boolean;
  group_overrides: Record<string, { min_select?: number; max_select?: number }>;
};
type PremiumItem = { master_item_id: string; upcharge_per_person_cents: number };
type MasterLite = {
  item_id: string; name: string; short_description?: string;
  image_url?: string; veg_type: string; category: string; allergens?: string[];
};
type Pkg = {
  package_id: string; name: string; tagline?: string; description: string;
  emoji?: string; perfect_for?: string;
  price_cents: number; min_guests: number; image_url: string;
  includes: string[]; included_master_ids: string[];
  choice_groups: ChoiceGroup[]; upgrade_tiers: UpgradeTier[]; premium_items: PremiumItem[];
  is_custom_quote: boolean; contact_email?: string; contact_phone?: string;
};

export default function CateringCustomizeScreen() {
  const { id, quote } = useLocalSearchParams<{ id: string; quote?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { add } = useCart();

  const [loading, setLoading] = useState(true);
  const [pkg, setPkg] = useState<Pkg | null>(null);
  const [master, setMaster] = useState<Record<string, MasterLite>>({});
  const [tierId, setTierId] = useState<string | undefined>(undefined);
  const [guests, setGuests] = useState<string>("10");
  const [picks, setPicks] = useState<Record<string, string[]>>({});     // group_id -> [master_id]
  const [premium, setPremium] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // Quote-request form state (for custom quote packages)
  const [qName, setQName] = useState("");
  const [qEmail, setQEmail] = useState("");
  const [qPhone, setQPhone] = useState("");
  const [qGuests, setQGuests] = useState("");
  const [qDate, setQDate] = useState("");
  const [qNotes, setQNotes] = useState("");

  useEffect(() => {
    (async () => {
      const r = await api.get<{ package: Pkg; master_items: Record<string, MasterLite> }>(`/catering/${id}`);
      if (r.ok && r.data) {
        setPkg(r.data.package);
        setMaster(r.data.master_items);
        setGuests(String(r.data.package.min_guests));
        setQGuests(String(r.data.package.min_guests));
        const tiers = r.data.package.upgrade_tiers || [];
        if (tiers.length > 0) {
          const def = tiers.find(t => t.is_default) || tiers[0];
          setTierId(def.tier_id);
        }
      }
      setLoading(false);
    })();
  }, [id]);

  // Redirect guests to sign in for real orders (not quote-only requests).
  useEffect(() => {
    if (!loading && pkg && !pkg.is_custom_quote && user?.role === "guest") {
      Alert.alert(
        "Sign in to order catering",
        "Catering orders require a Google account (for delivery updates & receipts).",
        [
          { text: "Cancel", style: "cancel", onPress: () => router.back() },
          { text: "Sign in", onPress: () => router.replace("/login") },
        ],
      );
    }
  }, [loading, pkg, user]);

  // Resolve the currently active tier + effective group min/max.
  const activeTier: UpgradeTier | null = useMemo(() => {
    if (!pkg) return null;
    if (pkg.upgrade_tiers?.length) {
      return pkg.upgrade_tiers.find(t => t.tier_id === tierId) || pkg.upgrade_tiers[0];
    }
    return null;
  }, [pkg, tierId]);

  const groupLimits = (g: ChoiceGroup) => {
    const ov = activeTier?.group_overrides?.[g.group_id];
    return {
      min: ov?.min_select ?? g.min_select,
      max: ov?.max_select ?? g.max_select,
    };
  };

  const togglePick = (g: ChoiceGroup, mid: string) => {
    setPicks(prev => {
      const cur = prev[g.group_id] || [];
      const { max } = groupLimits(g);
      if (cur.includes(mid)) {
        return { ...prev, [g.group_id]: cur.filter(x => x !== mid) };
      }
      // If maxing out, drop earliest
      if (cur.length >= max) {
        if (max === 1) return { ...prev, [g.group_id]: [mid] };
        return { ...prev, [g.group_id]: [...cur.slice(1), mid] };
      }
      return { ...prev, [g.group_id]: [...cur, mid] };
    });
  };

  const togglePremium = (mid: string) => {
    setPremium(prev => prev.includes(mid) ? prev.filter(x => x !== mid) : [...prev, mid]);
  };

  // Reset group picks whose new limits no longer fit when tier changes.
  useEffect(() => {
    if (!pkg) return;
    setPicks(prev => {
      const next: Record<string, string[]> = {};
      for (const g of pkg.choice_groups) {
        const { max } = groupLimits(g);
        const cur = prev[g.group_id] || [];
        next[g.group_id] = cur.slice(0, max);
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tierId]);

  const totalGuests = Math.max(pkg?.min_guests || 1, parseInt(guests, 10) || 0);

  const basePerPerson = activeTier?.per_person_cents ?? (pkg?.price_cents || 0);
  const premiumPerPerson = premium.reduce((s, mid) => {
    const p = pkg?.premium_items.find(x => x.master_item_id === mid);
    return s + (p?.upcharge_per_person_cents || 0);
  }, 0);
  const unitPerPerson = basePerPerson + premiumPerPerson;
  const totalCents = unitPerPerson * totalGuests;

  // Validation
  const isValid = useMemo(() => {
    if (!pkg) return false;
    if (totalGuests < pkg.min_guests) return false;
    for (const g of pkg.choice_groups) {
      const { min, max } = groupLimits(g);
      const n = (picks[g.group_id] || []).length;
      if (n < min || n > max) return false;
    }
    return true;
  }, [pkg, totalGuests, picks, activeTier]);

  const onAdd = async () => {
    if (!pkg || !isValid) return;
    setSubmitting(true);
    try {
      const selection: CateringSelection = {
        tier_id: activeTier?.tier_id,
        group_selections: picks,
        premium_selections: premium,
      };
      const selection_labels = pkg.choice_groups.map(g => ({
        title: g.title,
        items: (picks[g.group_id] || []).map(mid => master[mid]?.name || mid),
      })).filter(s => s.items.length > 0);
      add({
        kind: "catering",
        ref_id: pkg.package_id,
        name: pkg.name,
        price_cents: unitPerPerson,
        image_url: pkg.image_url,
        catering_guest_count: totalGuests,
        catering_selections: selection,
        tier_title: activeTier?.title,
        selection_labels,
      });
      router.replace("/(tabs)/orders");
    } finally {
      setSubmitting(false);
    }
  };

  const submitQuote = async () => {
    if (!pkg) return;
    if (!qName || !qEmail || !qPhone || !qGuests) {
      Alert.alert("Missing info", "Please fill in name, email, phone and guest count.");
      return;
    }
    setSubmitting(true);
    try {
      const r = await api.post<{ ok: boolean; request_id: string }>("/catering/quote-request", {
        package_id: pkg.package_id,
        name: qName, email: qEmail, phone: qPhone,
        guest_count: parseInt(qGuests, 10) || 0,
        event_date: qDate, notes: qNotes,
      });
      if (r.ok) {
        Alert.alert("Quote requested", "We'll get back to you within 24 hours.", [
          { text: "Done", onPress: () => router.back() },
        ]);
      } else {
        Alert.alert("Could not submit", r.error || "Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading || !pkg) {
    return (
      <View style={styles.center}><ActivityIndicator color={colors.primary} size="large" /></View>
    );
  }

  // ============ CUSTOM QUOTE UI ============
  if (pkg.is_custom_quote || quote === "1") {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background }}>
        <Stack.Screen options={{ headerShown: false }} />
        <SafeAreaView edges={["top"]} style={styles.hdr}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="quote-back">
            <Ionicons name="chevron-back" size={22} color={colors.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.hdrTitle}>Custom Quote</Text>
            <Text style={styles.hdrSub} numberOfLines={1}>{pkg.name}</Text>
          </View>
        </SafeAreaView>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={{ flex: 1 }}
        >
          <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 200 }}>
            <View style={styles.quoteHero}>
              <Text style={styles.emoji}>{pkg.emoji}</Text>
              <Text style={styles.quoteHeroTitle}>{pkg.name}</Text>
              {pkg.tagline ? <Text style={styles.quoteHeroSub}>{pkg.tagline}</Text> : null}
              <Text style={styles.quoteHeroMin}>Minimum {pkg.min_guests} guests · Chef-curated</Text>
            </View>

            <Text style={styles.desc}>{pkg.description}</Text>

            <Text style={styles.groupTitle}>Contact details</Text>

            <TextInput style={styles.qInput} placeholder="Your name" placeholderTextColor={colors.textMuted} value={qName} onChangeText={setQName} testID="quote-name" />
            <TextInput style={styles.qInput} placeholder="Email address" placeholderTextColor={colors.textMuted} keyboardType="email-address" autoCapitalize="none" value={qEmail} onChangeText={setQEmail} testID="quote-email" />
            <TextInput style={styles.qInput} placeholder="Phone number" placeholderTextColor={colors.textMuted} keyboardType="phone-pad" value={qPhone} onChangeText={setQPhone} testID="quote-phone" />
            <TextInput style={styles.qInput} placeholder={`Guest count (min ${pkg.min_guests})`} placeholderTextColor={colors.textMuted} keyboardType="number-pad" value={qGuests} onChangeText={t => setQGuests(t.replace(/[^0-9]/g, ""))} testID="quote-guests" />
            <TextInput style={styles.qInput} placeholder="Event date (YYYY-MM-DD)" placeholderTextColor={colors.textMuted} value={qDate} onChangeText={setQDate} testID="quote-date" />
            <TextInput style={[styles.qInput, { height: 110 }]} placeholder="Anything else we should know?" placeholderTextColor={colors.textMuted} value={qNotes} onChangeText={setQNotes} multiline testID="quote-notes" />

            <TouchableOpacity style={[styles.cta, submitting && { opacity: 0.6 }]} disabled={submitting} onPress={submitQuote} testID="quote-submit">
              {submitting ? <ActivityIndicator color="#fff" /> : (
                <>
                  <Ionicons name="paper-plane" size={16} color="#fff" />
                  <Text style={styles.ctaText}>Send Quote Request</Text>
                </>
              )}
            </TouchableOpacity>

            <View style={styles.contactBox}>
              <Text style={styles.contactLabel}>PREFER TO CALL?</Text>
              {pkg.contact_phone ? <Text style={styles.contactVal}>📞 {pkg.contact_phone}</Text> : null}
              {pkg.contact_email ? <Text style={styles.contactVal}>✉️ {pkg.contact_email}</Text> : null}
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </View>
    );
  }

  // ============ STANDARD CUSTOMIZE UI ============
  const sortedGroups = [...pkg.choice_groups].sort((a, b) => (a.display_order || 0) - (b.display_order || 0));
  const includedMasters = pkg.included_master_ids.map(mid => master[mid]).filter(Boolean);

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView edges={["top"]} style={styles.hdr}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="customize-back">
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.hdrTitle} numberOfLines={1}>Customize</Text>
          <Text style={styles.hdrSub} numberOfLines={1}>{pkg.name}</Text>
        </View>
      </SafeAreaView>

      <ScrollView contentContainerStyle={{ paddingBottom: 200 + insets.bottom }} showsVerticalScrollIndicator={false}>
        <Image source={{ uri: mediaUrl(pkg.image_url) }} style={styles.hero} />
        <View style={styles.headBlock}>
          <Text style={styles.emoji}>{pkg.emoji}</Text>
          <Text style={styles.packName}>{pkg.name}</Text>
          {pkg.tagline ? <Text style={styles.packTagline}>{pkg.tagline}</Text> : null}
          {pkg.perfect_for ? <Text style={styles.packPerfect}>{pkg.perfect_for}</Text> : null}
        </View>

        {/* Guest count */}
        <View style={styles.sectionBlock}>
          <Text style={styles.groupTitle}>Guest count</Text>
          <Text style={styles.groupSub}>Minimum {pkg.min_guests} guests</Text>
          <View style={styles.guestRow}>
            <TouchableOpacity
              testID="guests-dec"
              onPress={() => {
                const n = Math.max(pkg.min_guests, (parseInt(guests, 10) || 0) - 5);
                setGuests(String(n));
              }}
              style={styles.stepBtn}
            >
              <Ionicons name="remove" size={20} color={colors.text} />
            </TouchableOpacity>
            <TextInput
              testID="guests-input"
              value={guests}
              onChangeText={t => setGuests(t.replace(/[^0-9]/g, ""))}
              keyboardType="number-pad"
              style={styles.guestInput}
            />
            <TouchableOpacity
              testID="guests-inc"
              onPress={() => setGuests(String((parseInt(guests, 10) || pkg.min_guests) + 5))}
              style={styles.stepBtn}
            >
              <Ionicons name="add" size={20} color={colors.text} />
            </TouchableOpacity>
          </View>
          {totalGuests < pkg.min_guests && (
            <Text style={styles.warn}>Minimum {pkg.min_guests} guests required.</Text>
          )}
        </View>

        {/* Upgrade tiers */}
        {pkg.upgrade_tiers?.length > 1 && (
          <View style={styles.sectionBlock}>
            <Text style={styles.groupTitle}>Choose your tier</Text>
            <View style={{ gap: spacing.sm }}>
              {pkg.upgrade_tiers.map(t => {
                const active = t.tier_id === activeTier?.tier_id;
                return (
                  <TouchableOpacity
                    key={t.tier_id}
                    testID={`tier-${t.tier_id}`}
                    style={[styles.tierRow, active && styles.tierRowActive]}
                    onPress={() => setTierId(t.tier_id)}
                  >
                    <View style={[styles.radio, active && styles.radioActive]}>
                      {active && <View style={styles.radioDot} />}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.tierTitle}>{t.title}</Text>
                      {t.subtitle ? <Text style={styles.tierSub}>{t.subtitle}</Text> : null}
                    </View>
                    <Text style={styles.tierPrice}>{centsToCAD(t.per_person_cents)}/pp</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>
        )}

        {/* Choice groups */}
        {sortedGroups.map(g => {
          const { min, max } = groupLimits(g);
          const cur = picks[g.group_id] || [];
          const complete = cur.length >= min && cur.length <= max;
          return (
            <View key={g.group_id} style={styles.sectionBlock} testID={`group-${g.group_id}`}>
              <View style={styles.groupHead}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.groupTitle}>{g.title}</Text>
                  <Text style={styles.groupSub}>{g.subtitle || `Choose ${min === max ? min : `${min}–${max}`}`}</Text>
                </View>
                <View style={[styles.progressChip, complete && styles.progressChipDone]}>
                  <Text style={[styles.progressText, complete && { color: "#fff" }]}>
                    {cur.length} / {max}
                  </Text>
                </View>
              </View>
              <View style={styles.optionGrid}>
                {g.option_master_ids.map(mid => {
                  const m = master[mid];
                  if (!m) return null;
                  const selected = cur.includes(mid);
                  const premiumRule = pkg.premium_items.find(p => p.master_item_id === mid);
                  return (
                    <TouchableOpacity
                      key={mid}
                      style={[styles.optCard, selected && styles.optCardActive]}
                      onPress={() => togglePick(g, mid)}
                      testID={`option-${g.group_id}-${mid}`}
                    >
                      <Image source={{ uri: mediaUrl(m.image_url) }} style={styles.optImg} />
                      <View style={styles.optInfo}>
                        <View style={styles.optTitleRow}>
                          <VegDot type={m.veg_type} />
                          <Text style={styles.optName} numberOfLines={1}>{m.name}</Text>
                        </View>
                        {premiumRule ? (
                          <Text style={styles.optPremium}>+{centsToCAD(premiumRule.upcharge_per_person_cents)}/pp</Text>
                        ) : (
                          <Text style={styles.optDesc} numberOfLines={2}>{m.short_description}</Text>
                        )}
                      </View>
                      <View style={[styles.check, selected && styles.checkActive]}>
                        {selected && <Ionicons name="checkmark" size={16} color="#fff" />}
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          );
        })}

        {/* Premium add-ons (only if package defines any and none are inside choice groups) */}
        {pkg.premium_items?.length > 0 && (() => {
          // filter items not already in any choice group
          const inGroupIds = new Set<string>();
          pkg.choice_groups.forEach(g => g.option_master_ids.forEach(x => inGroupIds.add(x)));
          const extras = pkg.premium_items.filter(p => !inGroupIds.has(p.master_item_id));
          if (extras.length === 0) return null;
          return (
            <View style={styles.sectionBlock}>
              <Text style={styles.groupTitle}>Premium add-ons</Text>
              <Text style={styles.groupSub}>Optional per-person upgrades</Text>
              {extras.map(p => {
                const m = master[p.master_item_id];
                if (!m) return null;
                const selected = premium.includes(p.master_item_id);
                return (
                  <TouchableOpacity
                    key={p.master_item_id}
                    style={[styles.optCard, selected && styles.optCardActive]}
                    onPress={() => togglePremium(p.master_item_id)}
                    testID={`premium-${p.master_item_id}`}
                  >
                    <Image source={{ uri: m.image_url }} style={styles.optImg} />
                    <View style={styles.optInfo}>
                      <View style={styles.optTitleRow}>
                        <VegDot type={m.veg_type} />
                        <Text style={styles.optName} numberOfLines={1}>{m.name}</Text>
                      </View>
                      <Text style={styles.optPremium}>+{centsToCAD(p.upcharge_per_person_cents)}/pp</Text>
                    </View>
                    <View style={[styles.check, selected && styles.checkActive]}>
                      {selected && <Ionicons name="checkmark" size={16} color="#fff" />}
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          );
        })()}

        {/* Included items */}
        {includedMasters.length > 0 && (
          <View style={styles.sectionBlock}>
            <Text style={styles.groupTitle}>Always included</Text>
            <Text style={styles.groupSub}>Served with every guest — no extra selection needed</Text>
            <View style={styles.includedBox}>
              {includedMasters.map(m => (
                <View key={m.item_id} style={styles.includedRow}>
                  <VegDot type={m.veg_type} />
                  <Text style={styles.includedText}>{m.name}</Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>

      {/* Sticky footer */}
      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.footerLabel}>Package total ({totalGuests} guests)</Text>
          <Text style={styles.footerTotal} testID="cust-total">{centsToCAD(totalCents)}</Text>
          <Text style={styles.footerBreakdown}>
            {centsToCAD(basePerPerson)}
            {premiumPerPerson > 0 ? ` + ${centsToCAD(premiumPerPerson)} premium` : ""}
            {" / person"}
          </Text>
        </View>
        <TouchableOpacity
          testID="cust-add-to-bag"
          style={[styles.addBtn, (!isValid || submitting) && { opacity: 0.5 }]}
          disabled={!isValid || submitting}
          onPress={onAdd}
        >
          {submitting ? <ActivityIndicator color="#fff" /> : (
            <>
              <Ionicons name="bag-add" size={18} color="#fff" />
              <Text style={styles.addBtnText}>Add to Bag</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

function VegDot({ type }: { type: string }) {
  const isVeg = type === "vegetarian";
  const isEgg = type === "eggitarian";
  const border = isVeg ? "#166534" : isEgg ? "#B45309" : "#B91C1C";
  const fill = isVeg ? "#22C55E" : isEgg ? "#F59E0B" : "#EF4444";
  return (
    <View style={{ width: 12, height: 12, borderRadius: 3, borderWidth: 1.5, borderColor: border, alignItems: "center", justifyContent: "center" }}>
      <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: fill }} />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background },
  hdr: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border },
  backBtn: { width: 40, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceAlt },
  hdrTitle: { fontSize: 12, letterSpacing: 3, fontWeight: "800", color: colors.primary },
  hdrSub: { fontSize: 15, fontWeight: "800", color: colors.text, marginTop: 2 },
  hero: { width: "100%", height: 200, backgroundColor: colors.surfaceAlt },
  headBlock: { padding: spacing.lg, gap: 6 },
  emoji: { fontSize: 26 },
  packName: { fontSize: 22, fontWeight: "800", color: colors.text, letterSpacing: -0.3 },
  packTagline: { fontSize: 13, fontStyle: "italic", color: colors.textMuted },
  packPerfect: { fontSize: 12, color: colors.text, fontWeight: "700", marginTop: 4 },
  desc: { color: colors.textMuted, fontSize: 13, lineHeight: 19 },

  sectionBlock: { padding: spacing.lg, gap: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border },
  groupHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  groupTitle: { fontSize: 16, fontWeight: "800", color: colors.text, letterSpacing: -0.2 },
  groupSub: { fontSize: 12, color: colors.textMuted },
  progressChip: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  progressChipDone: { backgroundColor: colors.success },
  progressText: { fontSize: 11, fontWeight: "800", color: colors.text },

  guestRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, justifyContent: "center", marginTop: spacing.sm },
  stepBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  guestInput: { width: 110, height: 58, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, textAlign: "center", fontSize: 26, fontWeight: "800", color: colors.text },
  warn: { color: colors.danger, fontSize: 12, fontWeight: "600", textAlign: "center", marginTop: 4 },

  tierRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  tierRowActive: { borderColor: colors.primary, backgroundColor: "#FFF7F3" },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: colors.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary },
  tierTitle: { fontSize: 14, fontWeight: "800", color: colors.text },
  tierSub: { fontSize: 12, color: colors.textMuted },
  tierPrice: { fontSize: 13, fontWeight: "800", color: colors.primary },

  optionGrid: { gap: spacing.sm },
  optCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  optCardActive: { borderColor: colors.primary, backgroundColor: "#FFF7F3" },
  optImg: { width: 56, height: 56, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt },
  optInfo: { flex: 1, gap: 3 },
  optTitleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  optName: { fontSize: 14, fontWeight: "700", color: colors.text, flex: 1 },
  optDesc: { fontSize: 11, color: colors.textMuted, lineHeight: 14 },
  optPremium: { fontSize: 12, fontWeight: "800", color: colors.secondary },
  check: { width: 26, height: 26, borderRadius: 13, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  checkActive: { backgroundColor: colors.primary, borderColor: colors.primary },

  includedBox: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: spacing.md, gap: 6 },
  includedRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  includedText: { fontSize: 13, color: colors.text, fontWeight: "600" },

  footer: { position: "absolute", bottom: 0, left: 0, right: 0, flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, ...shadows.card },
  footerLabel: { fontSize: 11, color: colors.textMuted, letterSpacing: 1, fontWeight: "700" },
  footerTotal: { fontSize: 22, fontWeight: "800", color: colors.primary, marginTop: 2 },
  footerBreakdown: { fontSize: 11, color: colors.textMuted },
  addBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 22, paddingVertical: 14, borderRadius: radius.pill, ...shadows.soft },
  addBtnText: { color: "#fff", fontSize: 14, fontWeight: "800" },

  // Quote form
  quoteHero: { padding: spacing.lg, borderRadius: radius.lg, backgroundColor: colors.surfaceAlt, gap: 4, alignItems: "flex-start" },
  quoteHeroTitle: { fontSize: 22, fontWeight: "800", color: colors.text, marginTop: 4 },
  quoteHeroSub: { fontSize: 12, fontStyle: "italic", color: colors.textMuted },
  quoteHeroMin: { fontSize: 11, letterSpacing: 2, fontWeight: "800", color: colors.primary, marginTop: 6 },
  qInput: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, fontSize: 14, color: colors.text },
  cta: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.primary, paddingVertical: 16, borderRadius: radius.pill, ...shadows.soft, marginTop: spacing.md },
  ctaText: { color: "#fff", fontSize: 14, fontWeight: "800" },
  contactBox: { padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, gap: 4, marginTop: spacing.sm },
  contactLabel: { fontSize: 10, letterSpacing: 2, fontWeight: "800", color: colors.textMuted },
  contactVal: { fontSize: 14, color: colors.text, fontWeight: "700" },
});
