import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Image,
  TextInput, ScrollView, Modal, Platform, Alert,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";

type MasterItem = {
  item_id: string; name: string; short_description: string; category: string;
  default_price_cents: number; image_url: string; is_active: boolean; veg_type: string;
};

type ChoiceGroup = {
  group_id: string; title: string; subtitle: string;
  min_select: number; max_select: number;
  option_master_ids: string[]; display_order: number;
};

type UpgradeTier = {
  tier_id: string; title: string; subtitle: string;
  per_person_cents: number; is_default: boolean;
  group_overrides: Record<string, { min_select?: number; max_select?: number }>;
};

type PremiumItem = { master_item_id: string; upcharge_per_person_cents: number };

type CateringPackage = {
  package_id: string; name: string; tagline: string; description: string;
  emoji: string; perfect_for: string;
  price_cents: number; min_guests: number; image_url: string;
  includes: string[]; included_master_ids: string[];
  choice_groups: ChoiceGroup[]; upgrade_tiers: UpgradeTier[]; premium_items: PremiumItem[];
  is_custom_quote: boolean; contact_email: string; contact_phone: string;
  is_featured: boolean; is_active: boolean; sort_order: number;
};

const rndId = (prefix: string) => `${prefix}_${Math.random().toString(36).slice(2, 10)}`;

const makeBlank = (): CateringPackage => ({
  package_id: rndId("cat"), name: "", tagline: "", description: "",
  emoji: "🍽️", perfect_for: "",
  price_cents: 2499, min_guests: 10, image_url: "",
  includes: [], included_master_ids: [],
  choice_groups: [], upgrade_tiers: [], premium_items: [],
  is_custom_quote: false, contact_email: "", contact_phone: "",
  is_featured: false, is_active: true, sort_order: 0,
});

