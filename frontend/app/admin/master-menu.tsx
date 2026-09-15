import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator, ScrollView, Image, Modal, Alert, Platform,
} from "react-native";
import { useRouter } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import AdminShell from "@/src/components/AdminShell";
import { adminApi, getAdminToken } from "@/src/adminApi";
import { getBackendUrl } from "@/src/utils/backendUrl";
import { colors, spacing, radius, shadows } from "@/src/theme";

type MasterItem = {
  item_id: string; name: string; short_description: string; full_description: string;
  category: string; cuisine: string; default_price_cents: number; cost_price_cents: number;
  image_url: string; veg_type: string; spice_level: string; allergens: string[];
  is_active: boolean; prep_notes: string; kitchen_notes: string; display_order: number;
};

const CATS = [
  { k: "starter", label: "Starter" },
  { k: "main-veg", label: "Main Veg" },
  { k: "main-non-veg", label: "Main Non-Veg" },
  { k: "rice", label: "Rice" },
  { k: "curry", label: "Curry" },
  { k: "dessert", label: "Dessert" },
  { k: "beverage", label: "Beverage" },
];
const CUISINES = [
  { k: "bengali", label: "Bengali" },
  { k: "north-indian", label: "North Indian" },
  { k: "south-indian", label: "South Indian" },
  { k: "indo-chinese", label: "Indo-Chinese" },
  { k: "fusion", label: "Fusion" },
];
const VEG_TYPES = ["vegetarian", "non-vegetarian", "eggitarian"];
const SPICES = ["mild", "medium", "hot"];
const ALLERGENS = ["dairy", "nuts", "seafood", "gluten"];

const BLANK: MasterItem = {
  item_id: `mi_${Math.random().toString(36).slice(2, 12)}`,
  name: "", short_description: "", full_description: "",
  category: "curry", cuisine: "bengali", default_price_cents: 0, cost_price_cents: 0,
  image_url: "", veg_type: "vegetarian", spice_level: "medium", allergens: [],
  is_active: true, prep_notes: "", kitchen_notes: "", display_order: 0,
};

