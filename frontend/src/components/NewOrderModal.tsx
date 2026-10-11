/**
 * Admin — "New Order" modal.
 *
 * Lets admin manually create an order on behalf of a customer.
 * Flow (single-page form, sectioned):
 *   1. Customer      — search existing OR add new inline (name + phone required)
 *   2. Items         — pick from à la carte / weekly combos / catering packages
 *   3. Delivery      — pick date from dropdown (next 4 weeks × delivery_days) + address
 *   4. Payment       — method + mark-paid toggle + optional driver assignment
 */
import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, Modal, ScrollView, Alert, Image,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { adminApi } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";

type Customer = {
  user_id: string; name: string; email?: string; phone?: string;
  default_address?: any;
};
type MenuItem = {
  item_id: string; name: string; image_url?: string;
  default_price_cents?: number; veg_type?: string;
};
type Slot = { date: string; window: string; label: string };
type Partner = { partner_id: string; name: string; phone?: string; vehicle?: string };

type PickedItem = {
  key: string;                       // uid for React
  kind: "menu" | "weekly_package" | "catering" | "custom";
  ref_id: string;
  name: string;
  price_cents: number;
  quantity: number;
  catering_guest_count?: number;
  package_selections?: string[];      // for combos
};

const MODES = [
  { key: "menu", label: "À la carte", icon: "restaurant-outline" as const },
  { key: "weekly_package", label: "Weekly Combo", icon: "gift-outline" as const },
  { key: "catering", label: "Catering", icon: "people-outline" as const },
  { key: "custom", label: "Custom", icon: "create-outline" as const },
];

const money = (c: number) => `CA$${(c / 100).toFixed(2)}`;

