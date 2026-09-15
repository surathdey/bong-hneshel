import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, TextInput,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from "react-native";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Ionicons from "@react-native-vector-icons/ionicons";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { useCart } from "@/src/cart";
import { useAuth } from "@/src/auth";
import { api, BACKEND_URL } from "@/src/api";
import { mediaUrl, getBackendUrl } from "@/src/utils/backendUrl";
import { colors, spacing, radius, shadows } from "@/src/theme";
import { centsToCAD, currentWeekDeliverySlots } from "@/src/utils/format";
import { AddressAutocomplete, StructuredAddress } from "@/src/components/AddressAutocomplete";

type PaymentSlug = "card" | "cod" | "paypal" | "interac";
type PaymentMethodPublic = {
  enabled: boolean;
  tax_enabled: boolean;
  email?: string;         // interac
  instructions?: string;  // interac
};
type PublicSettings = {
  payment_methods?: Record<string, PaymentMethodPublic>;
  tax_label?: string;
  delivery_days?: number[];
  ordering_days?: number[];
  loyalty_enabled?: boolean;
};

const GUEST_ADDRESS_KEY = "curryco.guest_address.v1";

type Quote = {
  subtotal_cents: number; delivery_fee_cents: number; discount_cents: number;
  points_redeemed_cents: number; total_cents: number; coupon_code: string | null; points_available: number;
  tax_cents?: number; tax_label?: string; tax_enabled?: boolean;
  delivery_distance_km?: number | null; delivery_fee_tier?: string;
  delivery_time_window?: string; delivery_condo_policy?: string;
};