export default function AdminMasterMenu() {
  const router = useRouter();
  const [items, setItems] = useState<MasterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [catFilter, setCatFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [edit, setEdit] = useState<MasterItem | null>(null);
  const [priceStr, setPriceStr] = useState("");
  const [costStr, setCostStr] = useState("");

  // ---- Bulk-upload state
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkStep, setBulkStep] = useState<"input" | "preview">("input");
  const [bulkCsv, setBulkCsv] = useState("");        // raw CSV text
  const [bulkGenImages, setBulkGenImages] = useState(true);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkPreviews, setBulkPreviews] = useState<MasterItem[]>([]);
  const [bulkSkip, setBulkSkip] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (search) params.set("q", search);
    if (catFilter) params.set("category", catFilter);
    if (activeFilter) params.set("active", activeFilter);
    const r = await adminApi.get<MasterItem[]>(`/admin/master-menu${params.toString() ? "?" + params.toString() : ""}`);
    if (r.status === 401) { router.replace("/admin"); return; }
    if (r.ok) setItems(r.data || []);
    setLoading(false);
  }, [router, search, catFilter, activeFilter]);

  useEffect(() => { (async () => {
    const t = await getAdminToken(); if (!t) return router.replace("/admin");
    await load();
  })(); }, [router, load]);

  const openEdit = (it: MasterItem | null) => {
    const target = it || { ...BLANK, item_id: `mi_${Math.random().toString(36).slice(2, 12)}` };
    setEdit(target);
    setPriceStr((target.default_price_cents / 100).toFixed(2));
    setCostStr((target.cost_price_cents / 100).toFixed(2));
  };

  const pickImage = async () => {
    if (!edit) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      allowsEditing: true, aspect: [4, 3], quality: 0.6, base64: true,
    });
    if (!result.canceled && result.assets?.[0]?.base64) {
      const uri = `data:${result.assets[0].mimeType || "image/jpeg"};base64,${result.assets[0].base64}`;
      setEdit({ ...edit, image_url: uri });
    }
  };

  const save = async () => {
    if (!edit) return;
    const body: MasterItem = {
      ...edit,
      default_price_cents: Math.round((parseFloat(priceStr) || 0) * 100),
      cost_price_cents: Math.round((parseFloat(costStr) || 0) * 100),
    };
    const r = await adminApi.post("/admin/master-menu", body);
    if (r.ok) { setEdit(null); await load(); }
    else Alert.alert("Save failed", r.error);
  };

  const remove = async (id: string) => {
    const ok = Platform.OS === "web" ? window.confirm("Delete this item?") : true;
    if (!ok) return;
    await adminApi.del(`/admin/master-menu/${id}`);
    await load();
  };

  const duplicate = async (id: string) => {
    await adminApi.post(`/admin/master-menu/${id}/duplicate`);
    await load();
  };

  const bulk = async (action: "activate" | "deactivate" | "delete") => {
    if (selected.length === 0) return;
    await adminApi.post("/admin/master-menu/bulk", { item_ids: selected, action });
    setSelected([]);
    await load();
  };

  const toggle = (id: string) => setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  // ---- Bulk upload helpers ---------------------------------------------------
  const backendBase = getBackendUrl();

  /** Absolute URL helper for images returned by the AI (paths starting with /api/uploads). */
  const absUrl = (u: string) => (u && u.startsWith("/api/") ? `${backendBase}${u}` : u);

  const parseCsv = (text: string): { name: string; default_price_cents: number }[] => {
    const rows: { name: string; default_price_cents: number }[] = [];
    const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    for (let i = 0; i < lines.length; i++) {
      // very-forgiving CSV: split on comma (and only respect one level of double-quotes)
      const parts = lines[i].match(/("[^"]*"|[^,]+)/g)?.map(p => p.replace(/^"|"$/g, "").trim()) || [];
      if (parts.length < 2) continue;
      // Skip header row if it doesn't parse as a price
      if (i === 0 && !/^\d/.test(parts[1])) continue;
      const price = parseFloat(parts[1]);
      if (!isFinite(price)) continue;
      const name = parts[0];
      if (!name) continue;
      rows.push({ name, default_price_cents: Math.round(price * 100) });
    }
    return rows;
  };

  const pickCsvFile = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ["text/csv", "text/plain", "application/vnd.ms-excel", "*/*"],
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      let content = "";
      if (Platform.OS === "web") {
        // The uri is a blob:// URL; fetch it to read text.
        const r = await fetch(asset.uri);
        content = await r.text();
      } else {
        // On native the FS module would be needed; fallback: read via fetch which
        // supports file:// URIs in modern Expo builds.
        const r = await fetch(asset.uri);
        content = await r.text();
      }
      setBulkCsv(content);
    } catch (e: any) {
      Alert.alert("File error", e?.message || "Could not read file");
    }
  };

  const runBulkPreview = async () => {
    const rows = parseCsv(bulkCsv);
    if (rows.length === 0) { Alert.alert("Empty", "No valid rows found in the CSV."); return; }
    if (rows.length > 25) { Alert.alert("Too many", "Max 25 items per upload."); return; }
    if (bulkGenImages && rows.length > 10) {
      const proceed = Platform.OS === "web"
        ? window.confirm(`Generating ${rows.length} AI images will take ~${Math.ceil(rows.length * 2)}s. Continue?`)
        : true;
      if (!proceed) return;
    }
    setBulkLoading(true);

    // Direct fetch (not adminApi) so we can set a long timeout via AbortController.
    const token = await getAdminToken();
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 180_000); // 3-minute hard cap
    try {
      const res = await fetch(`${backendBase}/api/admin/master-menu/bulk-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token || ""}` },
        body: JSON.stringify({ rows, generate_images: bulkGenImages }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      const text = await res.text();
      let data: any = null;
      try { data = text ? JSON.parse(text) : null; } catch { data = text; }
      setBulkLoading(false);
      if (!res.ok) { Alert.alert("Preview failed", data?.detail || text || `HTTP ${res.status}`); return; }
      setBulkPreviews(data?.previews || []);
      setBulkSkip({});
      setBulkStep("preview");
    } catch (e: any) {
      clearTimeout(t);
      setBulkLoading(false);
      const msg = e?.name === "AbortError"
        ? "AI enrichment took longer than 3 minutes and was cancelled. Try fewer items or turn off image generation."
        : (e?.message || "Network error while generating preview.");
      Alert.alert("Preview failed", msg);
    }
  };

  const bulkSaveAll = async () => {
    const items = bulkPreviews
      .filter(p => !bulkSkip[p.item_id])
      .map(p => ({
        ...p,
        // Convert relative /api/uploads/... to absolute URL so images work in native builds
        // and in whichever host the DB is later restored to (as long as BACKEND_URL is set).
        image_url: p.image_url && p.image_url.startsWith("/api/") ? `${backendBase}${p.image_url}` : p.image_url,
      }));
    if (items.length === 0) { Alert.alert("Nothing to save", "All rows are skipped."); return; }
    setBulkLoading(true);
    const r = await adminApi.post<{ saved: number }>("/admin/master-menu/bulk-save", { items });
    setBulkLoading(false);
    if (!r.ok) { Alert.alert("Save failed", r.error); return; }
    Alert.alert("Saved", `${r.data.saved} items added to Master Menu.`);
    setBulkOpen(false);
    setBulkStep("input");
    setBulkCsv("");
    setBulkPreviews([]);
    await load();
  };

  const patchPreview = (idx: number, patch: Partial<MasterItem>) => {
    setBulkPreviews(prev => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  };
  // ----------------------------------------------------------------------------

  return (
    <AdminShell title="Master Menu">
      <View style={styles.toolbar}>
        <View style={styles.searchWrap}>
          <Ionicons name="search-outline" size={16} color={colors.textMuted} />
          <TextInput
            testID="mm-search"
            value={search}
            onChangeText={setSearch}
            placeholder="Search dishes"
            placeholderTextColor={colors.textMuted}
            style={styles.search}
          />
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
          <FilterChip label="All categories" active={catFilter === ""} onPress={() => setCatFilter("")} />
          {CATS.map(c => <FilterChip key={c.k} label={c.label} active={catFilter === c.k} onPress={() => setCatFilter(c.k)} testID={`mm-cat-${c.k}`} />)}
        </ScrollView>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
          <FilterChip label="All" active={activeFilter === ""} onPress={() => setActiveFilter("")} />
          <FilterChip label="Active" active={activeFilter === "true"} onPress={() => setActiveFilter("true")} testID="mm-only-active" />
          <FilterChip label="Inactive" active={activeFilter === "false"} onPress={() => setActiveFilter("false")} testID="mm-only-inactive" />
        </ScrollView>
        <TouchableOpacity testID="mm-bulk-upload" style={[styles.primaryBtn, { backgroundColor: colors.text }]} onPress={() => { setBulkOpen(true); setBulkStep("input"); }}>
          <Ionicons name="sparkles" size={16} color="#fff" />
          <Text style={styles.primaryBtnText}>Bulk upload (AI)</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="mm-new" style={styles.primaryBtn} onPress={() => openEdit(null)}>
          <Ionicons name="add" size={16} color="#fff" />
          <Text style={styles.primaryBtnText}>New item</Text>
        </TouchableOpacity>
      </View>

      {selected.length > 0 && (
        <View style={styles.bulkBar} testID="mm-bulk-bar">
          <Text style={{ color: colors.text, fontWeight: "700" }}>{selected.length} selected</Text>
          <TouchableOpacity testID="mm-bulk-activate" style={styles.bulkBtn} onPress={() => bulk("activate")}><Text style={styles.bulkBtnText}>Activate</Text></TouchableOpacity>
          <TouchableOpacity testID="mm-bulk-deactivate" style={styles.bulkBtn} onPress={() => bulk("deactivate")}><Text style={styles.bulkBtnText}>Deactivate</Text></TouchableOpacity>
          <TouchableOpacity testID="mm-bulk-delete" style={[styles.bulkBtn, { borderColor: colors.danger }]} onPress={() => bulk("delete")}><Text style={[styles.bulkBtnText, { color: colors.danger }]}>Delete</Text></TouchableOpacity>
        </View>
      )}

      {loading ? <ActivityIndicator color={colors.primary} size="large" /> : (
        <View style={styles.grid}>
          {items.map(it => {
            const sel = selected.includes(it.item_id);
            return (
              <View key={it.item_id} style={[styles.card, sel && styles.cardSel]} testID={`mm-card-${it.item_id}`}>
                <TouchableOpacity onPress={() => toggle(it.item_id)} style={styles.checkbox} testID={`mm-select-${it.item_id}`}>
                  <Ionicons name={sel ? "checkbox" : "square-outline"} size={20} color={sel ? colors.primary : colors.textMuted} />
                </TouchableOpacity>
                {it.image_url ? <Image source={{ uri: it.image_url }} style={styles.img} /> : <View style={[styles.img, styles.imgPh]}><Ionicons name="image-outline" size={28} color={colors.textMuted} /></View>}
                <View style={{ padding: spacing.md, gap: 4 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={styles.name} numberOfLines={1}>{it.name || "Untitled"}</Text>
                    {!it.is_active && <View style={styles.badgeMuted}><Text style={styles.badgeMutedText}>OFF</Text></View>}
                  </View>
                  <Text style={styles.meta}>{it.category} · {it.cuisine} · {it.veg_type}</Text>
                  <Text style={styles.desc} numberOfLines={2}>{it.short_description}</Text>
                  <View style={styles.foot}>
                    <Text style={styles.price}>CA${(it.default_price_cents / 100).toFixed(2)}</Text>
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      <TouchableOpacity testID={`mm-dup-${it.item_id}`} style={styles.iconBtn} onPress={() => duplicate(it.item_id)}><Ionicons name="copy-outline" size={14} color={colors.text} /></TouchableOpacity>
                      <TouchableOpacity testID={`mm-edit-${it.item_id}`} style={styles.iconBtn} onPress={() => openEdit(it)}><Ionicons name="pencil" size={14} color={colors.text} /></TouchableOpacity>
                      <TouchableOpacity testID={`mm-del-${it.item_id}`} style={styles.iconBtn} onPress={() => remove(it.item_id)}><Ionicons name="trash-outline" size={14} color={colors.danger} /></TouchableOpacity>
                    </View>
                  </View>
                </View>
              </View>
            );
          })}
          {items.length === 0 && <Text style={styles.empty}>No items match. Create your first dish.</Text>}
        </View>
      )}

      <Modal visible={!!edit} transparent animationType="slide" onRequestClose={() => setEdit(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard} testID="mm-edit-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>{edit?.name ? `Edit — ${edit.name}` : "New menu item"}</Text>
              <TouchableOpacity onPress={() => setEdit(null)}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>
            {edit && (
              <ScrollView contentContainerStyle={{ gap: spacing.sm }}>
                <Field label="Name" testID="mm-form-name" value={edit.name} onChange={t => setEdit({ ...edit, name: t })} />
                <Field label="Short description" testID="mm-form-short" value={edit.short_description} onChange={t => setEdit({ ...edit, short_description: t })} multiline />
                <Field label="Full description" testID="mm-form-full" value={edit.full_description} onChange={t => setEdit({ ...edit, full_description: t })} multiline />
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Category</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 4 }}>
                      {CATS.map(c => <MiniChip key={c.k} label={c.label} active={edit.category === c.k} onPress={() => setEdit({ ...edit, category: c.k })} testID={`mm-form-cat-${c.k}`} />)}
                    </ScrollView>
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Cuisine</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 4 }}>
                      {CUISINES.map(c => <MiniChip key={c.k} label={c.label} active={edit.cuisine === c.k} onPress={() => setEdit({ ...edit, cuisine: c.k })} />)}
                    </ScrollView>
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Default price (CAD)</Text>
                    <TextInput testID="mm-form-price" value={priceStr} onChangeText={setPriceStr} keyboardType="decimal-pad" style={styles.input} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Cost price (CAD) · super admin</Text>
                    <TextInput testID="mm-form-cost" value={costStr} onChangeText={setCostStr} keyboardType="decimal-pad" style={styles.input} />
                  </View>
                </View>
                <View>
                  <Text style={styles.label}>Image</Text>
                  <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                    <TextInput testID="mm-form-image" value={edit.image_url} onChangeText={t => setEdit({ ...edit, image_url: t })} placeholder="Paste a direct image URL" placeholderTextColor={colors.textMuted} style={[styles.input, { flex: 1 }]} />
                    <TouchableOpacity testID="mm-form-pick" onPress={pickImage} style={styles.pickBtn}><Ionicons name="cloud-upload-outline" size={16} color="#fff" /><Text style={styles.pickBtnText}>Upload</Text></TouchableOpacity>
                  </View>
                  {edit.image_url ? <Image source={{ uri: edit.image_url }} style={styles.preview} /> : null}
                </View>
                <View>
                  <Text style={styles.label}>Vegetarian type</Text>
                  <View style={{ flexDirection: "row", gap: 4 }}>
                    {VEG_TYPES.map(v => <MiniChip key={v} label={v.replace("-", " ")} active={edit.veg_type === v} onPress={() => setEdit({ ...edit, veg_type: v })} />)}
                  </View>
                </View>
                <View>
                  <Text style={styles.label}>Spice level</Text>
                  <View style={{ flexDirection: "row", gap: 4 }}>
                    {SPICES.map(v => <MiniChip key={v} label={v} active={edit.spice_level === v} onPress={() => setEdit({ ...edit, spice_level: v })} />)}
                  </View>
                </View>
                <View>
                  <Text style={styles.label}>Allergens</Text>
                  <View style={{ flexDirection: "row", gap: 4 }}>
                    {ALLERGENS.map(a => {
                      const on = edit.allergens.includes(a);
                      return <MiniChip key={a} label={a} active={on} onPress={() => setEdit({ ...edit, allergens: on ? edit.allergens.filter(x => x !== a) : [...edit.allergens, a] })} testID={`mm-form-allergen-${a}`} />;
                    })}
                  </View>
                </View>
                <Field label="Prep notes" testID="mm-form-prep" value={edit.prep_notes} onChange={t => setEdit({ ...edit, prep_notes: t })} multiline />
                <Field label="Kitchen notes" testID="mm-form-kitchen" value={edit.kitchen_notes} onChange={t => setEdit({ ...edit, kitchen_notes: t })} multiline />
                <TouchableOpacity testID="mm-form-active" onPress={() => setEdit({ ...edit, is_active: !edit.is_active })} style={styles.toggleRow}>
                  <Ionicons name={edit.is_active ? "checkbox" : "square-outline"} size={20} color={edit.is_active ? colors.success : colors.textMuted} />
                  <Text style={styles.toggleText}>{edit.is_active ? "Active" : "Inactive"} — {edit.is_active ? "shown to customers" : "hidden"}</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="mm-form-save" style={styles.saveBtn} onPress={save}>
                  <Text style={styles.saveBtnText}>Save item</Text>
                </TouchableOpacity>
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>

      {/* ==== BULK UPLOAD (AI-enriched) ==== */}
      <Modal visible={bulkOpen} transparent animationType="slide" onRequestClose={() => setBulkOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={[styles.modalCard, { maxWidth: 760 }]} testID="mm-bulk-modal">
            <View style={styles.modalHead}>
              <View style={{ flex: 1 }}>
                <Text style={styles.modalTitle}>
                  {bulkStep === "input" ? "Bulk upload · AI-assisted" : `Review ${bulkPreviews.length} items · AI-generated`}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }}>
                  {bulkStep === "input"
                    ? "Upload a CSV with name and price. AI fills description, image, category, and tags."
                    : "Edit any field, or tap ✕ to skip a row. Then Save all."}
                </Text>
              </View>
              <TouchableOpacity onPress={() => setBulkOpen(false)}><Ionicons name="close" size={22} color={colors.text} /></TouchableOpacity>
            </View>

            {bulkStep === "input" ? (
              <ScrollView contentContainerStyle={{ gap: spacing.md }}>
                <View style={styles.hintBox}>
                  <Ionicons name="information-circle" size={16} color={colors.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.hintTitle}>CSV format — 2 columns only</Text>
                    <Text style={styles.hintText}>{`name,price\nKolkata Chicken Biryani,16.99\nRasgulla,4.99\nAlur Dom,8.50`}</Text>
                    <Text style={[styles.hintText, { color: colors.textMuted, marginTop: 4 }]}>Max 25 rows per upload. Prices are in CAD.</Text>
                  </View>
                </View>

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <TouchableOpacity testID="mm-bulk-pick" style={styles.pickBtn} onPress={pickCsvFile}>
                    <Ionicons name="cloud-upload-outline" size={16} color="#fff" />
                    <Text style={styles.pickBtnText}>Choose CSV file</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.pickBtn, { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }]} onPress={() => setBulkCsv("name,price\nKolkata Chicken Biryani,16.99\nRasgulla,4.99")}>
                    <Ionicons name="clipboard-outline" size={16} color={colors.text} />
                    <Text style={[styles.pickBtnText, { color: colors.text }]}>Paste sample</Text>
                  </TouchableOpacity>
                </View>

                <View>
                  <Text style={styles.label}>Or paste rows here</Text>
                  <TextInput
                    testID="mm-bulk-csv"
                    value={bulkCsv}
                    onChangeText={setBulkCsv}
                    multiline
                    style={[styles.input, { minHeight: 160, fontFamily: Platform.select({ web: "monospace", default: undefined }) }]}
                    placeholder={"name,price\nKolkata Chicken Biryani,16.99"}
                    placeholderTextColor={colors.textMuted}
                  />
                </View>

                <TouchableOpacity testID="mm-bulk-gen-toggle" style={styles.toggleRow} onPress={() => setBulkGenImages(!bulkGenImages)}>
                  <Ionicons name={bulkGenImages ? "checkbox" : "square-outline"} size={20} color={bulkGenImages ? colors.primary : colors.textMuted} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.toggleText}>Generate AI food images</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11 }}>Uses Gemini Nano Banana · ~10s per item. Turn off for a faster text-only preview.</Text>
                  </View>
                </TouchableOpacity>

                <TouchableOpacity testID="mm-bulk-preview" style={[styles.saveBtn, bulkLoading && { opacity: 0.7 }]} disabled={bulkLoading} onPress={runBulkPreview}>
                  {bulkLoading
                    ? <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><ActivityIndicator color="#fff" /><Text style={styles.saveBtnText}>Generating with AI…</Text></View>
                    : <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><Ionicons name="sparkles" size={16} color="#fff" /><Text style={styles.saveBtnText}>Generate preview</Text></View>
                  }
                </TouchableOpacity>
              </ScrollView>
            ) : (
              <>
                <ScrollView contentContainerStyle={{ gap: spacing.sm }}>
                  {bulkPreviews.map((p, idx) => {
                    const skipped = !!bulkSkip[p.item_id];
                    return (
                      <View key={p.item_id} style={[styles.previewRow, skipped && { opacity: 0.4 }]}>
                        {p.image_url
                          ? <Image source={{ uri: absUrl(p.image_url) }} style={styles.previewImg} />
                          : <View style={[styles.previewImg, styles.imgPh]}><Ionicons name="image-outline" size={20} color={colors.textMuted} /></View>}
                        <View style={{ flex: 1, gap: 4 }}>
                          <View style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
                            <TextInput
                              value={p.name}
                              onChangeText={t => patchPreview(idx, { name: t })}
                              style={[styles.input, { flex: 1, fontWeight: "700" }]}
                            />
                            <TextInput
                              value={(p.default_price_cents / 100).toFixed(2)}
                              onChangeText={t => patchPreview(idx, { default_price_cents: Math.round((parseFloat(t) || 0) * 100) })}
                              keyboardType="decimal-pad"
                              style={[styles.input, { width: 90 }]}
                            />
                            <TouchableOpacity
                              testID={`mm-bulk-skip-${idx}`}
                              onPress={() => setBulkSkip(s => ({ ...s, [p.item_id]: !s[p.item_id] }))}
                              style={styles.skipBtn}
                            >
                              <Ionicons name={skipped ? "refresh" : "close"} size={16} color={skipped ? colors.success : colors.danger} />
                            </TouchableOpacity>
                          </View>
                          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4 }}>
                            <TagPill label={p.category} />
                            <TagPill label={p.cuisine} />
                            <TagPill label={p.veg_type} />
                            <TagPill label={p.spice_level} />
                            {p.allergens.map(a => <TagPill key={a} label={`⚠ ${a}`} />)}
                          </View>
                          <TextInput
                            value={p.short_description}
                            onChangeText={t => patchPreview(idx, { short_description: t })}
                            style={[styles.input, { minHeight: 40 }]}
                            multiline
                          />
                        </View>
                      </View>
                    );
                  })}
                </ScrollView>

                <View style={{ flexDirection: "row", gap: 8 }}>
                  <TouchableOpacity style={[styles.pickBtn, { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, flex: 1 }]} onPress={() => setBulkStep("input")}>
                    <Ionicons name="arrow-back" size={16} color={colors.text} />
                    <Text style={[styles.pickBtnText, { color: colors.text }]}>Back</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="mm-bulk-save" style={[styles.saveBtn, { flex: 2, marginTop: 0 }]} disabled={bulkLoading} onPress={bulkSaveAll}>
                    {bulkLoading
                      ? <ActivityIndicator color="#fff" />
                      : <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><Ionicons name="checkmark-circle" size={16} color="#fff" /><Text style={styles.saveBtnText}>Save {bulkPreviews.filter(p => !bulkSkip[p.item_id]).length} items</Text></View>}
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        </View>
      </Modal>
    </AdminShell>
  );
}

