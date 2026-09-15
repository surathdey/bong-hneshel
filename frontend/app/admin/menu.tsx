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
  cuisine: string; default_price_cents: number; image_url: string; is_active: boolean;
  veg_type: string;
};
type WeeklyLine = {
  line_id: string;
  master_item_id: string;
  price_override_cents?: number | null;
  availability: "available" | "low_inventory" | "sold_out";
  stock_limit?: number | null;
  stock_used?: number;
  is_featured?: boolean;
  display_order?: number;
  is_visible?: boolean;
};
type WeeklyPackage = {
  package_id?: string;
  name: string;
  description?: string;
  price_cents: number;
  pick_count: number;
  eligible_master_ids: string[];
  item_surcharges_cents?: Record<string, number>;   // per-item surcharge in cents
  image_url?: string;
  pricing_mode?: string;               // "flat" | "composition"
  veg_price_cents?: number;
  mixed_price_cents?: number;
  nonveg_price_cents?: number;
  complimentary_master_ids?: string[];
};
type WeeklyMenu = {
  menu_id?: string; week_start: string; week_end?: string; title: string;
  description?: string; lines?: WeeklyLine[]; items?: any[];  // legacy
  status?: string; published?: boolean;
  alacarte_enabled?: boolean;
  package_enabled?: boolean;
  package?: WeeklyPackage | null;
  complimentary_master_ids?: string[];
};

type Section = "alacarte" | "package" | "complimentary" | "always";

const AVAIL: WeeklyLine["availability"][] = ["available", "low_inventory", "sold_out"];

function sundayOf(d: Date): string {
  const day = d.getDay();
  const s = new Date(d); s.setDate(d.getDate() - day);
  return s.toISOString().slice(0, 10);
}