export default function AdminCatering() {
  const router = useRouter();
  const [items, setItems] = useState<CateringPackage[]>([]);
  const [master, setMaster] = useState<MasterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [edit, setEdit] = useState<CateringPackage | null>(null);
  const [priceStr, setPriceStr] = useState("");
  const [includesText, setIncludesText] = useState("");

  // Picker modal state
  const [pickerFor, setPickerFor] = useState<
    | { kind: "group"; group_id: string }
    | { kind: "included" }
    | { kind: "premium" }
    | null
  >(null);
  const [pickerSearch, setPickerSearch] = useState("");

  const masterMap = useMemo(() => {
    const m: Record<string, MasterItem> = {};
    master.forEach(x => { m[x.item_id] = x; });
    return m;
  }, [master]);

  const load = useCallback(async () => {
    const [rp, rm] = await Promise.all([
      adminApi.get<CateringPackage[]>("/admin/catering"),
      adminApi.get<MasterItem[]>("/admin/master-menu?active=true"),
    ]);
    if (rp.status === 401 || rm.status === 401) { router.replace("/admin"); return; }
    if (rp.ok) setItems(rp.data || []);
    if (rm.ok) setMaster(rm.data || []);
    setLoading(false);
  }, [router]);

  useEffect(() => {
    (async () => {
      const t = await getAdminToken();
      if (!t) return router.replace("/admin");
      await load();
    })();
  }, [router, load]);

  const openEdit = (p: CateringPackage | null) => {
    const target: CateringPackage = p ? JSON.parse(JSON.stringify(p)) : makeBlank();
    setEdit(target);
    setPriceStr((target.price_cents / 100).toFixed(2));
    setIncludesText(target.includes.join("\n"));
  };

  const save = async () => {
    if (!edit) return;
    if (!edit.name.trim()) { Alert.alert("Missing name", "Please enter a package name."); return; }
    const body: CateringPackage = {
      ...edit,
      price_cents: edit.is_custom_quote ? 0 : Math.round((parseFloat(priceStr) || 0) * 100),
      includes: includesText.split("\n").map(s => s.trim()).filter(Boolean),
    };
    const r = await adminApi.post("/admin/catering", body);
    if (r.ok) { setEdit(null); await load(); }
    else Alert.alert("Save failed", r.error);
  };

  const remove = async (p: CateringPackage) => {
    const ok = Platform.OS === "web" ? window.confirm(`Delete "${p.name}"?`) : true;
    if (!ok) return;
    const r = await adminApi.del(`/admin/catering/${p.package_id}`);
    if (r.ok) await load();
  };

  // ============ choice-group helpers ============
  const addGroup = () => {
    if (!edit) return;
    const g: ChoiceGroup = {
      group_id: rndId("grp"), title: "New group", subtitle: "Choose 1",
      min_select: 1, max_select: 1, option_master_ids: [],
      display_order: edit.choice_groups.length,
    };
    setEdit({ ...edit, choice_groups: [...edit.choice_groups, g] });
  };
  const updGroup = (gid: string, patch: Partial<ChoiceGroup>) => {
    if (!edit) return;
    setEdit({
      ...edit,
      choice_groups: edit.choice_groups.map(g => g.group_id === gid ? { ...g, ...patch } : g),
    });
  };
  const removeGroup = (gid: string) => {
    if (!edit) return;
    setEdit({ ...edit, choice_groups: edit.choice_groups.filter(g => g.group_id !== gid) });
  };

  // ============ tier helpers ============
  const addTier = () => {
    if (!edit) return;
    const t: UpgradeTier = {
      tier_id: rndId("tier"), title: "Tier", subtitle: "", per_person_cents: edit.price_cents,
      is_default: edit.upgrade_tiers.length === 0, group_overrides: {},
    };
    setEdit({ ...edit, upgrade_tiers: [...edit.upgrade_tiers, t] });
  };
  const updTier = (tid: string, patch: Partial<UpgradeTier>) => {
    if (!edit) return;
    setEdit({
      ...edit,
      upgrade_tiers: edit.upgrade_tiers.map(t => t.tier_id === tid ? { ...t, ...patch } : t),
    });
  };
  const removeTier = (tid: string) => {
    if (!edit) return;
    setEdit({ ...edit, upgrade_tiers: edit.upgrade_tiers.filter(t => t.tier_id !== tid) });
  };

  // ============ premium helpers ============
  const updPremium = (mid: string, upcharge_cents: number) => {
    if (!edit) return;
    setEdit({
      ...edit,
      premium_items: edit.premium_items.map(p =>
        p.master_item_id === mid ? { ...p, upcharge_per_person_cents: upcharge_cents } : p),
    });
  };
  const removePremium = (mid: string) => {
    if (!edit) return;
    setEdit({ ...edit, premium_items: edit.premium_items.filter(p => p.master_item_id !== mid) });
  };

  // ============ picker apply ============
  const applyPicker = (ids: string[]) => {
    if (!edit || !pickerFor) return;
    if (pickerFor.kind === "group") {
      updGroup(pickerFor.group_id, { option_master_ids: ids });
    } else if (pickerFor.kind === "included") {
      setEdit({ ...edit, included_master_ids: ids });
    } else if (pickerFor.kind === "premium") {
      const set = new Set(ids);
      const kept = edit.premium_items.filter(p => set.has(p.master_item_id));
      const existing = new Set(kept.map(p => p.master_item_id));
      const added = ids.filter(x => !existing.has(x)).map(x => ({
        master_item_id: x, upcharge_per_person_cents: 400,
      }));
      setEdit({ ...edit, premium_items: [...kept, ...added] });
    }
    setPickerFor(null);
    setPickerSearch("");
  };

  return (
    <AdminShell title="Catering Packages">
      {loading ? <ActivityIndicator color={colors.primary} size="large" /> : (
        <>
          <View style={styles.actionRow}>
            <Text style={styles.count}>{items.length} package{items.length === 1 ? "" : "s"}</Text>
            <TouchableOpacity testID="new-catering-btn" style={styles.primaryBtn} onPress={() => openEdit(null)}>
              <Ionicons name="add" size={16} color="#fff" />
              <Text style={styles.primaryBtnText}>New package</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.grid}>
            {items.map(p => (
              <View key={p.package_id} style={styles.card} testID={`cat-card-${p.package_id}`}>
                {p.image_url ? <Image source={{ uri: p.image_url }} style={styles.img} /> : (
                  <View style={[styles.img, { alignItems: "center", justifyContent: "center" }]}>
                    <Ionicons name="image-outline" size={30} color={colors.textMuted} />
                  </View>
                )}
                <View style={{ flex: 1, padding: spacing.md, gap: 6 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={styles.name}>{p.emoji} {p.name || "Untitled"}</Text>
                    {p.is_featured && <View style={styles.tagFeat}><Text style={styles.tagFeatText}>★</Text></View>}
                    {p.is_custom_quote && <View style={styles.tagCustom}><Text style={styles.tagCustomText}>QUOTE</Text></View>}
                  </View>
                  {p.tagline ? <Text style={styles.tagline}>{p.tagline}</Text> : null}
                  <Text style={styles.pricing}>
                    {p.is_custom_quote ? (
                      <>
                        <Text style={styles.priceStrong}>Custom Quote</Text>
                        <Text>{" "}· min {p.min_guests} guests</Text>
                      </>
                    ) : (
                      <>
                        {p.upgrade_tiers?.length > 0 ? (
                          <Text style={styles.priceStrong}>From CA${(p.upgrade_tiers[0].per_person_cents / 100).toFixed(2)}</Text>
                        ) : (
                          <Text style={styles.priceStrong}>CA${(p.price_cents / 100).toFixed(2)}</Text>
                        )}
                        <Text>{" "}/ person · min {p.min_guests} guests</Text>
                      </>
                    )}
                  </Text>
                  <Text style={styles.chip}>
                    {p.choice_groups?.length || 0} groups · {p.included_master_ids?.length || 0} included · {p.premium_items?.length || 0} premium
                  </Text>
                  <Text style={styles.desc} numberOfLines={2}>{p.description}</Text>
                  <View style={styles.foot}>
                    <TouchableOpacity testID={`edit-cat-${p.package_id}`} style={styles.iconBtn} onPress={() => openEdit(p)}>
                      <Ionicons name="pencil" size={14} color={colors.text} />
                    </TouchableOpacity>
                    <TouchableOpacity testID={`del-cat-${p.package_id}`} style={styles.iconBtn} onPress={() => remove(p)}>
                      <Ionicons name="trash-outline" size={14} color={colors.danger} />
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            ))}
            {items.length === 0 && <Text style={styles.empty}>No catering packages yet.</Text>}
          </View>
        </>
      )}

      {/* ============ Edit Modal ============ */}
      <Modal visible={!!edit} transparent animationType="slide" onRequestClose={() => setEdit(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard} testID="edit-cat-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>{edit?.name ? `Edit — ${edit.name}` : "New package"}</Text>
              <TouchableOpacity onPress={() => setEdit(null)}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>
            {edit && (
              <ScrollView contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.xl }}>
                {/* Basic */}
                <SectionCard title="Basic info">
                  <View style={{ flexDirection: "row", gap: spacing.sm }}>
                    <View style={{ flexBasis: 100 }}>
                      <Text style={styles.label}>Emoji</Text>
                      <TextInput value={edit.emoji} onChangeText={t => setEdit({ ...edit, emoji: t })} style={styles.input} testID="cat-emoji" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>Name</Text>
                      <TextInput value={edit.name} onChangeText={t => setEdit({ ...edit, name: t })} style={styles.input} testID="cat-form-name" />
                    </View>
                  </View>
                  <Field label="Tagline" value={edit.tagline} onChange={t => setEdit({ ...edit, tagline: t })} testID="cat-tagline" />
                  <Field label="Description" value={edit.description} onChange={t => setEdit({ ...edit, description: t })} multiline testID="cat-desc" />
                  <Field label="Perfect for (comma separated)" value={edit.perfect_for} onChange={t => setEdit({ ...edit, perfect_for: t })} testID="cat-perfect" />
                  <Field label="Image URL" value={edit.image_url} onChange={t => setEdit({ ...edit, image_url: t })} testID="cat-image" />
                  <View style={{ flexDirection: "row", gap: spacing.sm }}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>Per-person price (CAD)</Text>
                      <TextInput testID="cat-price" value={priceStr} onChangeText={setPriceStr} keyboardType="decimal-pad" style={styles.input} editable={!edit.is_custom_quote} />
                      {edit.is_custom_quote && <Text style={styles.hint}>Ignored — custom quote packages have no fixed price.</Text>}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>Minimum guests</Text>
                      <TextInput testID="cat-min" value={String(edit.min_guests)} onChangeText={t => setEdit({ ...edit, min_guests: parseInt(t.replace(/[^0-9]/g, ""), 10) || 0 })} keyboardType="number-pad" style={styles.input} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>Sort order</Text>
                      <TextInput value={String(edit.sort_order)} onChangeText={t => setEdit({ ...edit, sort_order: parseInt(t.replace(/[^0-9]/g, ""), 10) || 0 })} keyboardType="number-pad" style={styles.input} />
                    </View>
                  </View>
                  <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                    <ToggleRow label="Custom quote (contact form only)" value={edit.is_custom_quote} onToggle={() => setEdit({ ...edit, is_custom_quote: !edit.is_custom_quote })} testID="cat-custom-quote" />
                    <ToggleRow label="Featured" value={edit.is_featured} onToggle={() => setEdit({ ...edit, is_featured: !edit.is_featured })} testID="cat-featured" />
                    <ToggleRow label="Active" value={edit.is_active} onToggle={() => setEdit({ ...edit, is_active: !edit.is_active })} />
                  </View>
                  {edit.is_custom_quote && (
                    <>
                      <Field label="Contact email" value={edit.contact_email} onChange={t => setEdit({ ...edit, contact_email: t })} />
                      <Field label="Contact phone" value={edit.contact_phone} onChange={t => setEdit({ ...edit, contact_phone: t })} />
                    </>
                  )}
                </SectionCard>

                {/* Sales blurb */}
                <SectionCard title="What's inside (customer summary)">
                  <Text style={styles.hint}>Free-text bullets shown on the package card. One per line.</Text>
                  <TextInput
                    testID="cat-includes"
                    value={includesText}
                    onChangeText={setIncludesText}
                    multiline
                    style={[styles.input, { minHeight: 90 }]}
                    placeholder={"3 Veg + 3 Non-Veg + Dessert\nRice & Salad included"}
                    placeholderTextColor={colors.textMuted}
                  />
                </SectionCard>

                {/* Choice groups */}
                <SectionCard title="Choice groups" right={
                  <TouchableOpacity style={styles.smallBtn} onPress={addGroup} testID="add-group">
                    <Ionicons name="add" size={14} color="#fff" />
                    <Text style={styles.smallBtnText}>Add group</Text>
                  </TouchableOpacity>
                }>
                  {edit.choice_groups.length === 0 && <Text style={styles.hint}>{'No groups yet. Add "Choose Any N" selections for the customer.'}</Text>}
                  {edit.choice_groups.map(g => (
                    <View key={g.group_id} style={styles.groupBox}>
                      <View style={{ flexDirection: "row", gap: spacing.sm }}>
                        <View style={{ flex: 2 }}>
                          <Text style={styles.label}>Title</Text>
                          <TextInput value={g.title} onChangeText={t => updGroup(g.group_id, { title: t })} style={styles.input} testID={`group-${g.group_id}-title`} />
                        </View>
                        <View style={{ flex: 2 }}>
                          <Text style={styles.label}>Subtitle (e.g. Choose Any 3)</Text>
                          <TextInput value={g.subtitle} onChangeText={t => updGroup(g.group_id, { subtitle: t })} style={styles.input} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.label}>Min</Text>
                          <TextInput value={String(g.min_select)} keyboardType="number-pad" onChangeText={t => updGroup(g.group_id, { min_select: parseInt(t.replace(/[^0-9]/g, ""), 10) || 0 })} style={styles.input} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.label}>Max</Text>
                          <TextInput value={String(g.max_select)} keyboardType="number-pad" onChangeText={t => updGroup(g.group_id, { max_select: parseInt(t.replace(/[^0-9]/g, ""), 10) || 0 })} style={styles.input} />
                        </View>
                        <TouchableOpacity onPress={() => removeGroup(g.group_id)} style={[styles.iconBtn, { marginTop: 22 }]} testID={`del-group-${g.group_id}`}>
                          <Ionicons name="trash-outline" size={14} color={colors.danger} />
                        </TouchableOpacity>
                      </View>
                      <View style={{ marginTop: spacing.sm }}>
                        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                          <Text style={styles.label}>Options from Master Menu ({g.option_master_ids.length})</Text>
                          <TouchableOpacity onPress={() => setPickerFor({ kind: "group", group_id: g.group_id })} style={styles.smallBtn}>
                            <Ionicons name="list" size={14} color="#fff" />
                            <Text style={styles.smallBtnText}>Pick items</Text>
                          </TouchableOpacity>
                        </View>
                        <View style={styles.chipRow}>
                          {g.option_master_ids.map(mid => (
                            <View key={mid} style={styles.itemChip}>
                              <Text style={styles.itemChipText}>{masterMap[mid]?.name || mid}</Text>
                            </View>
                          ))}
                          {g.option_master_ids.length === 0 && <Text style={styles.hint}>No items picked yet.</Text>}
                        </View>
                      </View>
                    </View>
                  ))}
                </SectionCard>

                {/* Upgrade tiers */}
                <SectionCard title="Upgrade tiers (optional)" right={
                  <TouchableOpacity style={styles.smallBtn} onPress={addTier}>
                    <Ionicons name="add" size={14} color="#fff" />
                    <Text style={styles.smallBtnText}>Add tier</Text>
                  </TouchableOpacity>
                }>
                  <Text style={styles.hint}>Alternate per-person price tiers (e.g. Base $9 / Upgrade $12). Each tier can override group Min/Max.</Text>
                  {edit.upgrade_tiers.map(t => (
                    <View key={t.tier_id} style={styles.groupBox}>
                      <View style={{ flexDirection: "row", gap: spacing.sm }}>
                        <View style={{ flex: 2 }}>
                          <Text style={styles.label}>Title</Text>
                          <TextInput value={t.title} onChangeText={x => updTier(t.tier_id, { title: x })} style={styles.input} />
                        </View>
                        <View style={{ flex: 2 }}>
                          <Text style={styles.label}>Subtitle</Text>
                          <TextInput value={t.subtitle} onChangeText={x => updTier(t.tier_id, { subtitle: x })} style={styles.input} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.label}>Price CAD</Text>
                          <TextInput value={(t.per_person_cents / 100).toFixed(2)} keyboardType="decimal-pad"
                            onChangeText={x => updTier(t.tier_id, { per_person_cents: Math.round((parseFloat(x) || 0) * 100) })}
                            style={styles.input} />
                        </View>
                        <TouchableOpacity onPress={() => removeTier(t.tier_id)} style={[styles.iconBtn, { marginTop: 22 }]}>
                          <Ionicons name="trash-outline" size={14} color={colors.danger} />
                        </TouchableOpacity>
                      </View>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 }}>
                        <TouchableOpacity onPress={() => {
                          const next = edit.upgrade_tiers.map(x => ({ ...x, is_default: x.tier_id === t.tier_id }));
                          setEdit({ ...edit, upgrade_tiers: next });
                        }} style={[styles.pill, t.is_default && styles.pillActive]}>
                          <Ionicons name={t.is_default ? "checkmark-circle" : "ellipse-outline"} size={14} color={t.is_default ? "#fff" : colors.text} />
                          <Text style={[styles.pillText, t.is_default && { color: "#fff" }]}>Default tier</Text>
                        </TouchableOpacity>
                      </View>
                      {/* Group overrides */}
                      {edit.choice_groups.length > 0 && (
                        <View style={{ marginTop: 8 }}>
                          <Text style={styles.label}>Group overrides for this tier</Text>
                          {edit.choice_groups.map(g => {
                            const ov = t.group_overrides[g.group_id];
                            return (
                              <View key={g.group_id} style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 }}>
                                <Text style={{ flex: 2, fontSize: 12, color: colors.text }}>{g.title}</Text>
                                <TextInput
                                  placeholder={`min ${g.min_select}`}
                                  placeholderTextColor={colors.textMuted}
                                  value={ov?.min_select != null ? String(ov.min_select) : ""}
                                  onChangeText={x => {
                                    const n = x === "" ? undefined : parseInt(x.replace(/[^0-9]/g, ""), 10);
                                    const nov = { ...(ov || {}), min_select: n };
                                    if (nov.min_select == null && nov.max_select == null) {
                                      const { [g.group_id]: _drop, ...rest } = t.group_overrides;
                                      updTier(t.tier_id, { group_overrides: rest });
                                    } else {
                                      updTier(t.tier_id, { group_overrides: { ...t.group_overrides, [g.group_id]: nov } });
                                    }
                                  }}
                                  keyboardType="number-pad"
                                  style={[styles.input, { flex: 1 }]}
                                />
                                <TextInput
                                  placeholder={`max ${g.max_select}`}
                                  placeholderTextColor={colors.textMuted}
                                  value={ov?.max_select != null ? String(ov.max_select) : ""}
                                  onChangeText={x => {
                                    const n = x === "" ? undefined : parseInt(x.replace(/[^0-9]/g, ""), 10);
                                    const nov = { ...(ov || {}), max_select: n };
                                    if (nov.min_select == null && nov.max_select == null) {
                                      const { [g.group_id]: _drop, ...rest } = t.group_overrides;
                                      updTier(t.tier_id, { group_overrides: rest });
                                    } else {
                                      updTier(t.tier_id, { group_overrides: { ...t.group_overrides, [g.group_id]: nov } });
                                    }
                                  }}
                                  keyboardType="number-pad"
                                  style={[styles.input, { flex: 1 }]}
                                />
                              </View>
                            );
                          })}
                        </View>
                      )}
                    </View>
                  ))}
                </SectionCard>

                {/* Always included */}
                <SectionCard title={`Always included (${edit.included_master_ids.length})`} right={
                  <TouchableOpacity style={styles.smallBtn} onPress={() => setPickerFor({ kind: "included" })}>
                    <Ionicons name="list" size={14} color="#fff" />
                    <Text style={styles.smallBtnText}>Pick items</Text>
                  </TouchableOpacity>
                }>
                  <Text style={styles.hint}>Items served with every guest — no selection needed (Rice, Salad, Papad, etc.)</Text>
                  <View style={styles.chipRow}>
                    {edit.included_master_ids.map(mid => (
                      <View key={mid} style={styles.itemChip}>
                        <Text style={styles.itemChipText}>{masterMap[mid]?.name || mid}</Text>
                      </View>
                    ))}
                    {edit.included_master_ids.length === 0 && <Text style={styles.hint}>None.</Text>}
                  </View>
                </SectionCard>

                {/* Premium add-ons */}
                <SectionCard title={`Premium add-ons (${edit.premium_items.length})`} right={
                  <TouchableOpacity style={styles.smallBtn} onPress={() => setPickerFor({ kind: "premium" })}>
                    <Ionicons name="list" size={14} color="#fff" />
                    <Text style={styles.smallBtnText}>Pick items</Text>
                  </TouchableOpacity>
                }>
                  <Text style={styles.hint}>Items customer can add for a per-person upcharge (e.g. Chingri Malaikari +$4/pp).</Text>
                  {edit.premium_items.map(p => (
                    <View key={p.master_item_id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: 6 }}>
                      <Text style={{ flex: 2, fontSize: 13, color: colors.text }}>{masterMap[p.master_item_id]?.name || p.master_item_id}</Text>
                      <View style={{ flex: 1 }}>
                        <TextInput
                          value={(p.upcharge_per_person_cents / 100).toFixed(2)}
                          keyboardType="decimal-pad"
                          onChangeText={x => updPremium(p.master_item_id, Math.round((parseFloat(x) || 0) * 100))}
                          style={styles.input}
                          testID={`premium-${p.master_item_id}-upcharge`}
                        />
                      </View>
                      <TouchableOpacity onPress={() => removePremium(p.master_item_id)} style={styles.iconBtn}>
                        <Ionicons name="trash-outline" size={14} color={colors.danger} />
                      </TouchableOpacity>
                    </View>
                  ))}
                </SectionCard>

                <TouchableOpacity testID="cat-form-save" style={styles.saveBtn} onPress={save}>
                  <Ionicons name="save" size={16} color="#fff" />
                  <Text style={styles.primaryBtnText}>Save package</Text>
                </TouchableOpacity>
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>

      {/* ============ Master Menu Picker ============ */}
      <MasterPickerModal
        visible={!!pickerFor}
        master={master}
        initial={
          !edit || !pickerFor ? [] :
          pickerFor.kind === "group" ? (edit.choice_groups.find(g => g.group_id === pickerFor.group_id)?.option_master_ids || []) :
          pickerFor.kind === "included" ? edit.included_master_ids :
          edit.premium_items.map(p => p.master_item_id)
        }
        title={
          !pickerFor ? "" :
          pickerFor.kind === "group" ? "Pick options for this group" :
          pickerFor.kind === "included" ? "Pick always-included items" :
          "Pick premium items (upcharge)"
        }
        search={pickerSearch}
        setSearch={setPickerSearch}
        onCancel={() => { setPickerFor(null); setPickerSearch(""); }}
        onApply={applyPicker}
      />
    </AdminShell>
  );
}