function FilterChip({ label, active, onPress, testID }: any) {
  return (
    <TouchableOpacity testID={testID} onPress={onPress} style={[styles.filterChip, active && styles.filterChipActive]}>
      <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}
function MiniChip({ label, active, onPress, testID }: any) {
  return (
    <TouchableOpacity testID={testID} onPress={onPress} style={[styles.miniChip, active && styles.miniChipActive]}>
      <Text style={[styles.miniChipText, active && styles.miniChipTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}
function TagPill({ label }: { label: string }) {
  return (
    <View style={styles.tagPill}>
      <Text style={styles.tagPillText}>{label}</Text>
    </View>
  );
}
function Field({ label, value, onChange, multiline, testID }: any) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput testID={testID} value={value} onChangeText={onChange} multiline={multiline} style={[styles.input, multiline && { minHeight: 60 }]} placeholderTextColor={colors.textMuted} />
    </View>
  );
}

const styles = StyleSheet.create({
  toolbar: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: spacing.md, borderWidth: 1, borderColor: colors.border, height: 40, minWidth: 200 },
  search: { flex: 1, color: colors.text, fontSize: 13 },
  filterChip: { flexShrink: 0, paddingHorizontal: 12, height: 34, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  filterChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  filterChipText: { color: colors.text, fontWeight: "600", fontSize: 12 },
  filterChipTextActive: { color: "#fff" },
  primaryBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, ...shadows.soft, marginLeft: "auto" },
  primaryBtnText: { color: "#fff", fontWeight: "800", fontSize: 13 },

  bulkBar: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md, backgroundColor: "#FFF7E6", borderRadius: radius.md, borderWidth: 1, borderColor: "#FCD9A5", flexWrap: "wrap" },
  bulkBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  bulkBtnText: { color: colors.text, fontWeight: "700", fontSize: 12 },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  card: { flexGrow: 1, flexBasis: 240, minWidth: 240, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden", ...shadows.soft, position: "relative" },
  cardSel: { borderColor: colors.primary, borderWidth: 2 },
  checkbox: { position: "absolute", top: 8, left: 8, backgroundColor: "rgba(255,255,255,0.9)", borderRadius: radius.pill, padding: 3, zIndex: 2 },
  img: { width: "100%", height: 130, backgroundColor: colors.surfaceAlt },
  imgPh: { alignItems: "center", justifyContent: "center" },
  name: { fontSize: 14, fontWeight: "700", color: colors.text, flex: 1 },
  meta: { color: colors.textMuted, fontSize: 10, letterSpacing: 1, fontWeight: "700", textTransform: "uppercase" },
  desc: { color: colors.textMuted, fontSize: 12, lineHeight: 16, minHeight: 32 },
  foot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  price: { color: colors.primary, fontWeight: "800", fontSize: 15 },
  iconBtn: { width: 30, height: 30, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  badgeMuted: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 5, borderRadius: 4 },
  badgeMutedText: { color: colors.textMuted, fontSize: 9, fontWeight: "900", letterSpacing: 1 },
  empty: { color: colors.textMuted, textAlign: "center", padding: spacing.xl, width: "100%" },

  modalOverlay: { flex: 1, backgroundColor: colors.overlay, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 560, maxHeight: "90%", backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.lg, gap: spacing.sm, ...shadows.card },
  modalHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.text, flex: 1 },
  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800", marginBottom: 4 },
  input: { backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14 },
  pickBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.text, paddingHorizontal: 12, paddingVertical: 10, borderRadius: radius.md },
  pickBtnText: { color: "#fff", fontWeight: "700", fontSize: 12 },
  preview: { width: 120, height: 90, borderRadius: radius.md, marginTop: 8, backgroundColor: colors.surfaceAlt },

  miniChip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexShrink: 0 },
  miniChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  miniChipText: { color: colors.text, fontSize: 11, fontWeight: "600", textTransform: "capitalize" },
  miniChipTextActive: { color: "#fff", fontWeight: "800" },

  toggleRow: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md, backgroundColor: colors.surfaceAlt, borderRadius: radius.md },
  toggleText: { color: colors.text, fontWeight: "600" },
  saveBtn: { backgroundColor: colors.primary, padding: 14, borderRadius: radius.pill, alignItems: "center", marginTop: spacing.md, ...shadows.card },
  saveBtnText: { color: "#fff", fontWeight: "800", fontSize: 15 },

  hintBox: { flexDirection: "row", gap: 8, padding: spacing.md, backgroundColor: "#FFF7E6", borderRadius: radius.md, borderWidth: 1, borderColor: "#FCD9A5" },
  hintTitle: { color: colors.text, fontWeight: "800", fontSize: 12, marginBottom: 4 },
  hintText: { color: colors.text, fontSize: 12, fontFamily: Platform.select({ web: "monospace", default: undefined }) },
  previewRow: { flexDirection: "row", gap: spacing.sm, padding: spacing.sm, backgroundColor: colors.surfaceAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  previewImg: { width: 84, height: 84, borderRadius: radius.md, backgroundColor: colors.surface },
  skipBtn: { width: 34, height: 34, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  tagPill: { backgroundColor: colors.surface, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2, borderWidth: 1, borderColor: colors.border },
  tagPillText: { color: colors.text, fontSize: 10, fontWeight: "700", textTransform: "capitalize" },
});