/** Next N Sundays as ISO strings, starting with the current week's Sunday. */
function upcomingSundays(n: number): string[] {
  const base = new Date(sundayOf(new Date()) + "T00:00:00");
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date(base);
    d.setDate(base.getDate() + i * 7);
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

function prettyDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function AdminMenu() {
  const router = useRouter();
  const [menus, setMenus] = useState<WeeklyMenu[]>([]);
  const [master, setMaster] = useState<MasterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("alacarte");

  const [editLine, setEditLine] = useState<WeeklyLine | null>(null);
  // Multi-select set — populated ONLY when opening the "Add dish from Master" modal.
  const [multiPick, setMultiPick] = useState<Set<string>>(new Set());
  const [bulkAdding, setBulkAdding] = useState(false);
  const [priceStr, setPriceStr] = useState("");
  const [addSearch, setAddSearch] = useState("");

  // À la carte visibility search
  const [alacarteSearch, setAlacarteSearch] = useState("");

  // New week form
  const [showNewWeek, setShowNewWeek] = useState(false);
  const [newWeekStart, setNewWeekStart] = useState(sundayOf(new Date()));
  const [newWeekTitle, setNewWeekTitle] = useState("");
  const [newWeekCopyAll, setNewWeekCopyAll] = useState(false);
  const [creatingWeek, setCreatingWeek] = useState(false);

  // Complimentary This Week
  const [compSel, setCompSel] = useState<Set<string>>(new Set());
  const [compSearch, setCompSearch] = useState("");
  const [savingComp, setSavingComp] = useState(false);

  // Always Available (GLOBAL)
  const [alwaysSel, setAlwaysSel] = useState<Set<string>>(new Set());
  const [alwaysSearch, setAlwaysSearch] = useState("");
  const [savingAlways, setSavingAlways] = useState(false);

  // Package config modal state
  const [pkgOpen, setPkgOpen] = useState(false);
  const [pkgDraft, setPkgDraft] = useState<WeeklyPackage>({
    name: "This Week's Combo", description: "", price_cents: 3499, pick_count: 3,
    eligible_master_ids: [], image_url: "",
  });
  const [pkgPriceStr, setPkgPriceStr] = useState("34.99");
  const [pkgPickAll, setPkgPickAll] = useState(true);
  const [pkgSearch, setPkgSearch] = useState("");
  const [pkgMode, setPkgMode] = useState<"flat" | "composition">("flat");
  const [pkgVegStr, setPkgVegStr] = useState("64.99");
  const [pkgMixedStr, setPkgMixedStr] = useState("69.99");
  const [pkgNonvegStr, setPkgNonvegStr] = useState("79.99");
  const [surchargeStrs, setSurchargeStrs] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [m, mm, aa] = await Promise.all([
      adminApi.get<WeeklyMenu[]>("/admin/menus"),
      adminApi.get<MasterItem[]>("/admin/master-menu?active=true"),
      adminApi.get<{ master_ids: string[] }>("/admin/always-available"),
    ]);
    if (m.status === 401) return router.replace("/admin");
    if (m.ok) {
      setMenus(m.data || []);
      if (!selected && m.data && m.data.length > 0) setSelected(m.data[0].week_start);
    }
    if (mm.ok) setMaster(mm.data || []);
    if (aa.ok) setAlwaysSel(new Set(aa.data?.master_ids || []));
    setLoading(false);
  }, [router, selected]);

  useEffect(() => { (async () => {
    const tok = await getAdminToken();
    if (!tok) return router.replace("/admin");
    await load();
  })(); }, [router, load]);

  const current = menus.find(m => m.week_start === selected) || null;
  const lines = current?.lines || [];
  const masterById = useMemo(() => Object.fromEntries(master.map(m => [m.item_id, m])), [master]);
  const masterAlpha = useMemo(
    () => [...master].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase())),
    [master]
  );

  // Sync the Complimentary selection whenever the selected week changes.
  useEffect(() => {
    const wk = menus.find(x => x.week_start === selected);
    const ids = wk?.complimentary_master_ids || wk?.package?.complimentary_master_ids || [];
    setCompSel(new Set(ids));
  }, [selected, menus]);

  const openNewLine = () => {
    setEditLine({
      line_id: `wl_${Math.random().toString(36).slice(2, 12)}`,
      master_item_id: "",
      price_override_cents: null,
      availability: "available",
      stock_limit: null,
      is_featured: false,
      display_order: (lines.length || 0) + 1,
      is_visible: true,
    });
    setPriceStr("");
    setAddSearch("");
    setMultiPick(new Set());
  };

  const openEditLine = (l: WeeklyLine) => {
    setEditLine(l);
    setPriceStr(l.price_override_cents != null ? (l.price_override_cents / 100).toFixed(2) : "");
    setMultiPick(new Set());
  };

  const isAddMode = !!editLine && !editLine.master_item_id && !lines.some(l => l.line_id === editLine.line_id);

  const saveLine = async () => {
    if (!current || !editLine) return;

    if (isAddMode && multiPick.size > 0) {
      setBulkAdding(true);
      const ids = Array.from(multiPick);
      let ok = 0;
      for (let i = 0; i < ids.length; i++) {
        const mid = ids[i];
        const body: WeeklyLine = {
          line_id: `wl_${Math.random().toString(36).slice(2, 12)}`,
          master_item_id: mid,
          price_override_cents: null,
          availability: "available",
          stock_limit: null,
          is_featured: false,
          display_order: (lines.length || 0) + i + 1,
          is_visible: true,
        };
        const r = await adminApi.post(`/admin/menus/${current.week_start}/lines`, { line: body });
        if (r.ok) ok += 1;
      }
      setBulkAdding(false);
      if (ok === 0) Alert.alert("Add failed", "Could not add any dishes.");
      setEditLine(null);
      setMultiPick(new Set());
      await load();
      return;
    }

    if (!editLine.master_item_id) {
      Alert.alert("Pick a dish", "Please select a dish from Master Menu.");
      return;
    }
    const price = priceStr.trim() ? Math.round((parseFloat(priceStr) || 0) * 100) : null;
    const body: WeeklyLine = { ...editLine, price_override_cents: price };
    const r = await adminApi.post(`/admin/menus/${current.week_start}/lines`, { line: body });
    if (r.ok) { setEditLine(null); await load(); }
    else Alert.alert("Save failed", r.error);
  };

  const removeLine = async (l: WeeklyLine) => {
    if (!current) return;
    const ok = Platform.OS === "web" ? window.confirm("Remove this dish from the week?") : true;
    if (!ok) return;
    await adminApi.del(`/admin/menus/${current.week_start}/lines/${l.line_id}`);
    await load();
  };

  const setLineVisibility = async (l: WeeklyLine, vis: boolean) => {
    if (!current) return;
    // optimistic update
    setMenus(prev => prev.map(m => m.week_start === current.week_start
      ? { ...m, lines: (m.lines || []).map(x => x.line_id === l.line_id ? { ...x, is_visible: vis } : x) }
      : m));
    const r = await adminApi.post(`/admin/menus/${current.week_start}/lines/${l.line_id}/visibility`, { is_visible: vis });
    if (!r.ok) { await load(); Alert.alert("Update failed", r.error || ""); }
  };

  const createWeek = async () => {
    setCreatingWeek(true);
    const r = await adminApi.post("/admin/menus/create", {
      week_start: newWeekStart,
      title: newWeekTitle.trim() || undefined,
      copy_all_master: newWeekCopyAll,
    });
    setCreatingWeek(false);
    if (r.ok) {
      setShowNewWeek(false); setNewWeekTitle(""); setNewWeekCopyAll(false);
      await load(); setSelected(newWeekStart);
      setSection("alacarte");
    } else Alert.alert("Create failed", r.error);
  };

  const deleteWeek = async () => {
    if (!current) return;
    const ok = Platform.OS === "web" ? window.confirm(`Delete menu for ${current.week_start}?`) : true;
    if (!ok) return;
    const r = await adminApi.del(`/admin/menus/${current.week_start}`);
    if (r.ok) { setSelected(null); await load(); }
  };

  const patchSettings = async (patch: any) => {
    if (!current) return;
    const r = await adminApi.post(`/admin/menus/${current.week_start}/settings`, patch);
    if (r.ok) await load();
    else Alert.alert("Update failed", r.error || "");
  };

  const toggleAlacarte = async () => {
    if (!current) return;
    const next = !(current.alacarte_enabled ?? true);
    if (!next && !(current.package_enabled ?? false)) {
      Alert.alert("Cannot disable", "At least one of à la carte or package must remain enabled.");
      return;
    }
    await patchSettings({ alacarte_enabled: next });
  };

  const togglePackage = async () => {
    if (!current) return;
    const next = !(current.package_enabled ?? false);
    if (next && !current.package) { openPackageEditor(); return; }
    if (!next && !(current.alacarte_enabled ?? true)) {
      Alert.alert("Cannot disable", "At least one of à la carte or package must remain enabled.");
      return;
    }
    await patchSettings({ package_enabled: next });
  };

  const openPackageEditor = () => {
    if (!current) return;
    const p = current.package || {
      name: "This Week's Combo", description: "", price_cents: 3499, pick_count: 3,
      eligible_master_ids: [], image_url: "",
    };
    setPkgDraft({ ...p, item_surcharges_cents: p.item_surcharges_cents || {} });
    setPkgPriceStr((p.price_cents / 100).toFixed(2));
    setPkgMode((p.pricing_mode as any) === "composition" ? "composition" : "flat");
    setPkgVegStr(((p.veg_price_cents || 6499) / 100).toFixed(2));
    setPkgMixedStr(((p.mixed_price_cents || 6999) / 100).toFixed(2));
    setPkgNonvegStr(((p.nonveg_price_cents || 7999) / 100).toFixed(2));
    setPkgPickAll(!p.eligible_master_ids || p.eligible_master_ids.length === 0);
    setPkgSearch("");
    const initSurcharges: Record<string, string> = {};
    Object.entries(p.item_surcharges_cents || {}).forEach(([mid, c]) => {
      initSurcharges[mid] = ((c as number) / 100).toFixed(2);
    });
    setSurchargeStrs(initSurcharges);
    setPkgOpen(true);
  };

  const savePackage = async () => {
    if (!current) return;
    if (!pkgDraft.name.trim()) { Alert.alert("Missing", "Name is required."); return; }
    const priceCents = Math.round((parseFloat(pkgPriceStr) || 0) * 100);
    const vegC = Math.round((parseFloat(pkgVegStr) || 0) * 100);
    const mixedC = Math.round((parseFloat(pkgMixedStr) || 0) * 100);
    const nonvegC = Math.round((parseFloat(pkgNonvegStr) || 0) * 100);
    if (pkgMode === "composition") {
      if (vegC <= 0 || mixedC <= 0 || nonvegC <= 0) {
        Alert.alert("Invalid pricing", "Set all three prices (Veg / Mixed / Non-Veg)."); return;
      }
    } else if (priceCents <= 0) {
      Alert.alert("Invalid price", "Package price must be greater than 0."); return;
    }
    if (pkgDraft.pick_count <= 0) { Alert.alert("Invalid pick count", "Pick count must be at least 1."); return; }
    const eligible = pkgPickAll ? [] : pkgDraft.eligible_master_ids;
    if (!pkgPickAll && eligible.length < pkgDraft.pick_count) {
      Alert.alert("Not enough eligible items", `You picked ${eligible.length} eligible items but need at least ${pkgDraft.pick_count}.`);
      return;
    }
    const surchargeMap: Record<string, number> = {};
    Object.entries(surchargeStrs).forEach(([mid, s]) => {
      const cents = Math.round((parseFloat(s) || 0) * 100);
      if (cents > 0) surchargeMap[mid] = cents;
    });
    const body = {
      package: {
        ...pkgDraft,
        price_cents: pkgMode === "composition" ? 0 : priceCents,
        eligible_master_ids: eligible,
        item_surcharges_cents: pkgMode === "composition" ? {} : surchargeMap,
        pricing_mode: pkgMode,
        veg_price_cents: vegC,
        mixed_price_cents: mixedC,
        nonveg_price_cents: nonvegC,
        complimentary_master_ids: pkgDraft.complimentary_master_ids || [],
      },
      package_enabled: true,
    };
    const r = await adminApi.post(`/admin/menus/${current.week_start}/settings`, body);
    if (r.ok) { setPkgOpen(false); await load(); }
    else Alert.alert("Save failed", r.error || "");
  };

  const togglePkgEligible = (mid: string) => {
    setPkgDraft(prev => {
      const set = new Set(prev.eligible_master_ids);
      if (set.has(mid)) set.delete(mid); else set.add(mid);
      return { ...prev, eligible_master_ids: Array.from(set) };
    });
  };

  const saveComplimentary = async () => {
    if (!current) return;
    setSavingComp(true);
    const r = await adminApi.post(`/admin/menus/${current.week_start}/complimentary`, { master_ids: Array.from(compSel) });
    setSavingComp(false);
    if (r.ok) await load();
    else Alert.alert("Save failed", r.error || "");
  };

  const saveAlways = async () => {
    setSavingAlways(true);
    const r = await adminApi.post(`/admin/always-available`, { master_ids: Array.from(alwaysSel) });
    setSavingAlways(false);
    if (!r.ok) Alert.alert("Save failed", r.error || "");
  };

  // Master items NOT already added to this week (for the add-line picker).
  const availableMaster = useMemo(() => {
    const q = addSearch.trim().toLowerCase();
    return masterAlpha
      .filter(m => m.item_id === editLine?.master_item_id || !lines.some(l => l.master_item_id === m.item_id))
      .filter(m => !q || m.name.toLowerCase().includes(q) || (m.category || "").toLowerCase().includes(q));
  }, [masterAlpha, editLine, lines, addSearch]);

  // À la carte lines, alphabetical + searched
  const alacarteLines = useMemo(() => {
    const q = alacarteSearch.trim().toLowerCase();
    return [...lines]
      .filter(l => {
        const mi = masterById[l.master_item_id];
        if (!mi) return false;
        return !q || mi.name.toLowerCase().includes(q) || (mi.category || "").toLowerCase().includes(q);
      })
      .sort((a, b) => {
        const na = masterById[a.master_item_id]?.name?.toLowerCase() || "";
        const nb = masterById[b.master_item_id]?.name?.toLowerCase() || "";
        return na.localeCompare(nb);
      });
  }, [lines, masterById, alacarteSearch]);

  const visibleCount = lines.filter(l => l.is_visible !== false).length;

  return (
    <AdminShell title="Weekly Menu">
      {loading ? <ActivityIndicator color={colors.primary} size="large" /> : (
        <>
          <View style={styles.headRow}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
              {menus.map(m => {
                const active = selected === m.week_start;
                const count = (m.lines?.length || 0) + (m.items?.length || 0);
                return (
                  <TouchableOpacity key={m.week_start} testID={`week-tab-${m.week_start}`}
                    onPress={() => setSelected(m.week_start)}
                    style={[styles.weekTab, active && styles.weekTabActive]}>
                    <Text style={[styles.weekTabDate, active && { color: "#fff" }]}>{m.week_start}</Text>
                    <Text style={[styles.weekTabTitle, active && { color: "rgba(255,255,255,0.85)" }]} numberOfLines={1}>{m.title}</Text>
                    <Text style={[styles.weekTabCount, active && { color: colors.secondary }]}>{count} items</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
            <TouchableOpacity testID="new-week-btn" style={styles.newBtn} onPress={() => { setNewWeekStart(sundayOf(new Date())); setShowNewWeek(true); }}>
              <Ionicons name="add" size={18} color="#fff" />
              <Text style={styles.newBtnText}>New week</Text>
            </TouchableOpacity>
          </View>

          {current ? (
            <>
              <View style={styles.currentBar}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.currentDate}>WEEK OF {current.week_start}</Text>
                  <Text style={styles.currentTitle}>{current.title}</Text>
                </View>
                <TouchableOpacity testID="delete-week-btn" style={styles.dangerBtn} onPress={deleteWeek}>
                  <Ionicons name="trash-outline" size={16} color={colors.danger} />
                </TouchableOpacity>
              </View>

              {/* Section switcher — the 4 weekly-configuration sections */}
              <View style={styles.sectionTabs}>
                {([
                  { key: "alacarte", label: "À la carte", icon: "restaurant-outline" },
                  { key: "package", label: "Weekly Package", icon: "gift-outline" },
                  { key: "complimentary", label: "Complimentary This Week", icon: "sparkles-outline" },
                  { key: "always", label: "Always Available", icon: "time-outline" },
                ] as { key: Section; label: string; icon: any }[]).map(t => {
                  const on = section === t.key;
                  return (
                    <TouchableOpacity key={t.key} testID={`section-${t.key}`}
                      style={[styles.sectionTab, on && styles.sectionTabOn]} onPress={() => setSection(t.key)}>
                      <Ionicons name={t.icon} size={15} color={on ? "#fff" : colors.text} />
                      <Text style={[styles.sectionTabText, on && { color: "#fff" }]}>{t.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* ===================== À LA CARTE ===================== */}
              {section === "alacarte" && (
                <View style={{ gap: spacing.md }}>
                  <View style={styles.modeCard}>
                    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.modeTitle}>À la carte</Text>
                        <Text style={styles.modeHint}>{visibleCount} of {lines.length} dishes visible to customers this week.</Text>
                      </View>
                      <TouchableOpacity testID="toggle-alacarte" style={[styles.pill, (current.alacarte_enabled ?? true) ? styles.pillOn : styles.pillOff]} onPress={toggleAlacarte}>
                        <Ionicons name={(current.alacarte_enabled ?? true) ? "eye" : "eye-off"} size={14} color={(current.alacarte_enabled ?? true) ? "#fff" : colors.text} />
                        <Text style={[styles.pillText, (current.alacarte_enabled ?? true) && { color: "#fff" }]}>{(current.alacarte_enabled ?? true) ? "Shown" : "Hidden"}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>

                  <View style={styles.searchRow}>
                    <View style={styles.searchBox}>
                      <Ionicons name="search" size={16} color={colors.textMuted} />
                      <TextInput testID="alacarte-search" value={alacarteSearch} onChangeText={setAlacarteSearch}
                        placeholder="Search dishes…" placeholderTextColor={colors.textMuted} style={styles.searchInput} />
                    </View>
                    <TouchableOpacity testID="add-item-btn" style={styles.addItemBtn} onPress={openNewLine}>
                      <Ionicons name="add" size={16} color="#fff" />
                      <Text style={styles.addItemBtnText}>Add dish</Text>
                    </TouchableOpacity>
                  </View>

                  <View style={styles.grid}>
                    {alacarteLines.map(l => {
                      const mi = masterById[l.master_item_id];
                      const price = l.price_override_cents ?? mi?.default_price_cents ?? 0;
                      const overridden = l.price_override_cents != null && mi && l.price_override_cents !== mi.default_price_cents;
                      const stockText = l.stock_limit != null ? `${l.stock_used || 0}/${l.stock_limit} sold` : null;
                      const vis = l.is_visible !== false;
                      return (
                        <View key={l.line_id} style={[styles.itemCard, !vis && styles.itemCardHidden]} testID={`admin-line-${l.line_id}`}>
                          {mi?.image_url ? <Image source={{ uri: mi.image_url }} style={styles.itemImg} /> :
                            <View style={[styles.itemImg, { alignItems: "center", justifyContent: "center" }]}>
                              <Ionicons name="image-outline" size={30} color={colors.textMuted} />
                            </View>}
                          <View style={{ padding: spacing.md, gap: 4 }}>
                            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                              <Text style={styles.itemName} numberOfLines={1}>{mi?.name || "(missing master)"}</Text>
                              {l.is_featured && <View style={styles.tagFeat}><Text style={styles.tagFeatText}>★</Text></View>}
                              {l.availability === "sold_out" && <View style={[styles.tag, { backgroundColor: colors.danger }]}><Text style={styles.tagText}>SOLD OUT</Text></View>}
                              {l.availability === "low_inventory" && <View style={[styles.tag, { backgroundColor: colors.secondary }]}><Text style={[styles.tagText, { color: "#1a1a1a" }]}>LOW</Text></View>}
                            </View>
                            <Text style={styles.itemCat}>{mi?.category} · {mi?.cuisine}</Text>
                            <View style={styles.itemFoot}>
                              <View>
                                <Text style={styles.itemPrice}>CA${(price / 100).toFixed(2)}</Text>
                                {overridden && mi && (
                                  <Text style={styles.priceStrike}>was CA${(mi.default_price_cents / 100).toFixed(2)}</Text>
                                )}
                                {stockText && <Text style={styles.stockLine}>{stockText}</Text>}
                              </View>
                              <View style={{ flexDirection: "row", gap: 6 }}>
                                <TouchableOpacity testID={`edit-line-${l.line_id}`} onPress={() => openEditLine(l)} style={styles.iconBtn}>
                                  <Ionicons name="pencil" size={14} color={colors.text} />
                                </TouchableOpacity>
                                <TouchableOpacity testID={`del-line-${l.line_id}`} onPress={() => removeLine(l)} style={styles.iconBtn}>
                                  <Ionicons name="trash-outline" size={14} color={colors.danger} />
                                </TouchableOpacity>
                              </View>
                            </View>
                            {/* Visibility toggle */}
                            <TouchableOpacity testID={`vis-toggle-${l.line_id}`} onPress={() => setLineVisibility(l, !vis)}
                              style={[styles.visToggle, vis ? styles.visOn : styles.visOff]}>
                              <Ionicons name={vis ? "eye" : "eye-off"} size={14} color={vis ? "#fff" : colors.text} />
                              <Text style={[styles.visToggleText, vis && { color: "#fff" }]}>{vis ? "Visible to customers" : "Hidden — tap to show"}</Text>
                            </TouchableOpacity>
                          </View>
                        </View>
                      );
                    })}
                    {alacarteLines.length === 0 && (
                      <Text style={styles.empty}>{lines.length === 0 ? "No dishes yet. Add dishes, or create a new week with \u201cCopy all Master items\u201d." : "No dishes match your search."}</Text>
                    )}
                  </View>
                </View>
              )}

              {/* ===================== WEEKLY PACKAGE ===================== */}
              {section === "package" && (
                <View style={styles.modeCard}>
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.modeTitle}>Weekly Package</Text>
                      <Text style={styles.modeHint}>Customer picks X dishes for a flat or veg/non-veg price.</Text>
                    </View>
                    <TouchableOpacity testID="toggle-package" style={[styles.pill, (current.package_enabled ?? false) ? styles.pillOn : styles.pillOff]} onPress={togglePackage}>
                      <Ionicons name={(current.package_enabled ?? false) ? "eye" : "eye-off"} size={14} color={(current.package_enabled ?? false) ? "#fff" : colors.text} />
                      <Text style={[styles.pillText, (current.package_enabled ?? false) && { color: "#fff" }]}>{(current.package_enabled ?? false) ? "Shown" : "Hidden"}</Text>
                    </TouchableOpacity>
                  </View>
                  {current.package ? (
                    <View style={styles.pkgSummary}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.pkgSummaryTitle}>{current.package.name}</Text>
                        <Text style={styles.pkgSummarySub}>
                          Pick {current.package.pick_count} · {current.package.pricing_mode === "composition" ? "veg / non-veg pricing" : `CA$${(current.package.price_cents / 100).toFixed(2)}`} · {current.package.eligible_master_ids?.length ? `${current.package.eligible_master_ids.length} eligible dishes` : "all dishes eligible"}
                        </Text>
                        {current.package.description ? <Text style={styles.pkgSummaryDesc}>{current.package.description}</Text> : null}
                      </View>
                      <TouchableOpacity testID="edit-pkg-btn" style={styles.pkgEditBtn} onPress={openPackageEditor}>
                        <Ionicons name="pencil" size={14} color="#fff" />
                        <Text style={styles.pkgEditBtnText}>Edit package</Text>
                      </TouchableOpacity>
                    </View>
                  ) : (
                    <TouchableOpacity testID="config-pkg-btn" style={styles.pkgEditBtn} onPress={openPackageEditor}>
                      <Ionicons name="add" size={14} color="#fff" />
                      <Text style={styles.pkgEditBtnText}>Configure package</Text>
                    </TouchableOpacity>
                  )}
                </View>
              )}

              {/* ===================== COMPLIMENTARY THIS WEEK ===================== */}
              {section === "complimentary" && (
                <View style={{ gap: spacing.md }}>
                  <View style={styles.modeCard}>
                    <Text style={styles.modeTitle}>Complimentary This Week</Text>
                    <Text style={styles.modeHint}>Pick free dishes from the Master Menu. Shown to customers with the Weekly Meal Plan.</Text>
                    {!(current.package_enabled ?? false) && (
                      <View style={styles.warnRow}>
                        <Ionicons name="information-circle" size={15} color={colors.secondary} />
                        <Text style={styles.warnText}>These only appear on the customer app while the Weekly Package is enabled.</Text>
                      </View>
                    )}
                  </View>
                  <MasterMultiSelect
                    testIDPrefix="comp"
                    data={masterAlpha}
                    selected={compSel}
                    search={compSearch}
                    setSearch={setCompSearch}
                    onToggle={(mid) => setCompSel(prev => { const n = new Set(prev); n.has(mid) ? n.delete(mid) : n.add(mid); return n; })}
                  />
                  <TouchableOpacity testID="comp-save" style={[styles.primaryBtn, savingComp && { opacity: 0.7 }]} disabled={savingComp} onPress={saveComplimentary}>
                    {savingComp ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Save complimentary dishes ({compSel.size})</Text>}
                  </TouchableOpacity>
                </View>
              )}

              {/* ===================== ALWAYS AVAILABLE (GLOBAL) ===================== */}
              {section === "always" && (
                <View style={{ gap: spacing.md }}>
                  <View style={styles.modeCard}>
                    <Text style={styles.modeTitle}>Always Available (global)</Text>
                    <Text style={styles.modeHint}>One global list, shown on every week under &ldquo;Always Available&rdquo; on the customer home &amp; menu. Pick dishes from the Master Menu — changes go live instantly.</Text>
                  </View>
                  <MasterMultiSelect
                    testIDPrefix="always"
                    data={masterAlpha}
                    selected={alwaysSel}
                    search={alwaysSearch}
                    setSearch={setAlwaysSearch}
                    onToggle={(mid) => setAlwaysSel(prev => { const n = new Set(prev); n.has(mid) ? n.delete(mid) : n.add(mid); return n; })}
                  />
                  <TouchableOpacity testID="always-save" style={[styles.primaryBtn, savingAlways && { opacity: 0.7 }]} disabled={savingAlways} onPress={saveAlways}>
                    {savingAlways ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Save Always Available ({alwaysSel.size})</Text>}
                  </TouchableOpacity>
                </View>
              )}
            </>
          ) : (
            <View style={styles.emptyState}>
              <Ionicons name="calendar-outline" size={40} color={colors.textMuted} />
              <Text style={styles.empty}>No weekly menu selected. Create one to get started.</Text>
            </View>
          )}
        </>
      )}

      {/* Edit / Add line modal */}
      <Modal visible={!!editLine} transparent animationType="slide" onRequestClose={() => setEditLine(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard} testID="edit-line-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>{isAddMode ? `Add dishes to week${multiPick.size ? ` · ${multiPick.size} selected` : ""}` : "Edit weekly dish"}</Text>
              <TouchableOpacity onPress={() => setEditLine(null)}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>
            {editLine && (
              <ScrollView contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.md }}>
                <View>
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                    <Text style={styles.label}>{isAddMode ? "Select one or more dishes" : "Pick a dish from Master Menu"}</Text>
                    {isAddMode && multiPick.size > 0 && (
                      <TouchableOpacity onPress={() => setMultiPick(new Set())}>
                        <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: "700" }}>Clear ({multiPick.size})</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                  <View style={styles.searchBox}>
                    <Ionicons name="search" size={16} color={colors.textMuted} />
                    <TextInput testID="add-line-search" value={addSearch} onChangeText={setAddSearch}
                      placeholder="Search Master Menu…" placeholderTextColor={colors.textMuted} style={styles.searchInput} />
                  </View>
                  <ScrollView style={styles.pickerBox} contentContainerStyle={{ padding: 4 }} testID="line-master-picker">
                    {availableMaster.length === 0 ? (
                      <Text style={styles.emptyPicker}>No dishes found.</Text>
                    ) : (
                      availableMaster.map(mi => {
                        const singleActive = !isAddMode && editLine.master_item_id === mi.item_id;
                        const multiChecked = isAddMode && multiPick.has(mi.item_id);
                        const active = singleActive || multiChecked;
                        return (
                          <TouchableOpacity
                            key={mi.item_id}
                            testID={`line-pick-${mi.item_id}`}
                            onPress={() => {
                              if (isAddMode) {
                                setMultiPick(prev => {
                                  const nx = new Set(prev);
                                  if (nx.has(mi.item_id)) nx.delete(mi.item_id); else nx.add(mi.item_id);
                                  return nx;
                                });
                              } else {
                                setEditLine({ ...editLine, master_item_id: mi.item_id });
                              }
                            }}
                            style={[styles.pickerRow, active && styles.pickerRowActive]}
                          >
                            {isAddMode && (
                              <Ionicons name={multiChecked ? "checkbox" : "square-outline"} size={22}
                                color={multiChecked ? colors.primary : colors.textMuted} style={{ marginRight: 4 }} />
                            )}
                            {mi.image_url ? <Image source={{ uri: mi.image_url }} style={styles.pickerThumb} /> :
                              <View style={[styles.pickerThumb, { alignItems: "center", justifyContent: "center" }]}>
                                <Ionicons name="image-outline" size={18} color={colors.textMuted} />
                              </View>}
                            <View style={{ flex: 1 }}>
                              <Text style={styles.pickerName}>{mi.name}</Text>
                              <Text style={styles.pickerMeta}>{mi.category} · {mi.cuisine} · CA${(mi.default_price_cents / 100).toFixed(2)}</Text>
                            </View>
                            {singleActive && <Ionicons name="checkmark-circle" size={22} color={colors.primary} />}
                          </TouchableOpacity>
                        );
                      })
                    )}
                  </ScrollView>
                </View>

                {!isAddMode && (
                  <>
                    <View>
                      <Text style={styles.label}>Weekly price override (CAD) — optional</Text>
                      <TextInput testID="line-price-override" value={priceStr} onChangeText={setPriceStr}
                        placeholder={editLine.master_item_id ? `Default: CA$${((masterById[editLine.master_item_id]?.default_price_cents || 0) / 100).toFixed(2)}` : "0.00"}
                        placeholderTextColor={colors.textMuted} keyboardType="decimal-pad" style={styles.input} />
                      <Text style={styles.helper}>Leave blank to use the Master Menu default price.</Text>
                    </View>
                    <View>
                      <Text style={styles.label}>Availability</Text>
                      <View style={{ flexDirection: "row", gap: 6 }}>
                        {AVAIL.map(a => (
                          <TouchableOpacity key={a} testID={`line-avail-${a}`} onPress={() => setEditLine({ ...editLine, availability: a })}
                            style={[styles.chip, editLine.availability === a && styles.chipActive]}>
                            <Text style={[styles.chipText, editLine.availability === a && styles.chipTextActive]}>{a.replace("_", " ")}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                    <View>
                      <Text style={styles.label}>Stock limit (optional)</Text>
                      <TextInput testID="line-stock-limit"
                        value={editLine.stock_limit != null ? String(editLine.stock_limit) : ""}
                        onChangeText={t => setEditLine({ ...editLine, stock_limit: t ? parseInt(t.replace(/[^0-9]/g, ""), 10) || 0 : null })}
                        keyboardType="number-pad" placeholder="e.g. 50" placeholderTextColor={colors.textMuted} style={styles.input} />
                      <Text style={styles.helper}>Automatically flips to Sold Out once the limit is reached.</Text>
                    </View>
                    <TouchableOpacity testID="line-featured-toggle" onPress={() => setEditLine({ ...editLine, is_featured: !editLine.is_featured })} style={styles.toggleRow}>
                      <Ionicons name={editLine.is_featured ? "star" : "star-outline"} size={20} color={editLine.is_featured ? colors.secondary : colors.textMuted} />
                      <Text style={styles.toggleText}>Feature on Home this week</Text>
                    </TouchableOpacity>
                  </>
                )}

                {isAddMode && (
                  <Text style={styles.helper}>New dishes are visible by default. Fine-tune price, availability, stock and featured status after adding.</Text>
                )}

                <TouchableOpacity testID="line-save" style={[styles.primaryBtn, bulkAdding && { opacity: 0.7 }]} disabled={bulkAdding} onPress={saveLine}>
                  {bulkAdding
                    ? <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}><ActivityIndicator color="#fff" /><Text style={styles.primaryBtnText}>Adding…</Text></View>
                    : <Text style={styles.primaryBtnText}>{isAddMode ? (multiPick.size > 1 ? `Add ${multiPick.size} dishes to week` : "Add to week") : "Save to week"}</Text>}
                </TouchableOpacity>
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>

      {/* New week modal */}
      <Modal visible={showNewWeek} transparent animationType="slide" onRequestClose={() => setShowNewWeek(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard} testID="new-week-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>New week</Text>
              <TouchableOpacity onPress={() => setShowNewWeek(false)}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.md }}>
              <View>
                <Text style={styles.label}>Week date (pick a Sunday) *</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
                  {upcomingSundays(8).map(iso => {
                    const on = newWeekStart === iso;
                    const taken = menus.some(m => m.week_start === iso);
                    return (
                      <TouchableOpacity key={iso} testID={`new-week-date-${iso}`} disabled={taken}
                        onPress={() => setNewWeekStart(iso)}
                        style={[styles.dateChip, on && styles.dateChipOn, taken && styles.dateChipTaken]}>
                        <Text style={[styles.dateChipText, on && { color: "#fff" }]}>{prettyDate(iso)}</Text>
                        {taken && <Text style={styles.dateChipTakenText}>exists</Text>}
                      </TouchableOpacity>
                    );
                  })}
                </ScrollView>
                <TextInput testID="new-week-date" value={newWeekStart} onChangeText={setNewWeekStart}
                  style={[styles.input, { marginTop: 6 }]} placeholder="YYYY-MM-DD" placeholderTextColor={colors.textMuted} />
              </View>
              <View>
                <Text style={styles.label}>Week name (optional)</Text>
                <TextInput testID="new-week-title" value={newWeekTitle} onChangeText={setNewWeekTitle} style={styles.input}
                  placeholder={`Week of ${newWeekStart}`} placeholderTextColor={colors.textMuted} />
              </View>
              <TouchableOpacity testID="new-week-copyall" style={styles.checkboxRow} onPress={() => setNewWeekCopyAll(v => !v)}>
                <Ionicons name={newWeekCopyAll ? "checkbox" : "square-outline"} size={22} color={newWeekCopyAll ? colors.primary : colors.textMuted} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.toggleText}>Copy all active Master Menu items to À la carte</Text>
                  <Text style={styles.helper}>They&rsquo;re added hidden — turn on the ones you want customers to see this week.</Text>
                </View>
              </TouchableOpacity>
              <TouchableOpacity testID="new-week-save" style={[styles.primaryBtn, creatingWeek && { opacity: 0.7 }]} disabled={creatingWeek} onPress={createWeek}>
                {creatingWeek ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Create week</Text>}
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Package Config Modal */}
      <Modal visible={pkgOpen} transparent animationType="slide" onRequestClose={() => setPkgOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={[styles.modalCard, { maxWidth: 640 }]} testID="pkg-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>Weekly Package</Text>
              <TouchableOpacity onPress={() => setPkgOpen(false)}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.md }}>
              <View>
                <Text style={styles.label}>Package name</Text>
                <TextInput testID="pkg-name" value={pkgDraft.name} onChangeText={t => setPkgDraft({ ...pkgDraft, name: t })} style={styles.input} placeholder="This Week's Combo" placeholderTextColor={colors.textMuted} />
              </View>
              <View>
                <Text style={styles.label}>Description (shown on customer card)</Text>
                <TextInput testID="pkg-desc" value={pkgDraft.description || ""} onChangeText={t => setPkgDraft({ ...pkgDraft, description: t })} multiline style={[styles.input, { minHeight: 60 }]} />
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Number of items (X)</Text>
                  <TextInput testID="pkg-pick" value={String(pkgDraft.pick_count)} keyboardType="number-pad"
                    onChangeText={t => setPkgDraft({ ...pkgDraft, pick_count: Math.max(1, parseInt(t.replace(/[^0-9]/g, ""), 10) || 1) })}
                    style={styles.input} />
                </View>
                {pkgMode === "flat" && (
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Package price (CAD)</Text>
                    <TextInput testID="pkg-price" value={pkgPriceStr} keyboardType="decimal-pad" onChangeText={setPkgPriceStr} style={styles.input} />
                  </View>
                )}
              </View>

              <Text style={styles.label}>Pricing mode</Text>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <TouchableOpacity testID="pkg-mode-flat" style={[styles.chip, pkgMode === "flat" && styles.chipActive]} onPress={() => setPkgMode("flat")}>
                  <Text style={[styles.chipText, pkgMode === "flat" && styles.chipTextActive]}>Flat price</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pkg-mode-composition" style={[styles.chip, pkgMode === "composition" && styles.chipActive]} onPress={() => setPkgMode("composition")}>
                  <Text style={[styles.chipText, pkgMode === "composition" && styles.chipTextActive]}>By veg / non-veg mix</Text>
                </TouchableOpacity>
              </View>

              {pkgMode === "composition" && (
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>All Veg (CAD)</Text>
                    <TextInput testID="pkg-price-veg" value={pkgVegStr} keyboardType="decimal-pad" onChangeText={setPkgVegStr} style={styles.input} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Mixed (CAD)</Text>
                    <TextInput testID="pkg-price-mixed" value={pkgMixedStr} keyboardType="decimal-pad" onChangeText={setPkgMixedStr} style={styles.input} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>All Non-Veg (CAD)</Text>
                    <TextInput testID="pkg-price-nonveg" value={pkgNonvegStr} keyboardType="decimal-pad" onChangeText={setPkgNonvegStr} style={styles.input} />
                  </View>
                </View>
              )}
              <View>
                <Text style={styles.label}>Image URL (optional)</Text>
                <TextInput value={pkgDraft.image_url || ""} onChangeText={t => setPkgDraft({ ...pkgDraft, image_url: t })} style={styles.input} placeholder="https://…" placeholderTextColor={colors.textMuted} />
              </View>
              <View>
                <Text style={styles.label}>Eligible items</Text>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  <TouchableOpacity testID="pkg-eligible-all" style={[styles.chip, pkgPickAll && styles.chipActive]} onPress={() => setPkgPickAll(true)}>
                    <Text style={[styles.chipText, pkgPickAll && styles.chipTextActive]}>Any dish</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="pkg-eligible-custom" style={[styles.chip, !pkgPickAll && styles.chipActive]} onPress={() => setPkgPickAll(false)}>
                    <Text style={[styles.chipText, !pkgPickAll && styles.chipTextActive]}>Pick specific dishes</Text>
                  </TouchableOpacity>
                </View>
                {!pkgPickAll && (
                  <View style={{ marginTop: spacing.sm }}>
                    <Text style={styles.helper}>Selected: {pkgDraft.eligible_master_ids.length} dishes. All Master Menu dishes shown below (A→Z).</Text>
                    <View style={styles.searchBox}>
                      <Ionicons name="search" size={16} color={colors.textMuted} />
                      <TextInput testID="pkg-eligible-search" value={pkgSearch} onChangeText={setPkgSearch}
                        placeholder="Search dishes…" placeholderTextColor={colors.textMuted} style={styles.searchInput} />
                    </View>
                    <View style={styles.pickerBox}>
                      <ScrollView contentContainerStyle={{ padding: 4 }}>
                        {masterAlpha
                          .filter(mi => { const q = pkgSearch.trim().toLowerCase(); return !q || mi.name.toLowerCase().includes(q) || (mi.category || "").toLowerCase().includes(q); })
                          .map(mi => {
                            const on = pkgDraft.eligible_master_ids.includes(mi.item_id);
                            return (
                              <TouchableOpacity key={mi.item_id} style={[styles.pickerRow, on && styles.pickerRowActive]} onPress={() => togglePkgEligible(mi.item_id)} testID={`pkg-elig-${mi.item_id}`}>
                                {mi.image_url ? <Image source={{ uri: mi.image_url }} style={styles.pickerThumb} /> : <View style={styles.pickerThumb} />}
                                <View style={{ flex: 1 }}>
                                  <Text style={styles.pickerName}>{mi.name}</Text>
                                  <Text style={styles.pickerMeta}>{mi.category} · CA${(mi.default_price_cents / 100).toFixed(2)}</Text>
                                </View>
                                {on && <Ionicons name="checkmark-circle" size={22} color={colors.primary} />}
                              </TouchableOpacity>
                            );
                          })}
                      </ScrollView>
                    </View>
                  </View>
                )}
              </View>

              <View>
                <Text style={styles.label}>Per-item surcharge (optional)</Text>
                <Text style={styles.helper}>
                  Add extra CAD on top of the combo price when a customer picks certain premium items (e.g. Mutton +$5). Applied per portion.
                </Text>
                <View style={[styles.pickerBox, { marginTop: 6 }]}>
                  <ScrollView contentContainerStyle={{ padding: 4 }}>
                    {(() => {
                      const eligIds = pkgPickAll ? lines.map(l => l.master_item_id) : pkgDraft.eligible_master_ids;
                      const rows = eligIds.map(id => masterById[id]).filter(Boolean)
                        .sort((a: any, b: any) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
                      if (rows.length === 0) {
                        return <Text style={styles.emptyPicker}>Select eligible items first to configure surcharges.</Text>;
                      }
                      return rows.map((mi: any) => {
                        const val = surchargeStrs[mi.item_id] ?? "";
                        return (
                          <View key={`sur-${mi.item_id}`} style={styles.pickerRow} testID={`pkg-surcharge-${mi.item_id}`}>
                            {mi.image_url ? <Image source={{ uri: mi.image_url }} style={styles.pickerThumb} /> : <View style={styles.pickerThumb} />}
                            <View style={{ flex: 1 }}>
                              <Text style={styles.pickerName}>{mi.name}</Text>
                              <Text style={styles.pickerMeta}>+ CA$ per portion</Text>
                            </View>
                            <TextInput value={val} onChangeText={t => setSurchargeStrs(s => ({ ...s, [mi.item_id]: t }))}
                              placeholder="0.00" placeholderTextColor={colors.textMuted} keyboardType="decimal-pad"
                              style={[styles.input, { width: 90, textAlign: "right" }]} />
                          </View>
                        );
                      });
                    })()}
                  </ScrollView>
                </View>
              </View>

              <TouchableOpacity testID="pkg-save" style={styles.primaryBtn} onPress={savePackage}>
                <Text style={styles.primaryBtnText}>Save package</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </AdminShell>
  );
}

/** Reusable Master-Menu multi-select with search (A→Z). */
function MasterMultiSelect({
  data, selected, search, setSearch, onToggle, testIDPrefix,
}: {
  data: MasterItem[];
  selected: Set<string>;
  search: string;
  setSearch: (s: string) => void;
  onToggle: (mid: string) => void;
  testIDPrefix: string;
}) {
  const q = search.trim().toLowerCase();
  const rows = data.filter(mi => !q || mi.name.toLowerCase().includes(q) || (mi.category || "").toLowerCase().includes(q));
  return (
    <View style={{ gap: spacing.sm }}>
      <View style={styles.searchBox}>
        <Ionicons name="search" size={16} color={colors.textMuted} />
        <TextInput testID={`${testIDPrefix}-search`} value={search} onChangeText={setSearch}
          placeholder="Search Master Menu…" placeholderTextColor={colors.textMuted} style={styles.searchInput} />
      </View>
      <View style={[styles.pickerBox, { maxHeight: 380 }]}>
        <ScrollView contentContainerStyle={{ padding: 4 }}>
          {rows.length === 0 ? (
            <Text style={styles.emptyPicker}>No dishes found.</Text>
          ) : rows.map(mi => {
            const on = selected.has(mi.item_id);
            return (
              <TouchableOpacity key={mi.item_id} testID={`${testIDPrefix}-pick-${mi.item_id}`}
                style={[styles.pickerRow, on && styles.pickerRowActive]} onPress={() => onToggle(mi.item_id)}>
                <Ionicons name={on ? "checkbox" : "square-outline"} size={22} color={on ? colors.primary : colors.textMuted} style={{ marginRight: 4 }} />
                {mi.image_url ? <Image source={{ uri: mi.image_url }} style={styles.pickerThumb} /> :
                  <View style={[styles.pickerThumb, { alignItems: "center", justifyContent: "center" }]}>
                    <Ionicons name="image-outline" size={18} color={colors.textMuted} />
                  </View>}
                <View style={{ flex: 1 }}>
                  <Text style={styles.pickerName}>{mi.name}</Text>
                  <Text style={styles.pickerMeta}>{mi.category} · {mi.cuisine} · CA${(mi.default_price_cents / 100).toFixed(2)}</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  headRow: { flexDirection: "row", alignItems: "stretch", gap: spacing.md },
  weekTab: { minWidth: 160, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: 2 },
  weekTabActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  weekTabDate: { color: colors.textMuted, fontSize: 10, letterSpacing: 2, fontWeight: "800" },
  weekTabTitle: { color: colors.text, fontSize: 13, fontWeight: "700" },
  weekTabCount: { color: colors.textMuted, fontSize: 11 },
  newBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.text, paddingHorizontal: 14, borderRadius: radius.md },
  newBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },

  currentBar: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, marginTop: spacing.md },
  currentDate: { color: colors.textMuted, fontSize: 10, letterSpacing: 2, fontWeight: "800" },
  currentTitle: { color: colors.text, fontSize: 16, fontWeight: "800" },
  dangerBtn: { width: 40, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.danger },

  sectionTabs: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.md },
  sectionTab: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  sectionTabOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  sectionTabText: { color: colors.text, fontWeight: "700", fontSize: 13 },

  addItemBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill },
  addItemBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },

  modeCard: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm, marginTop: spacing.md },
  modeTitle: { fontSize: 15, fontWeight: "800", color: colors.text },
  modeHint: { fontSize: 12, color: colors.textMuted },
  warnRow: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#FFFBF2", borderRadius: radius.md, borderWidth: 1, borderColor: colors.secondary, padding: spacing.sm },
  warnText: { flex: 1, fontSize: 11, color: colors.text, fontWeight: "600" },
  pill: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: radius.pill, borderWidth: 1 },
  pillOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  pillOff: { backgroundColor: colors.surface, borderColor: colors.border },
  pillText: { fontSize: 12, fontWeight: "800", color: colors.text },

  pkgSummary: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: "#FFF7F3" },
  pkgSummaryTitle: { fontSize: 14, fontWeight: "800", color: colors.text },
  pkgSummarySub: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  pkgSummaryDesc: { fontSize: 12, color: colors.text, marginTop: 4 },
  pkgEditBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, alignSelf: "flex-start" },
  pkgEditBtnText: { color: "#fff", fontWeight: "700", fontSize: 12 },

  searchRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  searchBox: { flex: 1, flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, marginTop: 4 },
  searchInput: { flex: 1, color: colors.text, fontSize: 14, paddingVertical: 10 },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  itemCard: { flexGrow: 1, flexBasis: 260, minWidth: 260, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden", ...shadows.soft },
  itemCardHidden: { opacity: 0.6, borderStyle: "dashed" },
  itemImg: { width: "100%", height: 120, backgroundColor: colors.surfaceAlt },
  itemName: { fontSize: 14, fontWeight: "700", color: colors.text, flexShrink: 1 },
  itemCat: { color: colors.primary, fontSize: 10, letterSpacing: 2, fontWeight: "800", textTransform: "uppercase" },
  itemFoot: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: 4 },
  itemPrice: { color: colors.primary, fontWeight: "800", fontSize: 15 },
  priceStrike: { color: colors.textMuted, fontSize: 11, textDecorationLine: "line-through" },
  stockLine: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  iconBtn: { width: 30, height: 30, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  visToggle: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8, paddingVertical: 8, paddingHorizontal: 10, borderRadius: radius.md, borderWidth: 1 },
  visOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  visOff: { backgroundColor: colors.surfaceAlt, borderColor: colors.border },
  visToggleText: { fontSize: 12, fontWeight: "700", color: colors.text },
  tag: { paddingHorizontal: 5, borderRadius: 4 },
  tagText: { color: "#fff", fontSize: 9, fontWeight: "900", letterSpacing: 1 },
  tagFeat: { backgroundColor: colors.secondary, paddingHorizontal: 5, borderRadius: 4 },
  tagFeatText: { color: "#1a1a1a", fontSize: 10, fontWeight: "900" },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl, width: "100%" },
  emptyState: { alignItems: "center", justifyContent: "center", padding: spacing.xxl, gap: spacing.md },

  modalOverlay: { flex: 1, backgroundColor: colors.overlay, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 540, maxHeight: "90%", backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.lg, gap: spacing.sm, ...shadows.card },
  modalHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  modalTitle: { fontSize: 20, fontWeight: "800", color: colors.text },
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800", marginBottom: 4 },
  helper: { color: colors.textMuted, fontSize: 11, marginTop: 4, fontStyle: "italic" },
  input: { backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontSize: 12, fontWeight: "600", textTransform: "capitalize" },
  chipTextActive: { color: "#fff", fontWeight: "800" },
  dateChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center" },
  dateChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  dateChipTaken: { opacity: 0.4 },
  dateChipText: { color: colors.text, fontSize: 12, fontWeight: "700" },
  dateChipTakenText: { color: colors.textMuted, fontSize: 9, fontWeight: "700" },
  checkboxRow: { flexDirection: "row", alignItems: "flex-start", gap: 10, padding: spacing.md, backgroundColor: colors.surfaceAlt, borderRadius: radius.md },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md, backgroundColor: colors.surfaceAlt, borderRadius: radius.md },
  toggleText: { color: colors.text, fontWeight: "600" },
  primaryBtn: { backgroundColor: colors.primary, padding: 14, borderRadius: radius.pill, alignItems: "center", marginTop: 4, ...shadows.card },
  primaryBtnText: { color: "#fff", fontWeight: "800", fontSize: 15 },

  pickerBox: { maxHeight: 300, backgroundColor: colors.background, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, marginTop: 6 },
  pickerRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.sm, borderRadius: radius.sm, marginBottom: 4 },
  pickerRowActive: { backgroundColor: "#FBF3EF", borderWidth: 1, borderColor: colors.primary },
  pickerThumb: { width: 42, height: 42, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  pickerName: { color: colors.text, fontWeight: "700", fontSize: 13 },
  pickerMeta: { color: colors.textMuted, fontSize: 11 },
  emptyPicker: { color: colors.textMuted, padding: spacing.md, textAlign: "center" },
});