export default function NewOrderModal({
  visible, onClose, onCreated,
}: {
  visible: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Builder data
  const [builder, setBuilder] = useState<any>(null);

  // Customer state
  const [existingCustomers, setExistingCustomers] = useState<Customer[]>([]);
  const [custSearch, setCustSearch] = useState("");
  const [selectedCust, setSelectedCust] = useState<Customer | null>(null);
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [newCust, setNewCust] = useState({ name: "", phone: "", email: "" });

  // Items state
  const [mode, setMode] = useState<"menu" | "weekly_package" | "catering" | "custom">("menu");
  const [picked, setPicked] = useState<PickedItem[]>([]);
  // Custom dish entry (admin types a one-off name + price)
  const [customName, setCustomName] = useState("");
  const [customPrice, setCustomPrice] = useState("");

  // Weekly Combo picker (opens when admin clicks + on a combo)
  const [comboPicker, setComboPicker] = useState<{ combo: any; qty: Record<string, number> } | null>(null);

  // Delivery
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [address, setAddress] = useState({
    line1: "", line2: "", city: "Mississauga", province: "ON", postal_code: "",
  });

  // Payment + driver — Card (Stripe) is temporarily disabled for MVP,
  // so admins can only pick COD or Interac when creating a manual order.
  const [paymentMethod, setPaymentMethod] = useState<"cod" | "interac">("cod");
  const [markAsPaid, setMarkAsPaid] = useState(false);
  const [driverId, setDriverId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");

  // -------- Load ---------------------------------------------------------
  useEffect(() => {
    if (!visible) return;
    (async () => {
      setLoading(true);
      const [b, c] = await Promise.all([
        adminApi.get<any>("/admin/order-builder"),
        adminApi.get<Customer[]>("/admin/customers"),
      ]);
      if (b.ok) {
        setBuilder(b.data);
        if (b.data.delivery_slots?.length) setSelectedSlot(b.data.delivery_slots[0]);
      }
      if (c.ok) setExistingCustomers(Array.isArray(c.data) ? c.data : []);
      setLoading(false);
    })();
  }, [visible]);

  const resetAll = () => {
    setSelectedCust(null); setShowNewCustomer(false);
    setNewCust({ name: "", phone: "", email: "" });
    setPicked([]); setNotes(""); setComboPicker(null);
    setCustomName(""); setCustomPrice("");
    setPaymentMethod("cod"); setMarkAsPaid(false); setDriverId(null);
    setAddress({ line1: "", line2: "", city: "Mississauga", province: "ON", postal_code: "" });
    setCustSearch("");
  };

  // When customer changes, pre-fill address
  useEffect(() => {
    if (selectedCust?.default_address) {
      const a = selectedCust.default_address;
      setAddress({
        line1: a.line1 || "", line2: a.line2 || "",
        city: a.city || "Mississauga", province: a.province || "ON", postal_code: a.postal_code || "",
      });
    }
  }, [selectedCust]);

  // -------- Derived state -----------------------------------------------
  const filteredCustomers = useMemo(() => {
    const q = custSearch.trim().toLowerCase();
    if (!q) return existingCustomers.slice(0, 25);
    return existingCustomers.filter(c =>
      (c.name || "").toLowerCase().includes(q) ||
      (c.email || "").toLowerCase().includes(q) ||
      (c.phone || "").toLowerCase().includes(q)
    ).slice(0, 25);
  }, [custSearch, existingCustomers]);

  // Pick the right source-week per mode. Prefers the current week (today ∈ week);
  // falls back to the nearest week that has that mode enabled — this way "à la carte"
  // and "Weekly Combo" always show something when at least ONE weekly menu is live.
  const pickWeekForMode = (mode: "menu" | "weekly_package") => {
    if (!builder) return null;
    const weeks: any[] = builder.weeks || [];
    if (!weeks.length) return null;
    const cws: string | null = builder.current_week_start || null;
    const enabledKey = mode === "menu" ? "alacarte_enabled" : "package_enabled";
    // 1) current week if it's enabled for this mode
    const cur = cws ? weeks.find(w => w.week_start === cws) : null;
    if (cur && cur[enabledKey] && (cur.items || []).length) return cur;
    // 2) nearest week where mode enabled + has items
    const withMode = weeks.filter(w => w[enabledKey] && (w.items || []).length);
    if (!withMode.length) return cur || weeks[0];
    // Prefer future/current, else most recent past
    const today = new Date().toISOString().slice(0, 10);
    const upcoming = withMode
      .filter(w => w.week_start >= today)
      .sort((a, b) => a.week_start.localeCompare(b.week_start))[0];
    if (upcoming) return upcoming;
    return withMode.sort((a, b) => b.week_start.localeCompare(a.week_start))[0];
  };

  const availableItems = useMemo(() => {
    if (!builder) return { menu: [], combos: [], catering: [], menuWeek: null, comboWeek: null };
    const menuWeek = pickWeekForMode("menu");
    const comboWeek = pickWeekForMode("weekly_package");

    const menuItems: MenuItem[] = [];
    if (menuWeek?.alacarte_enabled) {
      for (const it of (menuWeek.items || [])) {
        if (it.availability === "sold_out") continue;
        menuItems.push({
          item_id: it.item_id || it.master_item_id,
          name: it.name,
          image_url: it.image_url,
          default_price_cents: it.price_cents || it.default_price_cents,
          veg_type: it.veg_type,
        });
      }
    }

    const combos: any[] = [];
    if (comboWeek?.package_enabled && comboWeek.package?.name) {
      combos.push({
        ...comboWeek.package,
        week_start: comboWeek.week_start,
        menu_id: comboWeek.menu_id,
        eligible_master_ids: comboWeek.package.eligible_master_ids || [],
      });
    }
    return { menu: menuItems, combos, catering: builder.catering || [], menuWeek, comboWeek };
  }, [builder]);

  // Master menu lookup (id → item) for combo picker rendering.
  const masterMap: Record<string, any> = useMemo(() => {
    const m: Record<string, any> = {};
    for (const mi of (builder?.master_menu || [])) m[mi.item_id] = mi;
    return m;
  }, [builder]);

  const subtotal = picked.reduce((s, p) => s + p.price_cents * (p.quantity || 1)
    * (p.kind === "catering" ? (p.catering_guest_count || 1) : 1), 0);
  const deliveryFee = builder?.settings?.delivery_fee_cents || 0;
  const taxRate = builder?.settings?.tax_rate_bps || 0;
  const taxEnabled = builder?.settings?.tax_enabled;
  const pmCfg = builder?.settings?.payment_methods?.[paymentMethod] || {};
  const taxable = subtotal + deliveryFee;
  const tax = (taxEnabled && pmCfg?.tax_enabled) ? Math.floor(taxable * taxRate / 10000) : 0;
  const total = taxable + tax;

  // -------- Item add helpers --------------------------------------------
  const addMenuItem = (m: MenuItem) => {
    setPicked(prev => {
      const key = `menu_${m.item_id}`;
      const existing = prev.find(p => p.key === key);
      if (existing) return prev.map(p => p.key === key ? { ...p, quantity: p.quantity + 1 } : p);
      return [...prev, { key, kind: "menu", ref_id: m.item_id, name: m.name,
                          price_cents: m.default_price_cents || 0, quantity: 1 }];
    });
  };
  const addCatering = (pkg: any, guests: number) => {
    setPicked(prev => [...prev, {
      key: `cat_${pkg.package_id}_${Date.now()}`, kind: "catering",
      ref_id: pkg.package_id, name: pkg.name,
      price_cents: pkg.price_cents, quantity: 1, catering_guest_count: guests,
    }]);
  };
  const addCombo = (combo: any) => {
    // Open inline picker so admin can choose exact items (mirrors customer app UX).
    setComboPicker({ combo, qty: {} });
  };
  const addCustom = () => {
    const name = customName.trim();
    const dollars = parseFloat(customPrice);
    if (!name) { Alert.alert("Missing name", "Enter a dish name."); return; }
    if (isNaN(dollars) || dollars < 0) { Alert.alert("Invalid price", "Enter a valid price."); return; }
    const cents = Math.round(dollars * 100);
    setPicked(prev => [...prev, {
      key: `custom_${Date.now()}`,
      kind: "custom",
      ref_id: "",
      name,
      price_cents: cents,
      quantity: 1,
    }]);
    setCustomName("");
    setCustomPrice("");
  };
  const bumpComboQty = (mid: string, delta: number) => {
    setComboPicker(cp => {
      if (!cp) return cp;
      const pickCount = Number(cp.combo.pick_count) || 0;
      const cur = cp.qty[mid] || 0;
      const total = Object.values(cp.qty).reduce((a, b) => a + b, 0);
      const next = cur + delta;
      if (next < 0) return cp;
      if (delta > 0 && total >= pickCount) return cp;      // don't exceed pickCount
      const newQty = { ...cp.qty, [mid]: next };
      if (newQty[mid] === 0) delete newQty[mid];
      return { ...cp, qty: newQty };
    });
  };
  const confirmComboPicker = () => {
    if (!comboPicker) return;
    const { combo, qty } = comboPicker;
    const pickCount = Number(combo.pick_count) || 0;
    // Expand qty map → picks[] with repeats (preserves quantities per master id)
    const picks: string[] = [];
    for (const [mid, q] of Object.entries(qty)) {
      for (let i = 0; i < q; i++) picks.push(mid);
    }
    if (picks.length !== pickCount) {
      Alert.alert("Pick exactly " + pickCount, `You've picked ${picks.length} of ${pickCount} portions.`);
      return;
    }
    // Compute per-portion surcharge total for pricing display.
    const surchargeMap: Record<string, number> = combo.item_surcharges_cents || {};
    let surcharge = 0;
    for (const [mid, q] of Object.entries(qty)) surcharge += (surchargeMap[mid] || 0) * (q as number);
    const unit = (combo.price_cents || 0) + surcharge;
    setPicked(prev => [...prev, {
      key: `combo_${combo.menu_id || combo.week_start}_${Date.now()}`,
      kind: "weekly_package",
      ref_id: combo.menu_id || combo.week_start,
      name: combo.name || "Weekly Combo",
      price_cents: unit,
      quantity: 1,
      package_selections: picks,
    }]);
    setComboPicker(null);
  };
  const bump = (key: string, delta: number) => {
    setPicked(prev => prev.map(p => p.key === key
      ? { ...p, quantity: Math.max(1, p.quantity + delta) } : p).filter(p => p.quantity > 0));
  };
  const remove = (key: string) => setPicked(prev => prev.filter(p => p.key !== key));

  // -------- Submit -------------------------------------------------------
  const canSubmit =
    (selectedCust || (showNewCustomer && newCust.name.trim() && newCust.phone.trim())) &&
    picked.length > 0 && selectedSlot &&
    address.line1.trim() && address.postal_code.trim();

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    const body: any = {
      items: picked.map(p => ({
        kind: p.kind, ref_id: p.ref_id, quantity: p.quantity,
        catering_guest_count: p.catering_guest_count,
        package_selections: p.package_selections,
        custom_name: p.kind === "custom" ? p.name : undefined,
        custom_price_cents: p.kind === "custom" ? p.price_cents : undefined,
      })),
      address, slot: { date: selectedSlot!.date, window: selectedSlot!.window },
      phone: selectedCust?.phone || newCust.phone,
      special_instructions: notes,
      payment_method: paymentMethod,
      mark_as_paid: markAsPaid,
      driver_partner_id: driverId,
    };
    if (selectedCust) body.user_id = selectedCust.user_id;
    else body.new_customer = { ...newCust, address };

    const r = await adminApi.post<any>("/admin/orders/create", body);
    setSubmitting(false);
    if (r.ok) {
      Alert.alert("Order created",
        `Order ${r.data.order.order_id.slice(-6).toUpperCase()} for ${r.data.customer.name}`);
      resetAll();
      onCreated();
      onClose();
    } else {
      Alert.alert("Create failed", r.error);
    }
  };

  // ---- Render -----------------------------------------------------------
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} transparent>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.header}>
            <Text style={styles.title}>Create new order</Text>
            <TouchableOpacity onPress={onClose} testID="new-order-close">
              <Ionicons name="close" size={24} color={colors.text} />
            </TouchableOpacity>
          </View>

          {loading ? <ActivityIndicator size="large" color={colors.primary} style={{ padding: spacing.xl }} /> : (
            <ScrollView contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}>
              {/* --- CUSTOMER --- */}
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Ionicons name="person-outline" size={18} color={colors.primary} />
                  <Text style={styles.cardTitle}>1. Customer</Text>
                  {selectedCust && (
                    <View style={styles.chipOn}><Text style={styles.chipOnText}>{selectedCust.name}</Text></View>
                  )}
                </View>

                {!showNewCustomer ? (
                  <>
                    <TextInput
                      testID="cust-search" placeholder="Search by name, phone, or email…"
                      value={custSearch} onChangeText={setCustSearch}
                      style={styles.input}
                      placeholderTextColor={colors.textMuted}
                    />
                    <ScrollView style={{ maxHeight: 240 }}>
                      {filteredCustomers.map(c => {
                        const a = c.default_address || {};
                        const addrLine = [a.line1, a.line2, a.city, a.postal_code]
                          .filter(Boolean).join(", ");
                        return (
                          <TouchableOpacity
                            key={c.user_id}
                            testID={`cust-${c.user_id}`}
                            onPress={() => setSelectedCust(c)}
                            style={[styles.custRow, selectedCust?.user_id === c.user_id && styles.custRowSelected]}
                          >
                            <View style={{ flex: 1 }}>
                              <Text style={styles.custName}>{c.name || "(no name)"}</Text>
                              {addrLine ? (
                                <View style={styles.custAddrRow}>
                                  <Ionicons name="location-outline" size={12} color={colors.textMuted} />
                                  <Text style={styles.custAddr} numberOfLines={1}>{addrLine}</Text>
                                </View>
                              ) : (
                                <Text style={styles.custAddr}>No saved address</Text>
                              )}
                              <Text style={styles.custMeta}>{c.phone || "—"} · {c.email || "no email"}</Text>
                            </View>
                            {selectedCust?.user_id === c.user_id && <Ionicons name="checkmark-circle" size={20} color={colors.success} />}
                          </TouchableOpacity>
                        );
                      })}
                    </ScrollView>
                    <TouchableOpacity onPress={() => { setShowNewCustomer(true); setSelectedCust(null); }} style={styles.linkBtn}>
                      <Ionicons name="add-circle-outline" size={16} color={colors.primary} />
                      <Text style={styles.linkBtnText}>Add new customer</Text>
                    </TouchableOpacity>
                  </>
                ) : (
                  <>
                    <TextInput placeholder="Name *" value={newCust.name} onChangeText={t => setNewCust({...newCust, name:t})} style={styles.input} placeholderTextColor={colors.textMuted} testID="new-cust-name" />
                    <TextInput placeholder="Phone * (+14161234567)" value={newCust.phone} onChangeText={t => setNewCust({...newCust, phone:t})} keyboardType="phone-pad" style={styles.input} placeholderTextColor={colors.textMuted} testID="new-cust-phone" />
                    <TextInput placeholder="Email (optional)" value={newCust.email} onChangeText={t => setNewCust({...newCust, email:t})} keyboardType="email-address" autoCapitalize="none" style={styles.input} placeholderTextColor={colors.textMuted} testID="new-cust-email" />
                    <Text style={styles.newCustAddrLabel}>Address (saved to the customer & used for this order)</Text>
                    <TextInput placeholder="Street address *" value={address.line1} onChangeText={t => setAddress({...address, line1:t})} style={styles.input} placeholderTextColor={colors.textMuted} testID="new-cust-line1" />
                    <TextInput placeholder="Unit / Apt (optional)" value={address.line2} onChangeText={t => setAddress({...address, line2:t})} style={styles.input} placeholderTextColor={colors.textMuted} testID="new-cust-line2" />
                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <TextInput placeholder="City" value={address.city} onChangeText={t => setAddress({...address, city:t})} style={[styles.input, { flex: 1 }]} placeholderTextColor={colors.textMuted} testID="new-cust-city" />
                      <TextInput placeholder="Province" value={address.province} onChangeText={t => setAddress({...address, province:t})} autoCapitalize="characters" style={[styles.input, { width: 90 }]} placeholderTextColor={colors.textMuted} testID="new-cust-province" />
                    </View>
                    <TextInput placeholder="Postal code *" value={address.postal_code} onChangeText={t => setAddress({...address, postal_code:t})} autoCapitalize="characters" style={styles.input} placeholderTextColor={colors.textMuted} testID="new-cust-postal" />
                    <TouchableOpacity onPress={() => setShowNewCustomer(false)} style={styles.linkBtn}>
                      <Ionicons name="arrow-back" size={16} color={colors.primary} />
                      <Text style={styles.linkBtnText}>Pick from existing instead</Text>
                    </TouchableOpacity>
                  </>
                )}
              </View>

              {/* --- ITEMS --- */}
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Ionicons name="basket-outline" size={18} color={colors.primary} />
                  <Text style={styles.cardTitle}>2. Items ({picked.length})</Text>
                </View>
                <View style={{ flexDirection: "row", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                  {MODES.map(m => (
                    <TouchableOpacity key={m.key} onPress={() => { setMode(m.key as any); setComboPicker(null); }}
                      style={[styles.modeBtn, mode === m.key && styles.modeBtnOn]}
                      testID={`mode-${m.key}`}>
                      <Ionicons name={m.icon} size={14} color={mode === m.key ? "#fff" : colors.text} />
                      <Text style={[styles.modeBtnText, mode === m.key && { color: "#fff" }]}>{m.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <ScrollView style={{ maxHeight: 240 }}>
                  {mode === "menu" && availableItems.menuWeek && (
                    <Text style={styles.sourceHint}>
                      Sourcing from week of {availableItems.menuWeek.week_start}
                    </Text>
                  )}
                  {mode === "menu" && availableItems.menu.map(m => (
                    <View key={m.item_id} style={styles.itemRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemName}>{m.name}</Text>
                        <Text style={styles.itemMeta}>{money(m.default_price_cents || 0)}{m.veg_type ? ` · ${m.veg_type}` : ""}</Text>
                      </View>
                      <TouchableOpacity onPress={() => addMenuItem(m)} style={styles.addBtn} testID={`add-${m.item_id}`}>
                        <Ionicons name="add" size={18} color="#fff" />
                      </TouchableOpacity>
                    </View>
                  ))}
                  {mode === "menu" && availableItems.menu.length === 0 && (
                    <Text style={styles.emptyMini}>
                      No à la carte items available. Enable à la carte + add items to a weekly menu in Admin → Menu first.
                    </Text>
                  )}

                  {mode === "weekly_package" && !comboPicker && availableItems.comboWeek && (
                    <Text style={styles.sourceHint}>
                      Sourcing from week of {availableItems.comboWeek.week_start}
                    </Text>
                  )}
                  {mode === "weekly_package" && !comboPicker && availableItems.combos.map((c: any, i: number) => (
                    <View key={i} style={styles.itemRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemName}>{c.name}</Text>
                        <Text style={styles.itemMeta}>
                          {money(c.price_cents)} · pick {c.pick_count} · {c.eligible_master_ids?.length || 0} eligible items
                        </Text>
                      </View>
                      <TouchableOpacity onPress={() => addCombo(c)} style={styles.addBtn} testID="add-combo">
                        <Ionicons name="add" size={18} color="#fff" />
                      </TouchableOpacity>
                    </View>
                  ))}
                  {mode === "weekly_package" && !comboPicker && availableItems.combos.length === 0 && (
                    <Text style={styles.emptyMini}>
                      No weekly combo enabled. Enable it in Admin → Menu → &quot;Weekly Combo&quot; settings.
                    </Text>
                  )}

                  {/* Combo item picker — mirrors customer /menu/package/[id] UX */}
                  {mode === "weekly_package" && comboPicker && (() => {
                    const { combo, qty } = comboPicker;
                    const pickCount = Number(combo.pick_count) || 0;
                    const totalPicked = Object.values(qty).reduce((a, b) => a + b, 0);
                    const remaining = Math.max(0, pickCount - totalPicked);
                    const surchargeMap: Record<string, number> = combo.item_surcharges_cents || {};
                    let surcharge = 0;
                    for (const [mid, q] of Object.entries(qty)) surcharge += (surchargeMap[mid] || 0) * (q as number);
                    const effectiveUnit = (combo.price_cents || 0) + surcharge;
                    const eligible: string[] = combo.eligible_master_ids || [];
                    return (
                      <View>
                        <View style={styles.comboPickerHeader}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.comboPickerTitle}>{combo.name}</Text>
                            <Text style={styles.comboPickerMeta}>
                              {money(effectiveUnit)} · {remaining > 0 ? `Pick ${remaining} more` : "All picked ✓"}  · {totalPicked} / {pickCount}
                            </Text>
                          </View>
                          <TouchableOpacity onPress={() => setComboPicker(null)} style={styles.linkBtn}>
                            <Ionicons name="close" size={16} color={colors.primary} />
                            <Text style={styles.linkBtnText}>Cancel</Text>
                          </TouchableOpacity>
                        </View>
                        {eligible.map((mid) => {
                          const mi = masterMap[mid];
                          if (!mi) return null;
                          const q = qty[mid] || 0;
                          const extra = surchargeMap[mid] || 0;
                          const atMax = totalPicked >= pickCount;
                          return (
                            <View key={mid} style={styles.pickerRow}>
                              {mi.image_url ? (
                                <Image
                                  source={{ uri: mi.image_url }}
                                  style={styles.pickerThumb}
                                />
                              ) : (
                                <View style={[styles.pickerThumb, { backgroundColor: colors.surfaceAlt }]} />
                              )}
                              <View style={{ flex: 1 }}>
                                <Text style={styles.itemName} numberOfLines={1}>{mi.name}</Text>
                                <Text style={styles.itemMeta}>
                                  {mi.veg_type ? mi.veg_type + " · " : ""}
                                  À la carte {money(mi.default_price_cents || 0)}
                                  {extra > 0 ? ` · +${money(extra)}` : ""}
                                </Text>
                              </View>
                              <View style={styles.qtyBox}>
                                <TouchableOpacity
                                  onPress={() => bumpComboQty(mid, -1)}
                                  disabled={q <= 0}
                                  style={[styles.qtyBtn, q <= 0 && { opacity: 0.35 }]}>
                                  <Text style={styles.qtyBtnText}>−</Text>
                                </TouchableOpacity>
                                <Text style={styles.qtyVal}>{q}</Text>
                                <TouchableOpacity
                                  onPress={() => bumpComboQty(mid, 1)}
                                  disabled={atMax}
                                  style={[styles.qtyBtn, atMax && { opacity: 0.35 }]}
                                  testID={`pick-plus-${mid}`}>
                                  <Text style={styles.qtyBtnText}>+</Text>
                                </TouchableOpacity>
                              </View>
                            </View>
                          );
                        })}
                        <TouchableOpacity
                          onPress={confirmComboPicker}
                          disabled={remaining > 0}
                          style={[styles.confirmComboBtn, remaining > 0 && { opacity: 0.5 }]}
                          testID="confirm-combo">
                          <Ionicons name="checkmark-circle" size={16} color="#fff" />
                          <Text style={styles.createBtnText}>
                            {remaining > 0 ? `Pick ${remaining} more` : `Add to cart · ${money(effectiveUnit)}`}
                          </Text>
                        </TouchableOpacity>
                      </View>
                    );
                  })()}

                  {mode === "catering" && availableItems.catering.map((p: any) => (
                    <View key={p.package_id} style={styles.itemRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemName}>{p.emoji} {p.name}</Text>
                        <Text style={styles.itemMeta}>{money(p.price_cents)} / guest · min {p.min_guests || 0} guests</Text>
                      </View>
                      <TouchableOpacity onPress={() => {
                        const g = p.min_guests || 10;
                        addCatering(p, g);
                      }} style={styles.addBtn}>
                        <Ionicons name="add" size={18} color="#fff" />
                      </TouchableOpacity>
                    </View>
                  ))}

                  {mode === "custom" && (
                    <View style={{ gap: 8, paddingVertical: 4 }}>
                      <Text style={styles.emptyMini}>
                        Add a one-off dish that isn&apos;t on the master menu. Just a name and a price.
                      </Text>
                      <Text style={styles.label}>Dish name</Text>
                      <TextInput
                        testID="custom-name"
                        placeholder="e.g. Special Thali"
                        value={customName}
                        onChangeText={setCustomName}
                        style={styles.input}
                        placeholderTextColor={colors.textMuted}
                      />
                      <Text style={styles.label}>Price (CA$)</Text>
                      <TextInput
                        testID="custom-price"
                        placeholder="e.g. 18.99"
                        value={customPrice}
                        onChangeText={setCustomPrice}
                        keyboardType="decimal-pad"
                        style={styles.input}
                        placeholderTextColor={colors.textMuted}
                      />
                      <TouchableOpacity onPress={addCustom} style={styles.confirmComboBtn} testID="add-custom">
                        <Ionicons name="add-circle" size={16} color="#fff" />
                        <Text style={styles.createBtnText}>Add custom dish</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </ScrollView>

                {picked.length > 0 && (
                  <View style={styles.cartBox}>
                    <Text style={styles.subhead}>CART</Text>
                    {picked.map(p => {
                      // For combos, aggregate picks → "Biryani × 2, Ilish × 1"
                      let comboLines: string | null = null;
                      if (p.kind === "weekly_package" && p.package_selections?.length) {
                        const counts: Record<string, number> = {};
                        for (const mid of p.package_selections) counts[mid] = (counts[mid] || 0) + 1;
                        comboLines = Object.entries(counts)
                          .map(([mid, q]) => {
                            const name = masterMap[mid]?.name || mid;
                            return q > 1 ? `${name} × ${q}` : name;
                          })
                          .join(", ");
                      }
                      return (
                        <View key={p.key} style={styles.cartRow}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.cartName}>{p.name}</Text>
                            <Text style={styles.cartMeta}>
                              {p.kind === "catering"
                                ? `${p.catering_guest_count} guests × ${money(p.price_cents)}`
                                : `${money(p.price_cents)} each`}
                            </Text>
                            {comboLines && (
                              <Text style={[styles.cartMeta, { color: colors.primary, marginTop: 2 }]} numberOfLines={2}>
                                • {comboLines}
                              </Text>
                            )}
                          </View>
                          <View style={styles.qtyBox}>
                            <TouchableOpacity onPress={() => bump(p.key, -1)} style={styles.qtyBtn}><Text style={styles.qtyBtnText}>−</Text></TouchableOpacity>
                            <Text style={styles.qtyVal}>{p.quantity}</Text>
                            <TouchableOpacity onPress={() => bump(p.key, 1)} style={styles.qtyBtn}><Text style={styles.qtyBtnText}>+</Text></TouchableOpacity>
                          </View>
                          <TouchableOpacity onPress={() => remove(p.key)}>
                            <Ionicons name="trash-outline" size={16} color={colors.danger} />
                          </TouchableOpacity>
                        </View>
                      );
                    })}
                  </View>
                )}
              </View>

              {/* --- DELIVERY --- */}
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Ionicons name="location-outline" size={18} color={colors.primary} />
                  <Text style={styles.cardTitle}>3. Delivery</Text>
                </View>
                <Text style={styles.label}>Delivery date</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                  {(builder?.delivery_slots || []).map((s: Slot) => (
                    <TouchableOpacity key={s.date} onPress={() => setSelectedSlot(s)}
                      style={[styles.slotChip, selectedSlot?.date === s.date && styles.slotChipOn]}>
                      <Text style={[styles.slotChipText, selectedSlot?.date === s.date && { color: "#fff" }]}>{s.label}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
                <Text style={styles.label}>Address line 1</Text>
                <TextInput placeholder="Street address" value={address.line1} onChangeText={t => setAddress({...address, line1:t})} style={styles.input} placeholderTextColor={colors.textMuted} testID="addr-line1" />
                <Text style={styles.label}>Line 2 (unit / apt)</Text>
                <TextInput placeholder="Unit / Apt (optional)" value={address.line2} onChangeText={t => setAddress({...address, line2:t})} style={styles.input} placeholderTextColor={colors.textMuted} />
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>City</Text>
                    <TextInput value={address.city} onChangeText={t => setAddress({...address, city:t})} style={styles.input} placeholderTextColor={colors.textMuted} />
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={styles.label}>Province</Text>
                    <TextInput value={address.province} onChangeText={t => setAddress({...address, province:t})} autoCapitalize="characters" style={styles.input} placeholderTextColor={colors.textMuted} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Postal code</Text>
                    <TextInput value={address.postal_code} onChangeText={t => setAddress({...address, postal_code:t})} autoCapitalize="characters" style={styles.input} placeholderTextColor={colors.textMuted} testID="addr-postal" />
                  </View>
                </View>
              </View>

              {/* --- PAYMENT + DRIVER --- */}
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <Ionicons name="card-outline" size={18} color={colors.primary} />
                  <Text style={styles.cardTitle}>4. Payment & driver</Text>
                </View>
                <Text style={styles.label}>Payment method</Text>
                <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
                  {["cod", "interac"].map(pm => (
                    <TouchableOpacity key={pm} onPress={() => setPaymentMethod(pm as any)}
                      style={[styles.modeBtn, paymentMethod === pm && styles.modeBtnOn]}>
                      <Text style={[styles.modeBtnText, paymentMethod === pm && { color: "#fff" }]}>{pm.toUpperCase()}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <TouchableOpacity onPress={() => setMarkAsPaid(v => !v)} style={styles.toggleRow} testID="mark-paid">
                  <View style={[styles.checkbox, markAsPaid && styles.checkboxOn]}>
                    {markAsPaid && <Ionicons name="checkmark" size={14} color="#fff" />}
                  </View>
                  <Text style={styles.toggleText}>Mark as paid now (money already collected)</Text>
                </TouchableOpacity>

                <Text style={styles.label}>Assign driver (optional)</Text>
                <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
                  <TouchableOpacity onPress={() => setDriverId(null)}
                    style={[styles.driverChip, driverId === null && styles.driverChipOn]}>
                    <Text style={[styles.driverChipText, driverId === null && { color: "#fff" }]}>Unassigned</Text>
                  </TouchableOpacity>
                  {(builder?.delivery_partners || []).map((p: Partner) => (
                    <TouchableOpacity key={p.partner_id} onPress={() => setDriverId(p.partner_id)}
                      style={[styles.driverChip, driverId === p.partner_id && styles.driverChipOn]}
                      testID={`driver-${p.partner_id}`}>
                      <Ionicons name={p.vehicle === "car" ? "car-outline" : "bicycle-outline"} size={12} color={driverId === p.partner_id ? "#fff" : colors.text} />
                      <Text style={[styles.driverChipText, driverId === p.partner_id && { color: "#fff" }]}>{p.name}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {driverId && (
                  <Text style={[styles.emptyMini, { marginTop: 4 }]}>
                    ℹ️ Order will be auto-set to <Text style={{ fontWeight: "800" }}>packed</Text> and pushed to driver&apos;s queue.
                  </Text>
                )}

                <Text style={styles.label}>Special instructions</Text>
                <TextInput placeholder="No spice, ring doorbell, etc." value={notes} onChangeText={setNotes} multiline style={[styles.input, { height: 60 }]} placeholderTextColor={colors.textMuted} />
              </View>

              {/* --- TOTALS --- */}
              <View style={styles.totalsBox}>
                <View style={styles.totalRow}><Text style={styles.totalLbl}>Subtotal</Text><Text style={styles.totalVal}>{money(subtotal)}</Text></View>
                <View style={styles.totalRow}><Text style={styles.totalLbl}>Delivery fee</Text><Text style={styles.totalVal}>{money(deliveryFee)}</Text></View>
                {tax > 0 && (
                  <View style={styles.totalRow}><Text style={styles.totalLbl}>{builder?.settings?.tax_label || "Tax"}</Text><Text style={styles.totalVal}>{money(tax)}</Text></View>
                )}
                <View style={[styles.totalRow, { marginTop: 4, paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.border }]}>
                  <Text style={[styles.totalLbl, { fontSize: 16, fontWeight: "800" }]}>Total</Text>
                  <Text style={[styles.totalVal, { fontSize: 18, color: colors.primary }]}>{money(total)}</Text>
                </View>
              </View>

              <TouchableOpacity
                onPress={submit}
                disabled={!canSubmit || submitting}
                style={[styles.createBtn, (!canSubmit || submitting) && { opacity: 0.5 }]}
                testID="submit-order"
              >
                {submitting
                  ? <ActivityIndicator color="#fff" />
                  : <>
                      <Ionicons name="checkmark-circle" size={18} color="#fff" />
                      <Text style={styles.createBtnText}>Create order · {money(total)}</Text>
                    </>}
              </TouchableOpacity>
              <View style={{ height: 20 }} />
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.background, borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: "94%" },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { fontSize: 18, fontWeight: "800", color: colors.text },

  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, gap: 6, borderWidth: 1, borderColor: colors.border, ...shadows.soft },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 4 },
  cardTitle: { color: colors.text, fontWeight: "800", fontSize: 14, flex: 1 },
  chipOn: { backgroundColor: colors.success + "22", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 3 },
  chipOnText: { color: colors.success, fontSize: 11, fontWeight: "800" },

  label: { color: colors.textMuted, letterSpacing: 1.5, fontSize: 10, fontWeight: "800", marginTop: 6 },
  input: { backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 10, paddingVertical: 8, color: colors.text, fontSize: 13 },

  custRow: { flexDirection: "row", alignItems: "center", paddingVertical: 8, paddingHorizontal: 10, borderRadius: radius.md, borderWidth: 1, borderColor: "transparent", marginBottom: 4 },
  custRowSelected: { backgroundColor: colors.primary + "11", borderColor: colors.primary },
  custName: { color: colors.text, fontWeight: "700", fontSize: 13 },
  custAddrRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  custAddr: { color: colors.textMuted, fontSize: 11, fontStyle: "italic", flex: 1 },
  custMeta: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  linkBtn: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  linkBtnText: { color: colors.primary, fontWeight: "700", fontSize: 12 },
  newCustAddrLabel: { color: colors.textMuted, fontSize: 11, fontWeight: "700", marginTop: 8, marginBottom: 2 },

  modeBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background },
  modeBtnOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  modeBtnText: { color: colors.text, fontSize: 11, fontWeight: "800" },

  itemRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.surfaceAlt },
  itemName: { color: colors.text, fontWeight: "700", fontSize: 13 },
  itemMeta: { color: colors.textMuted, fontSize: 11 },
  addBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, padding: 6 },

  cartBox: { marginTop: 8, backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: 8, gap: 4 },
  subhead: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800" },
  cartRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 4 },
  cartName: { color: colors.text, fontWeight: "700", fontSize: 12 },
  cartMeta: { color: colors.textMuted, fontSize: 10 },
  qtyBox: { flexDirection: "row", alignItems: "center", gap: 6 },
  qtyBtn: { width: 22, height: 22, borderRadius: 11, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  qtyBtnText: { color: "#fff", fontWeight: "800", fontSize: 14 },
  qtyVal: { color: colors.text, fontWeight: "800", minWidth: 20, textAlign: "center" },

  slotChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background },
  slotChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  slotChipText: { color: colors.text, fontSize: 12, fontWeight: "700" },

  toggleRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8 },
  toggleText: { color: colors.text, fontSize: 12, fontWeight: "600", flex: 1 },
  checkbox: { width: 20, height: 20, borderRadius: 4, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  checkboxOn: { backgroundColor: colors.primary, borderColor: colors.primary },

  driverChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background },
  driverChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  driverChipText: { color: colors.text, fontSize: 11, fontWeight: "700" },

  totalsBox: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: 4 },
  totalRow: { flexDirection: "row", justifyContent: "space-between" },
  totalLbl: { color: colors.text, fontSize: 13 },
  totalVal: { color: colors.text, fontSize: 13, fontWeight: "700" },

  createBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.pill, ...shadows.soft },
  createBtnText: { color: "#fff", fontWeight: "800", fontSize: 15 },

  emptyMini: { color: colors.textMuted, fontSize: 12, fontStyle: "italic", padding: 8 },
  sourceHint: { color: colors.textMuted, fontSize: 10, letterSpacing: 1, fontWeight: "800", paddingHorizontal: 4, paddingBottom: 6 },
  comboPickerHeader: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 6, paddingHorizontal: 4, marginBottom: 4, borderBottomWidth: 1, borderBottomColor: colors.border },
  comboPickerTitle: { color: colors.text, fontWeight: "800", fontSize: 14 },
  comboPickerMeta: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  pickerRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.surfaceAlt },
  pickerThumb: { width: 40, height: 40, borderRadius: radius.md },
  confirmComboBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.primary, paddingVertical: 12, borderRadius: radius.pill, marginTop: 10 },
});