export default function CartScreen() {
  const { items, setQty, remove, clear, subtotalCents } = useCart();
  const { user, refresh } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [line1, setLine1] = useState("");
  const [line2, setLine2] = useState("");
  const [city, setCity] = useState("");
  const [postal, setPostal] = useState("");
  // Exact coordinates from the Google Places pick — sent to the backend so the
  // delivery-distance fee is measured from the precise point (not a re-geocode
  // of free text, which used to default the city to Toronto and mis-charge).
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [phone, setPhone] = useState(user?.phone || "");
  const [email, setEmail] = useState((user as any)?.email && !((user as any)?.email || "").includes("@guest") ? (user as any).email : "");
  // Recipient name. Pre-fills from user profile so returning customers
  // don't re-type it. Guests type it here → we ship it as address.name
  // AND server saves it back on their user record so the admin sees the
  // real name instead of "Guest 1", "Guest 2".
  const looksLikeGuestName = (n?: string) => {
    const s = (n || "").trim().toLowerCase();
    return !s || s === "guest" || s.startsWith("guest ") || s.startsWith("guest_");
  };
  const [recipientName, setRecipientName] = useState(
    looksLikeGuestName(user?.name) ? "" : (user?.name || "")
  );
  const [couponCode, setCouponCode] = useState("");
  const [redeemPoints, setRedeemPoints] = useState(0);
  const [instructions, setInstructions] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [placing, setPlacing] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentSlug>("cod");
  const [publicSettings, setPublicSettings] = useState<PublicSettings | null>(null);
  const [interacBanner, setInteracBanner] = useState<{ email: string; instructions: string; amount: number; orderId: string } | null>(null);

  const slots = useMemo(
    () => currentWeekDeliverySlots(publicSettings?.delivery_days),
    [publicSettings?.delivery_days]
  );
  const [selectedSlot, setSelectedSlot] = useState(slots[0]);

  // Keep selected slot in sync when delivery-day config arrives from /settings.
  useEffect(() => {
    if (!selectedSlot && slots[0]) setSelectedSlot(slots[0]);
    else if (selectedSlot && !slots.some(s => s.date === selectedSlot.date && s.window === selectedSlot.window)) {
      setSelectedSlot(slots[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots]);

  // Fetch payment-method configuration once — needed to render the right options + auto-tax choice.
  useEffect(() => {
    (async () => {
      const r = await api.get<PublicSettings>("/settings");
      if (r.ok) {
        setPublicSettings(r.data);
        // Auto-pick the first enabled method. Card (Stripe) is currently
        // disabled during MVP so this typically lands on COD.
        const pm = r.data.payment_methods || {};
        const ORDER: PaymentSlug[] = ["cod", "interac", "paypal", "card"];
        const currentKey: Record<PaymentSlug, string> = { card: "stripe", cod: "cod", paypal: "paypal", interac: "interac" };
        if (!pm[currentKey[paymentMethod]]?.enabled) {
          const firstEnabled = ORDER.find(k => pm[currentKey[k]]?.enabled);
          if (firstEnabled) setPaymentMethod(firstEnabled);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const interacCfg = publicSettings?.payment_methods?.interac;
  const pmEnabled = (slug: PaymentSlug): boolean => {
    const key = ({ card: "stripe", cod: "cod", paypal: "paypal", interac: "interac" } as const)[slug];
    return !!publicSettings?.payment_methods?.[key]?.enabled;
  };

  // Pre-fill saved address: logged-in user's default_address, or the guest's AsyncStorage copy.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Logged in — server sends default_address on /auth/me.
      const savedFromUser: any = (user as any)?.default_address;
      if (savedFromUser && savedFromUser.line1) {
        if (cancelled) return;
        if (!line1) setLine1(savedFromUser.line1 || "");
        if (!line2) setLine2(savedFromUser.line2 || "");
        if (!postal) setPostal(savedFromUser.postal_code || "");
        if (savedFromUser.city) setCity(savedFromUser.city);
        if (savedFromUser.lat != null && savedFromUser.lng != null) setCoords({ lat: savedFromUser.lat, lng: savedFromUser.lng });
        if (savedFromUser.email && !email) setEmail(savedFromUser.email);
        return;
      }
      // Guest — pull from AsyncStorage.
      try {
        const raw = await AsyncStorage.getItem(GUEST_ADDRESS_KEY);
        if (!raw || cancelled) return;
        const g = JSON.parse(raw);
        if (g?.line1 && !line1) setLine1(g.line1);
        if (g?.line2 && !line2) setLine2(g.line2);
        if (g?.postal_code && !postal) setPostal(g.postal_code);
        if (g?.city) setCity(g.city);
        if (g?.lat != null && g?.lng != null) setCoords({ lat: g.lat, lng: g.lng });
        if (g?.email && !email) setEmail(g.email);
      } catch (e) { /* ignore */ }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);

  // Called when the user picks a Google Places suggestion — auto-fills city +
  // postal AND captures the exact lat/lng so distance-based fees are accurate.
  const onAddressPick = (addr: StructuredAddress) => {
    setLine1(addr.line1 || "");
    setCity(addr.city || "");
    setPostal(addr.postal_code || "");
    if (addr.lat != null && addr.lng != null) setCoords({ lat: addr.lat, lng: addr.lng });
    else setCoords(null);
  };

  // Persist address (guest → AsyncStorage; logged-in users are auto-saved by the backend on order creation).
  const persistAddressForGuest = async () => {
    if (user) return; // authenticated users saved server-side
    try {
      await AsyncStorage.setItem(GUEST_ADDRESS_KEY, JSON.stringify({
        line1, line2, city, province: "ON", postal_code: postal,
        lat: coords?.lat ?? null, lng: coords?.lng ?? null, email: email.trim(),
      }));
    } catch (e) { /* ignore */ }
  };

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const canPlace = items.length > 0 && recipientName.trim().length >= 2 && line1.trim().length > 3 && postal.trim().length >= 5 && phone.trim().length >= 7 && emailValid && selectedSlot;

  const fetchQuote = async () => {
    if (items.length === 0) { setQuote(null); return; }
    const r = await api.post<Quote>("/orders/quote", {
      items: items.map(i => ({
        kind: i.kind, ref_id: i.ref_id, quantity: i.quantity,
        catering_guest_count: i.catering_guest_count,
        catering_selections: i.catering_selections,
        package_selections: i.package_selections,
      })),
      address: { name: recipientName.trim(), email: email.trim(), line1: line1 || "TBD", line2, city, province: "ON", postal_code: postal || "M5V0A0", lat: coords?.lat, lng: coords?.lng },
      slot: { date: selectedSlot.date, window: selectedSlot.window },
      phone: phone || "0000000",
      coupon_code: couponCode || undefined,
      redeem_points: redeemPoints,
      payment_method: paymentMethod,
    });
    if (r.ok) setQuote(r.data);
  };

  useEffect(() => { fetchQuote(); /* eslint-disable-next-line */ }, [items, couponCode, redeemPoints, selectedSlot, paymentMethod, coords, city, postal]);

  const placeAndPay = async () => {
    if (!canPlace) { Alert.alert("Missing info", "Please add your name, delivery address, phone, a valid email and pick a slot."); return; }
    setPlacing(true);
    try {
      const orderResp = await api.post<{ order_id: string; total_cents: number; payment_method: string; status: string }>("/orders", {
        items: items.map(i => ({
          kind: i.kind, ref_id: i.ref_id, quantity: i.quantity,
          catering_guest_count: i.catering_guest_count,
          catering_selections: i.catering_selections,
          package_selections: i.package_selections,
        })),
        address: { name: recipientName.trim(), email: email.trim(), line1, line2, city, province: "ON", postal_code: postal, lat: coords?.lat, lng: coords?.lng },
        slot: { date: selectedSlot.date, window: selectedSlot.window },
        phone,
        coupon_code: couponCode || undefined,
        redeem_points: redeemPoints,
        special_instructions: instructions,
        payment_method: paymentMethod,
        client_base_url: getBackendUrl(),
      });
      if (!orderResp.ok) throw new Error(orderResp.error || "Could not create order");
      const orderId = orderResp.data.order_id;

      // Persist address for future visits (guest only; logged-in users are auto-saved server-side).
      persistAddressForGuest();

      // Cash on Delivery — order is already confirmed on the backend.
      if (paymentMethod === "cod") {
        clear();
        await refresh();
        router.replace(`/order/${orderId}`);
        return;
      }

      // Interac e-Transfer — show the payee email in a modal, then send them to the order page.
      if (paymentMethod === "interac") {
        const email = interacCfg?.email || "orders@curryandco.ca";
        const instr = interacCfg?.instructions || "Please note your order ID in the message field.";
        setInteracBanner({
          email, instructions: instr,
          amount: orderResp.data.total_cents,
          orderId,
        });
        clear();
        await refresh();
        setPlacing(false);
        return; // Banner dismiss will route to /order/{id}
      }

      // PayPal — not yet implemented. For now, show a friendly message.
      if (paymentMethod === "paypal") {
        Alert.alert(
          "PayPal not enabled yet",
          "PayPal checkout is coming soon. Your order was placed but is unpaid. Please contact support or choose another payment method.",
        );
        clear();
        await refresh();
        router.replace(`/order/${orderId}`);
        return;
      }

      // Card / Stripe → continue to hosted Stripe Checkout below
      // (Apple Pay / Google Pay / cards on the Stripe page).

      // If total is 0 (fully covered by points), skip Stripe.
      if (orderResp.data.total_cents <= 0) {
        clear();
        router.replace(`/order/${orderId}?paid=1`);
        return;
      }

      const originUrl = Platform.OS === "web" && typeof window !== "undefined"
        ? window.location.origin
        : Linking.createURL("").replace(/\/$/, "");

      const sessResp = await api.post<{ url: string; session_id: string }>("/checkout/session", {
        order_id: orderId,
        origin_url: originUrl,
      });
      if (!sessResp.ok) throw new Error(sessResp.error || "Could not start checkout");

      if (Platform.OS === "web" && typeof window !== "undefined") {
        window.location.href = sessResp.data.url;
        return;
      }
      const result = await WebBrowser.openAuthSessionAsync(sessResp.data.url, originUrl);
      // If user cancelled/dismissed, cancel the order server-side (deletes it + emails).
      const returnedWithSuccess =
        result.type === "success" && typeof result.url === "string" && result.url.includes("paid=1");
      if (!returnedWithSuccess) {
        await api.post(`/orders/${orderId}/cancel-unpaid`);
        Alert.alert("Payment cancelled", "No charge was made. We've sent you a courtesy email.");
        setPlacing(false);
        return;
      }
      clear();
      await refresh();
      router.replace(`/order/${orderId}`);
    } catch (e: any) {
      Alert.alert("Payment failed", e?.message || "Please try again.");
    } finally {
      setPlacing(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      {interacBanner && (
        <View style={styles.interacModalOverlay} testID="interac-modal">
          <View style={styles.interacModal}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Ionicons name="mail-open" size={22} color="#F9B233" />
              <Text style={styles.interacModalTitle}>Order placed — pay by Interac</Text>
            </View>
            <Text style={styles.interacModalLabel}>SEND EXACTLY</Text>
            <Text style={styles.interacModalTotal}>{centsToCAD(interacBanner.amount)}</Text>
            <Text style={styles.interacModalLabel}>TO THIS INTERAC EMAIL</Text>
            <Text selectable style={styles.interacModalEmail} testID="interac-modal-email">{interacBanner.email}</Text>
            <Text style={styles.interacModalLabel}>MESSAGE / NOTE</Text>
            <Text selectable style={styles.interacModalEmail}>Order {interacBanner.orderId}</Text>
            {!!interacBanner.instructions && (
              <Text style={styles.interacModalNote}>{interacBanner.instructions}</Text>
            )}
            <TouchableOpacity
              testID="interac-modal-continue"
              style={styles.interacModalBtn}
              onPress={() => {
                const id = interacBanner.orderId;
                setInteracBanner(null);
                router.replace(`/order/${id}`);
              }}
            >
              <Ionicons name="checkmark" size={16} color="#fff" />
              <Text style={styles.interacModalBtnText}>{"I've sent the transfer"}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
      <SafeAreaView edges={["top"]} style={styles.header}>
        <View style={styles.headerRow}>
          <TouchableOpacity testID="cart-close" onPress={() => router.back()} style={styles.iconBtn}>
            <Ionicons name="close" size={22} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.title}>Your Cart</Text>
          <View style={{ width: 40 }} />
        </View>
      </SafeAreaView>

      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          testID="cart-scroll"
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: 240, gap: spacing.lg }}
          keyboardShouldPersistTaps="handled"
        >
          {items.length === 0 ? (
            <View style={styles.empty} testID="cart-empty">
              <Ionicons name="bag-handle-outline" size={40} color={colors.textMuted} />
              <Text style={styles.emptyTitle}>Your cart is empty</Text>
              <TouchableOpacity testID="cart-browse" style={styles.emptyBtn} onPress={() => { router.back(); }}>
                <Text style={styles.emptyBtnText}>Browse menu</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Items</Text>
                {items.map(i => {
                  const isCatering = i.kind === "catering";
                  const isPackage = i.kind === "weekly_package";
                  const guests = i.catering_guest_count || 1;
                  const lineTotal = i.price_cents * (isCatering ? guests : 1) * i.quantity;
                  return (
                    <View key={i.cart_item_id} style={styles.cartRow} testID={`cart-item-${i.cart_item_id}`}>
                      <Image source={{ uri: mediaUrl(i.image_url) }} style={styles.thumb} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemName} numberOfLines={2}>{i.name}</Text>
                        {isCatering ? (
                          <>
                            <Text style={styles.itemMeta}>
                              {i.tier_title ? `${i.tier_title} · ` : ""}
                              {centsToCAD(i.price_cents)} / person × {guests} guests
                            </Text>
                            {i.selection_labels?.map((s, idx) => (
                              <Text key={idx} style={styles.itemMeta} numberOfLines={1}>
                                {s.title}: {s.items.join(", ")}
                              </Text>
                            ))}
                          </>
                        ) : isPackage ? (
                          <>
                            <Text style={styles.itemMeta}>WEEKLY COMBO · Pick {i.package_pick_count} · {centsToCAD(i.price_cents)}</Text>
                            <Text style={styles.itemMeta} numberOfLines={2}>
                              {(i.package_selection_names || []).join(", ")}
                            </Text>
                          </>
                        ) : (
                          <Text style={styles.itemMeta}>{centsToCAD(i.price_cents)} each</Text>
                        )}
                        <Text style={styles.itemPrice}>{centsToCAD(lineTotal)}</Text>
                      </View>
                      <View style={styles.stepper}>
                        <TouchableOpacity testID={`cart-dec-${i.cart_item_id}`} onPress={() => setQty(i.cart_item_id, i.quantity - 1)} style={styles.stepperBtn}>
                          <Ionicons name="remove" size={16} color={colors.text} />
                        </TouchableOpacity>
                        <Text style={styles.qty}>{i.quantity}</Text>
                        <TouchableOpacity testID={`cart-inc-${i.cart_item_id}`} onPress={() => setQty(i.cart_item_id, i.quantity + 1)} style={styles.stepperBtn}>
                          <Ionicons name="add" size={16} color={colors.text} />
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </View>

              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Delivery slot</Text>
                {slots.length === 0 ? (
                  <View style={styles.noSlotBox} testID="cart-no-slots">
                    <Ionicons name="time-outline" size={20} color="#B45309" />
                    <Text style={styles.noSlotText}>
                      {"No delivery days are enabled yet. Ask the admin to open delivery days in Settings → Ordering & Delivery Schedule."}
                    </Text>
                  </View>
                ) : (
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingRight: 20 }}>
                    {slots.map(s => {
                      const active = selectedSlot?.date === s.date && selectedSlot?.window === s.window;
                      return (
                        <TouchableOpacity
                          key={`${s.date}-${s.window}`}
                          testID={`slot-${s.date}-${s.window}`}
                          onPress={() => setSelectedSlot(s)}
                          style={[styles.slot, active && styles.slotActive]}
                        >
                          <Text style={[styles.slotText, active && styles.slotTextActive]}>{s.label}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </ScrollView>
                )}
              </View>

              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Delivery address & contact</Text>
                <TextInput
                  testID="cart-recipient-name"
                  placeholder="Recipient name (who's this order for?)"
                  placeholderTextColor={colors.textMuted}
                  value={recipientName}
                  onChangeText={setRecipientName}
                  style={styles.input}
                  autoCapitalize="words"
                  autoCorrect={false}
                />
                {!user && recipientName.trim().length < 2 && (
                  <Text style={[styles.helperTxt, { color: colors.primary }]}>
                    <Ionicons name="person" size={11} color={colors.primary} /> Please add your name so our driver knows who to hand the food to.
                  </Text>
                )}
                <AddressAutocomplete
                  testID="cart-line1"
                  value={line1}
                  onChangeText={(t) => { setLine1(t); setCoords(null); }}
                  onSelect={onAddressPick}
                  placeholder="Street address (start typing…)"
                />
                {!!(user as any)?.default_address?.line1 && line1 === (user as any).default_address.line1 && (
                  <Text style={styles.helperTxt}>
                    <Ionicons name="bookmark" size={11} color={colors.primary} /> Using your saved address — edit anytime
                  </Text>
                )}
                <TextInput testID="cart-line2" placeholder="Apt / Unit (optional)"
                  placeholderTextColor={colors.textMuted} value={line2} onChangeText={setLine2} style={styles.input} />
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <TextInput testID="cart-city" placeholder="City" placeholderTextColor={colors.textMuted}
                    value={city} onChangeText={(t) => { setCity(t); setCoords(null); }} style={[styles.input, { flex: 1 }]} />
                  <TextInput testID="cart-postal" placeholder="Postal code"
                    placeholderTextColor={colors.textMuted} value={postal} onChangeText={(t) => { setPostal(t); setCoords(null); }}
                    style={[styles.input, { flex: 1 }]} autoCapitalize="characters" />
                </View>
                <TextInput
                  testID="cart-phone"
                  placeholder="Phone number (for delivery updates)"
                  placeholderTextColor={colors.textMuted}
                  value={phone}
                  onChangeText={setPhone}
                  style={styles.input}
                  keyboardType="phone-pad"
                />
                {!!user?.phone && phone === user.phone && (
                  <Text style={styles.helperTxt}>Using saved phone from your profile</Text>
                )}
                <TextInput
                  testID="cart-email"
                  placeholder="Email (for order confirmation & invoice)"
                  placeholderTextColor={colors.textMuted}
                  value={email}
                  onChangeText={setEmail}
                  style={styles.input}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                {email.trim().length > 0 && !emailValid && (
                  <Text style={[styles.helperTxt, { color: colors.primary }]}>
                    <Ionicons name="mail" size={11} color={colors.primary} /> Please enter a valid email — we send your confirmation & invoice here.
                  </Text>
                )}
                <TextInput testID="cart-instructions" placeholder="Special instructions (optional)"
                  placeholderTextColor={colors.textMuted} value={instructions} onChangeText={setInstructions}
                  style={[styles.input, { height: 60 }]} multiline />
              </View>

              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Coupon & rewards</Text>
                <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
                  <TextInput testID="cart-coupon" placeholder="Coupon code (e.g. WELCOME10)"
                    placeholderTextColor={colors.textMuted} value={couponCode} onChangeText={t => setCouponCode(t.toUpperCase())}
                    style={[styles.input, { flex: 1 }]} autoCapitalize="characters" />
                  <TouchableOpacity testID="cart-coupon-apply" style={styles.applyBtn} onPress={fetchQuote}>
                    <Text style={styles.applyBtnText}>Apply</Text>
                  </TouchableOpacity>
                </View>
                {quote?.coupon_code && (
                  <Text style={styles.couponOK}>✓ {quote.coupon_code} applied · saved {centsToCAD(quote.discount_cents)}</Text>
                )}
                {publicSettings?.loyalty_enabled !== false && !!user && user.role !== "guest" && (
                <View style={styles.pointsRow}>
                  <Text style={styles.pointsLabel}>Redeem loyalty points (avail: {user?.loyalty_points || 0})</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <TouchableOpacity testID="points-dec" onPress={() => setRedeemPoints(p => Math.max(0, p - 100))} style={styles.stepperBtn}>
                      <Ionicons name="remove" size={16} color={colors.text} />
                    </TouchableOpacity>
                    <Text style={styles.qty}>{redeemPoints}</Text>
                    <TouchableOpacity testID="points-inc" onPress={() => setRedeemPoints(p => Math.min(user?.loyalty_points || 0, p + 100))} style={styles.stepperBtn}>
                      <Ionicons name="add" size={16} color={colors.text} />
                    </TouchableOpacity>
                  </View>
                </View>
                )}
              </View>

              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Payment method</Text>
                {pmEnabled("card") && (
                  <PayOption slug="card" icon="card" title="Card (Stripe)" sub="Pay now — Visa/Mastercard, Google Pay & Apple Pay included."
                    current={paymentMethod} setCurrent={setPaymentMethod} />
                )}
                {pmEnabled("interac") && (
                  <PayOption slug="interac" icon="mail" title="Interac e-Transfer" sub={`Send to ${interacCfg?.email || "our Interac email"}`}
                    current={paymentMethod} setCurrent={setPaymentMethod} />
                )}
                {pmEnabled("paypal") && (
                  <PayOption slug="paypal" icon="logo-paypal" title="PayPal" sub="Pay with your PayPal balance or linked card."
                    current={paymentMethod} setCurrent={setPaymentMethod} />
                )}
                {pmEnabled("cod") && (
                  <PayOption slug="cod" icon="cash" title="Cash on Delivery" sub="Pay the driver at your door."
                    current={paymentMethod} setCurrent={setPaymentMethod} />
                )}

                {paymentMethod === "interac" && (
                  <View style={styles.interacHint} testID="interac-preview">
                    <Ionicons name="mail-open" size={16} color={colors.primary} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.interacHintTitle}>Interac e-Transfer to:</Text>
                      <Text style={styles.interacHintEmail}>{interacCfg?.email || "orders@curryandco.ca"}</Text>
                      {!!interacCfg?.instructions && <Text style={styles.interacHintNote}>{interacCfg.instructions}</Text>}
                    </View>
                  </View>
                )}
              </View>

              {quote && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Order summary</Text>
                  <View style={styles.summaryBox}>
                    <SumRow label="Subtotal" value={centsToCAD(quote.subtotal_cents)} />
                    <SumRow
                      label={`Delivery fee${quote.delivery_fee_tier && quote.delivery_fee_tier !== "standard" ? ` (${quote.delivery_fee_tier})` : ""}`}
                      value={quote.delivery_fee_cents === 0 ? "FREE" : centsToCAD(quote.delivery_fee_cents)}
                      color={quote.delivery_fee_cents === 0 ? colors.success : undefined}
                    />
                    {typeof quote.delivery_distance_km === "number" && (
                      <Text style={styles.feeHint} testID="cart-distance-hint">
                        ~{quote.delivery_distance_km} km from our Milton kitchen
                      </Text>
                    )}
                    {quote.discount_cents > 0 && <SumRow label="Coupon discount" value={`-${centsToCAD(quote.discount_cents)}`} color={colors.success} />}
                    {quote.points_redeemed_cents > 0 && <SumRow label="Points redeemed" value={`-${centsToCAD(quote.points_redeemed_cents)}`} color={colors.success} />}
                    {!!quote.tax_cents && quote.tax_cents > 0 && (
                      <SumRow label={`${quote.tax_label || "Tax"} (${((quote.tax_cents / Math.max(1, quote.subtotal_cents + quote.delivery_fee_cents - quote.discount_cents - quote.points_redeemed_cents)) * 100).toFixed(0)}%)`} value={centsToCAD(quote.tax_cents)} />
                    )}
                    <View style={styles.hr} />
                    <SumRow label="Total" value={centsToCAD(quote.total_cents)} bold />
                  </View>
                  <View style={styles.policyBox} testID="cart-delivery-policy">
                    <View style={styles.policyRow}>
                      <Ionicons name="time-outline" size={14} color={colors.primary} />
                      <Text style={styles.policyText}>Delivery hours: {quote.delivery_time_window || "6:00 AM – 8:00 PM"}</Text>
                    </View>
                    <View style={styles.policyRow}>
                      <Ionicons name="business-outline" size={14} color={colors.primary} />
                      <Text style={styles.policyText}>{quote.delivery_condo_policy || "Condo & apartment deliveries: please collect your food from the building gate — our drivers cannot deliver to individual unit doors."}</Text>
                    </View>
                  </View>
                </View>
              )}
            </>
          )}
        </ScrollView>

        {items.length > 0 && (
          <View style={[styles.checkoutBar, { paddingBottom: insets.bottom + 12 }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.checkoutHint}>Total</Text>
              <Text style={styles.checkoutTotal}>{centsToCAD(quote?.total_cents ?? subtotalCents)}</Text>
            </View>
            <TouchableOpacity
              testID="cart-checkout"
              disabled={!canPlace || placing}
              onPress={placeAndPay}
              style={[styles.checkoutBtn, (!canPlace || placing) && { opacity: 0.5 }]}
            >
              {placing ? <ActivityIndicator color="#fff" /> : (
                <>
                  <Text style={styles.checkoutBtnText}>
                    {paymentMethod === "cod" ? "Place order (Cash on Delivery)" : "Place order & pay"}
                  </Text>
                  <Ionicons name="arrow-forward" size={16} color="#fff" />
                </>
              )}
            </TouchableOpacity>
          </View>
        )}
      </KeyboardAvoidingView>
    </View>
  );
}

function SumRow({ label, value, color, bold }: { label: string; value: string; color?: string; bold?: boolean }) {  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 }}>
      <Text style={{ color: colors.textMuted, fontSize: 13, fontWeight: bold ? "700" : "500" }}>{label}</Text>
      <Text style={{ color: color || colors.text, fontSize: bold ? 18 : 14, fontWeight: bold ? "800" : "600" }}>{value}</Text>
    </View>
  );
}

function PayOption({ slug, icon, title, sub, current, setCurrent }: { slug: PaymentSlug; icon: any; title: string; sub: string; current: PaymentSlug; setCurrent: (s: PaymentSlug) => void }) {
  const active = current === slug;
  return (
    <TouchableOpacity
      testID={`pay-method-${slug}`}
      onPress={() => setCurrent(slug)}
      activeOpacity={0.85}
      style={[styles.payOption, active && styles.payOptionActive]}
    >
      <View style={[styles.radio, active && styles.radioActive]}>
        {active && <View style={styles.radioDot} />}
      </View>
      <Ionicons name={icon} size={22} color={active ? colors.primary : colors.text} />
      <View style={{ flex: 1 }}>
        <Text style={styles.payTitle}>{title}</Text>
        <Text style={styles.paySub}>{sub}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  header: { backgroundColor: colors.background, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: spacing.lg },
  iconBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { fontSize: 18, fontWeight: "800", color: colors.text },

  empty: { alignItems: "center", justifyContent: "center", paddingVertical: 60, gap: spacing.md },
  emptyTitle: { fontSize: 18, fontWeight: "700", color: colors.text },
  emptyBtn: { backgroundColor: colors.primary, paddingHorizontal: 24, paddingVertical: 12, borderRadius: radius.pill },
  emptyBtnText: { color: "#fff", fontWeight: "700" },

  section: { gap: spacing.sm },
  sectionTitle: { color: colors.textMuted, letterSpacing: 2, fontSize: 11, fontWeight: "800", marginBottom: 4 },

  cartRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, padding: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  thumb: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  itemName: { fontSize: 14, fontWeight: "700", color: colors.text },
  itemPrice: { color: colors.primary, fontWeight: "700", fontSize: 13, marginTop: 2 },
  stepper: { flexDirection: "row", alignItems: "center", gap: 6 },
  stepperBtn: { width: 30, height: 30, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  qty: { fontSize: 14, fontWeight: "800", color: colors.text, minWidth: 24, textAlign: "center" },

  slot: { flexShrink: 0, height: 44, paddingHorizontal: 16, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  slotActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  slotText: { color: colors.text, fontWeight: "600", fontSize: 13 },
  slotTextActive: { color: "#1a1a1a", fontWeight: "800" },
  noSlotBox: { flexDirection: "row", alignItems: "center", gap: 8, padding: spacing.md, backgroundColor: "#FEF3C7", borderRadius: radius.md, borderWidth: 1, borderColor: "#FDE68A" },
  noSlotText: { flex: 1, color: "#7C4A03", fontSize: 12, fontWeight: "600" },

  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12, color: colors.text, fontSize: 14 },
  helperTxt: { color: colors.textMuted, fontSize: 11, fontStyle: "italic" },

  itemMeta: { color: colors.textMuted, fontSize: 11, marginTop: 2 },

  applyBtn: { paddingHorizontal: 18, paddingVertical: 12, backgroundColor: colors.text, borderRadius: radius.pill },
  applyBtnText: { color: "#fff", fontWeight: "700" },
  couponOK: { color: colors.success, fontWeight: "700", fontSize: 12 },
  pointsRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  pointsLabel: { color: colors.text, fontSize: 12, flex: 1 },

  summaryBox: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  feeHint: { fontSize: 11, color: colors.textMuted, marginTop: -4, marginBottom: 2 },
  policyBox: { marginTop: spacing.sm, backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: spacing.md, gap: 8 },
  policyRow: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  policyText: { flex: 1, fontSize: 12, color: colors.text, lineHeight: 17 },
  hr: { height: 1, backgroundColor: colors.border, marginVertical: 6 },

  payOption: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    padding: spacing.md, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  payOptionActive: { borderColor: colors.primary, backgroundColor: "#FBF3EF" },
  radio: {
    width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  radioActive: { borderColor: colors.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary },
  payTitle: { fontSize: 14, fontWeight: "700", color: colors.text },
  paySub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  interacHint: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: "#FEF3C7", borderWidth: 1, borderColor: "#F9B233",
    marginTop: 6,
  },
  interacHintTitle: { fontSize: 11, fontWeight: "700", color: "#78350F", letterSpacing: 0.5 },
  interacHintEmail: { fontSize: 15, fontWeight: "800", color: "#78350F", marginTop: 2 },
  interacHintNote: { fontSize: 11, color: "#78350F", marginTop: 4, fontStyle: "italic" },
  // Interac confirmation modal
  interacModalOverlay: {
    position: "absolute", top: 0, right: 0, bottom: 0, left: 0,
    backgroundColor: "rgba(0,0,0,0.55)", alignItems: "center", justifyContent: "center", padding: spacing.lg, zIndex: 999,
  },
  interacModal: {
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm,
    borderLeftWidth: 4, borderLeftColor: "#F9B233", width: "100%", maxWidth: 420,
  },
  interacModalTitle: { fontSize: 18, fontWeight: "800", color: colors.text },
  interacModalTotal: { fontSize: 26, fontWeight: "900", color: "#166534", marginTop: 6 },
  interacModalLabel: { fontSize: 10, fontWeight: "700", color: colors.textMuted, letterSpacing: 1, marginTop: 8 },
  interacModalEmail: {
    fontSize: 16, fontWeight: "800", color: colors.text, padding: 10,
    borderRadius: 8, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border,
  },
  interacModalNote: { fontSize: 12, color: colors.textMuted, marginTop: 6, lineHeight: 18 },
  interacModalBtn: {
    marginTop: spacing.md, backgroundColor: colors.primary, paddingVertical: 12, borderRadius: radius.pill,
    alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 6,
  },
  interacModalBtnText: { color: "#fff", fontWeight: "800", fontSize: 14 },

  checkoutBar: { position: "absolute", bottom: 0, left: 0, right: 0, backgroundColor: colors.surface, padding: spacing.lg, borderTopWidth: 1, borderTopColor: colors.border, flexDirection: "row", alignItems: "center", gap: spacing.md, ...shadows.card },
  checkoutHint: { color: colors.textMuted, fontSize: 11, letterSpacing: 2, fontWeight: "800" },
  checkoutTotal: { fontSize: 22, fontWeight: "800", color: colors.text },
  checkoutBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 14, borderRadius: radius.pill, ...shadows.card },
  checkoutBtnText: { color: "#fff", fontSize: 15, fontWeight: "800" },
});