// ============ Helpers ============

function SectionCard({ title, children, right }: { title: string; children: any; right?: any }) {
  return (
    <View style={styles.section}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {right}
      </View>
      <View style={{ gap: spacing.sm }}>{children}</View>
    </View>
  );
}

function Field({ label, value, onChange, multiline, testID, placeholder }: any) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput testID={testID} value={value} onChangeText={onChange} multiline={multiline}
        style={[styles.input, multiline && { minHeight: 70 }]}
        placeholder={placeholder} placeholderTextColor={colors.textMuted} />
    </View>
  );
}

function ToggleRow({ label, value, onToggle, testID }: { label: string; value: boolean; onToggle: () => void; testID?: string }) {
  return (
    <TouchableOpacity onPress={onToggle} style={[styles.pill, value && styles.pillActive]} testID={testID}>
      <Ionicons name={value ? "checkmark-circle" : "ellipse-outline"} size={16} color={value ? "#fff" : colors.text} />
      <Text style={[styles.pillText, value && { color: "#fff" }]}>{label}</Text>
    </TouchableOpacity>
  );
}

function MasterPickerModal({
  visible, master, initial, title, search, setSearch, onCancel, onApply,
}: {
  visible: boolean; master: MasterItem[]; initial: string[]; title: string;
  search: string; setSearch: (s: string) => void;
  onCancel: () => void; onApply: (ids: string[]) => void;
}) {
  const [sel, setSel] = useState<string[]>(initial);
  useEffect(() => { setSel(initial); }, [initial, visible]);
  const q = search.trim().toLowerCase();
  const filtered = master.filter(m =>
    !q || m.name.toLowerCase().includes(q) || m.category.toLowerCase().includes(q)
  );
  const toggle = (mid: string) => setSel(prev => prev.includes(mid) ? prev.filter(x => x !== mid) : [...prev, mid]);
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.modalOverlay}>
        <View style={[styles.modalCard, { maxWidth: 600 }]}>
          <View style={styles.modalHead}>
            <Text style={styles.modalTitle}>{title}</Text>
            <TouchableOpacity onPress={onCancel}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
          </View>
          <TextInput
            value={search} onChangeText={setSearch}
            placeholder="Search master menu…" placeholderTextColor={colors.textMuted}
            style={[styles.input, { marginBottom: spacing.sm }]}
          />
          <Text style={styles.hint}>{sel.length} selected · {filtered.length} shown · {master.length} total</Text>
          <ScrollView style={{ maxHeight: 400 }} contentContainerStyle={{ gap: 4 }}>
            {filtered.map(m => {
              const on = sel.includes(m.item_id);
              return (
                <TouchableOpacity key={m.item_id} onPress={() => toggle(m.item_id)} style={[styles.pickerRow, on && styles.pickerRowActive]}>
                  {m.image_url ? <Image source={{ uri: m.image_url }} style={styles.pickerImg} /> : <View style={styles.pickerImg} />}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.pickerName}>{m.name}</Text>
                    <Text style={styles.pickerMeta}>{m.category.toUpperCase()} · {m.veg_type} · CA${(m.default_price_cents / 100).toFixed(2)}</Text>
                  </View>
                  <View style={[styles.check, on && styles.checkActive]}>
                    {on && <Ionicons name="checkmark" size={14} color="#fff" />}
                  </View>
                </TouchableOpacity>
              );
            })}
            {filtered.length === 0 && <Text style={styles.empty}>No items match your search.</Text>}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
            <TouchableOpacity onPress={onCancel} style={[styles.ghostBtn, { flex: 1 }]}>
              <Text style={styles.ghostBtnText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => onApply(sel)} style={[styles.primaryBtn, { flex: 1, justifyContent: "center" }]}>
              <Text style={styles.primaryBtnText}>Apply ({sel.length})</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  actionRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  count: { color: colors.textMuted, fontWeight: "600" },
  primaryBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.pill, ...shadows.soft },
  primaryBtnText: { color: "#fff", fontWeight: "800", fontSize: 14 },
  smallBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.primary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill },
  smallBtnText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  ghostBtn: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  ghostBtnText: { color: colors.text, fontWeight: "700" },
  saveBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.pill, marginTop: spacing.md },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.md },
  card: { flexGrow: 1, flexBasis: 320, minWidth: 320, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden", ...shadows.soft },
  img: { width: "100%", height: 140, backgroundColor: colors.surfaceAlt },
  name: { fontSize: 16, fontWeight: "800", color: colors.text, flexShrink: 1 },
  tagline: { color: colors.textMuted, fontSize: 11, fontStyle: "italic" },
  pricing: { color: colors.textMuted, fontSize: 12 },
  priceStrong: { color: colors.primary, fontWeight: "800" },
  chip: { fontSize: 11, color: colors.text, backgroundColor: colors.surfaceAlt, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, alignSelf: "flex-start" },
  desc: { color: colors.textMuted, fontSize: 12, lineHeight: 16 },
  foot: { flexDirection: "row", gap: 6, marginTop: 6 },
  iconBtn: { width: 30, height: 30, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  tagFeat: { backgroundColor: colors.secondary, paddingHorizontal: 5, borderRadius: 4 },
  tagFeatText: { color: "#1a1a1a", fontSize: 10, fontWeight: "900" },
  tagCustom: { backgroundColor: colors.accent, paddingHorizontal: 5, borderRadius: 4 },
  tagCustomText: { color: "#fff", fontSize: 9, fontWeight: "900", letterSpacing: 1 },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl, width: "100%" },

  modalOverlay: { flex: 1, backgroundColor: colors.overlay, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 800, maxHeight: "92%", backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.lg, gap: spacing.sm, ...shadows.card },
  modalHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 20, fontWeight: "800", color: colors.text },

  section: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceAlt },
  sectionTitle: { fontSize: 14, fontWeight: "800", color: colors.text },
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800", marginBottom: 4 },
  hint: { color: colors.textMuted, fontSize: 11, fontStyle: "italic" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14 },
  groupBox: { padding: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surface, gap: 4 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  itemChip: { backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill },
  itemChipText: { color: colors.text, fontSize: 11, fontWeight: "600" },
  pill: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  pillText: { fontSize: 12, color: colors.text, fontWeight: "700" },

  pickerRow: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pickerRowActive: { borderColor: colors.primary, backgroundColor: "#FFF7F3" },
  pickerImg: { width: 40, height: 40, borderRadius: 6, backgroundColor: colors.surfaceAlt },
  pickerName: { fontSize: 13, fontWeight: "700", color: colors.text },
  pickerMeta: { fontSize: 10, color: colors.textMuted, marginTop: 2 },
  check: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  checkActive: { backgroundColor: colors.primary, borderColor: colors.primary },
});
