/**
 * Google Places autocomplete for the Bag / checkout screen.
 * Backend proxy: GET /api/places/autocomplete + /api/places/details
 * (Keeps the API key on the server & lets us country-restrict to Canada.)
 *
 * On selection → structured address (line1, city, province, postal_code, lat, lng) is emitted.
 */
import React, { useEffect, useRef, useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, ActivityIndicator, StyleSheet, Platform,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { colors, radius, shadows } from "@/src/theme";

type Prediction = {
  place_id: string;
  description: string;
  main_text: string;
  secondary_text: string;
};

export type StructuredAddress = {
  line1: string;
  city: string;
  province: string;
  postal_code: string;
  country?: string;
  lat?: number | null;
  lng?: number | null;
  formatted?: string;
};

type Props = {
  value: string;
  onChangeText: (t: string) => void;
  onSelect: (addr: StructuredAddress) => void;
  placeholder?: string;
  testID?: string;
  style?: any;
};

// Generate a fresh session token per typing session so Google bills a single "session"
// (autocomplete + one details call) rather than each keystroke separately.
let _sessionCounter = 0;
function newSessionToken(): string {
  _sessionCounter += 1;
  return `${Date.now().toString(36)}-${_sessionCounter}-${Math.random().toString(36).slice(2, 8)}`;
}

export function AddressAutocomplete({
  value, onChangeText, onSelect, placeholder = "Street address", testID, style,
}: Props) {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const sessionRef = useRef<string>(newSessionToken());
  const debounceRef = useRef<any>(null);
  const lastQueryRef = useRef<string>("");
  // Only search when the text change came from the USER typing — never from a
  // programmatic value update (e.g. the parent injecting the picked address,
  // which previously re-opened the dropdown and blocked selection).
  const userEditedRef = useRef(false);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!focused) return;
    if (!userEditedRef.current) return;
    const q = (value || "").trim();
    if (q.length < 3) { setPredictions([]); setOpen(false); return; }
    if (q === lastQueryRef.current) return;
    debounceRef.current = setTimeout(async () => {
      userEditedRef.current = false;
      lastQueryRef.current = q;
      setLoading(true);
      const r = await api.get<{ predictions: Prediction[] }>(`/places/autocomplete?q=${encodeURIComponent(q)}&session_token=${sessionRef.current}`);
      setLoading(false);
      if (r.ok && r.data?.predictions) {
        setPredictions(r.data.predictions);
        setOpen(r.data.predictions.length > 0);
      } else {
        setPredictions([]); setOpen(false);
      }
    }, 260);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [value, focused]);

  // Wraps the parent onChangeText for the TextInput so we can flag user typing.
  const handleUserType = (t: string) => {
    userEditedRef.current = true;
    onChangeText(t);
  };

  const pick = async (p: Prediction) => {
    // Fill the input with a nice human string right away for instant feedback.
    userEditedRef.current = false;
    onChangeText(p.description);
    setOpen(false);
    setPredictions([]);
    setFocused(false);
    lastQueryRef.current = p.description;
    setLoading(true);
    const r = await api.get<{ ok: boolean; address: StructuredAddress }>(`/places/details?place_id=${encodeURIComponent(p.place_id)}&session_token=${sessionRef.current}`);
    setLoading(false);
    // New session token for the next autocomplete round.
    sessionRef.current = newSessionToken();
    if (r.ok && r.data?.ok && r.data.address) {
      onSelect(r.data.address);
    } else {
      // Fallback — parse a naive "line1, city, province" split
      const parts = p.description.split(",").map(s => s.trim());
      onSelect({
        line1: parts[0] || p.description,
        city: parts[1] || "Toronto",
        province: parts[2] || "ON",
        postal_code: "",
      });
    }
  };

  return (
    <View style={[{ position: "relative", zIndex: 20 }, style]}>
      <View style={styles.inputWrap}>
        <Ionicons name="location-outline" size={16} color={colors.textMuted} style={{ marginLeft: 10 }} />
        <TextInput
          testID={testID}
          value={value}
          onChangeText={handleUserType}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            // Small delay so a tap on a suggestion registers first.
            setTimeout(() => { setFocused(false); setOpen(false); }, 160);
          }}
          placeholder={placeholder}
          placeholderTextColor={colors.textMuted}
          style={styles.input}
          autoCorrect={false}
          autoCapitalize="words"
        />
        {loading && <ActivityIndicator size="small" color={colors.textMuted} style={{ marginRight: 10 }} />}
      </View>
      {open && predictions.length > 0 && (
        <View style={styles.dropdown} testID={testID ? `${testID}-dropdown` : undefined}>
          {predictions.map((p) => (
            <TouchableOpacity
              key={p.place_id}
              onPress={() => pick(p)}
              activeOpacity={0.7}
              style={styles.suggestion}
              testID={testID ? `${testID}-suggestion-${p.place_id}` : undefined}
            >
              <Ionicons name="location" size={13} color={colors.primary} style={{ marginTop: 3 }} />
              <View style={{ flex: 1 }}>
                <Text style={styles.mainTxt} numberOfLines={1}>{p.main_text || p.description}</Text>
                {!!p.secondary_text && <Text style={styles.secTxt} numberOfLines={1}>{p.secondary_text}</Text>}
              </View>
            </TouchableOpacity>
          ))}
          <View style={styles.attribution}>
            <Text style={styles.attrTxt}>powered by Google</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1,
    paddingHorizontal: 10,
    paddingVertical: Platform.OS === "ios" ? 12 : 10,
    color: colors.text,
    fontSize: 14,
  },
  dropdown: {
    position: "absolute",
    top: "100%",
    left: 0,
    right: 0,
    marginTop: 4,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.pop,
    zIndex: 100,
    overflow: "hidden",
  },
  suggestion: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  mainTxt: { fontSize: 13, fontWeight: "700", color: colors.text },
  secTxt: { fontSize: 11, color: colors.textMuted, marginTop: 1 },
  attribution: {
    padding: 6,
    alignItems: "flex-end",
    backgroundColor: colors.surfaceAlt,
  },
  attrTxt: { fontSize: 9, color: colors.textMuted, fontStyle: "italic" },
});
