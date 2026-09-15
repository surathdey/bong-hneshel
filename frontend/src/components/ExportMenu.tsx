/**
 * Shared "Export" button + dropdown menu for the Admin Portal.
 *
 * Three destinations:
 *   1. Download XLS      — triggers a browser download of the base64 blob
 *   2. Google Drive      — uploads to configured Drive folder, shows shareable link
 *   3. SMS               — uploads to Drive + sends SMS with link (prompts for phone)
 *
 * Configuration checks:
 *   - If Drive/Twilio isn't configured, those buttons appear disabled with a hint.
 *
 * Props:
 *   selectedCount: number of selected rows (0 = "all")
 *   isConfigured: { drive: bool, twilio: bool } — determines which buttons are enabled
 *   onExport(destination, opts) — async callback; opts includes sms_to for SMS
 *   disabled: bool — global disable (e.g. when list is empty)
 */
import React, { useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, Modal, TextInput, ActivityIndicator, Platform,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { colors, spacing, radius, shadows } from "@/src/theme";

export type ExportDest = "download" | "email" | "sms" | "drive";
export type ExportOpts = { sms_to?: string; sms_message?: string; email_to?: string };
export type ExportConfig = { email: boolean; twilio: boolean; drive: boolean; emailRecipient?: string };

type ExportResult =
  | { kind: "download"; filename: string; count: number; b64?: string }
  | { kind: "email"; filename: string; count: number; recipient: string; download_link: string; message_id?: string }
  | { kind: "sms"; filename: string; count: number; download_link: string; sms_status: string }
  | { kind: "drive"; filename: string; count: number; web_view_link: string };

/** Trigger a browser download of a base64 XLSX blob. Web-only. */
export function downloadB64(b64: string, filename: string, contentType: string) {
  if (Platform.OS !== "web" || typeof window === "undefined") return;
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const blob = new Blob([bytes], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

export default function ExportMenu({
  selectedCount, totalCount, isConfigured, onExport, disabled, testID,
}: {
  selectedCount: number;
  totalCount: number;
  isConfigured: ExportConfig;
  onExport: (dest: ExportDest, opts?: ExportOpts) => Promise<ExportResult | null>;
  disabled?: boolean;
  testID?: string;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [smsOpen, setSmsOpen] = useState(false);
  const [smsPhone, setSmsPhone] = useState("");
  const [smsMessage, setSmsMessage] = useState("");
  const [loading, setLoading] = useState<ExportDest | null>(null);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string>("");

  const count = selectedCount || totalCount;
  const btnLabel = selectedCount > 0 ? `Export ${selectedCount} selected` : `Export all (${totalCount})`;

  const run = async (dest: ExportDest, opts?: ExportOpts) => {
    setLoading(dest);
    setError("");
    setResult(null);
    try {
      const r = await onExport(dest, opts);
      if (r) setResult(r);
    } catch (e: any) {
      setError(e?.message || "Export failed");
    } finally {
      setLoading(null);
    }
  };

  const closeAll = () => {
    setMenuOpen(false); setSmsOpen(false); setResult(null); setError("");
    setSmsPhone(""); setSmsMessage("");
  };

  return (
    <View>
      <TouchableOpacity
        testID={testID || "export-btn"}
        onPress={() => setMenuOpen(true)}
        disabled={disabled || totalCount === 0}
        style={[styles.exportBtn, (disabled || totalCount === 0) && styles.exportBtnDisabled]}
      >
        <Ionicons name="download-outline" size={16} color="#fff" />
        <Text style={styles.exportBtnText}>{btnLabel}</Text>
        <Ionicons name="chevron-down" size={14} color="#fff" />
      </TouchableOpacity>

      {/* Menu / result modal */}
      <Modal visible={menuOpen} transparent animationType="fade" onRequestClose={closeAll}>
        <TouchableOpacity style={styles.backdrop} activeOpacity={1} onPress={closeAll}>
          <TouchableOpacity activeOpacity={1} style={styles.sheet} onPress={() => {}}>
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>Export {count} {count === 1 ? "row" : "rows"}</Text>
              <TouchableOpacity onPress={closeAll} testID="export-close">
                <Ionicons name="close" size={22} color={colors.textMuted} />
              </TouchableOpacity>
            </View>

            {result ? (
              <View style={{ gap: spacing.md }}>
                <View style={styles.resultBanner}>
                  <Ionicons name="checkmark-circle" size={22} color={colors.success} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultTitle}>
                      {result.kind === "download" && "File downloaded"}
                      {result.kind === "email" && `Emailed to ${result.recipient}`}
                      {result.kind === "sms" && `SMS sent (${result.sms_status})`}
                      {result.kind === "drive" && "Uploaded to Google Drive"}
                    </Text>
                    <Text style={styles.resultFile}>{result.filename} · {result.count} rows</Text>
                  </View>
                </View>
                {(result.kind === "email" || result.kind === "sms") && (
                  <TouchableOpacity
                    onPress={() => {
                      const url = result.kind === "email" ? result.download_link : result.download_link;
                      if (typeof window !== "undefined") window.open(url, "_blank");
                    }}
                    style={styles.linkBtn}
                    testID="export-open-link"
                  >
                    <Ionicons name="download-outline" size={16} color={colors.primary} />
                    <Text style={styles.linkBtnText}>Open download link</Text>
                  </TouchableOpacity>
                )}
                {result.kind === "drive" && (
                  <TouchableOpacity
                    onPress={() => {
                      if (typeof window !== "undefined") window.open(result.web_view_link, "_blank");
                    }}
                    style={styles.linkBtn}
                    testID="export-open-link"
                  >
                    <Ionicons name="open-outline" size={16} color={colors.primary} />
                    <Text style={styles.linkBtnText}>Open in Google Drive</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={closeAll} style={styles.doneBtn} testID="export-done">
                  <Text style={styles.doneBtnText}>Done</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View style={{ gap: spacing.sm }}>
                {/* Download */}
                <TouchableOpacity
                  testID="export-download"
                  disabled={loading != null}
                  onPress={async () => {
                    const r = await run("download");
                    if (r && r.kind === "download" && r.b64) {
                      downloadB64(r.b64, r.filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
                    }
                  }}
                  style={styles.optRow}
                >
                  <View style={[styles.optIcon, { backgroundColor: "#0f766e22" }]}>
                    {loading === "download"
                      ? <ActivityIndicator size="small" color="#0f766e" />
                      : <Ionicons name="download-outline" size={20} color="#0f766e" />}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.optTitle}>Download XLSX</Text>
                    <Text style={styles.optSub}>Instant download to this device</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                </TouchableOpacity>

                {/* Email */}
                <TouchableOpacity
                  testID="export-email"
                  disabled={loading != null || !isConfigured.email}
                  onPress={() => run("email")}
                  style={[styles.optRow, !isConfigured.email && styles.optRowDisabled]}
                >
                  <View style={[styles.optIcon, { backgroundColor: "#B14F3622" }]}>
                    {loading === "email"
                      ? <ActivityIndicator size="small" color={colors.primary} />
                      : <Ionicons name="mail-outline" size={20} color={colors.primary} />}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.optTitle}>
                      Email me the report
                      {!isConfigured.email && <Text style={styles.dim}> (no recipient set)</Text>}
                    </Text>
                    <Text style={styles.optSub}>
                      {isConfigured.email
                        ? `Sends to ${isConfigured.emailRecipient || "your inbox"} · 48h secure link`
                        : "Add a recipient in Settings → Integrations · Exports"}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                </TouchableOpacity>

                {/* SMS */}
                <TouchableOpacity
                  testID="export-sms"
                  disabled={loading != null || !isConfigured.twilio}
                  onPress={() => setSmsOpen(true)}
                  style={[styles.optRow, !isConfigured.twilio && styles.optRowDisabled]}
                >
                  <View style={[styles.optIcon, { backgroundColor: "#7c3aed22" }]}>
                    <Ionicons name="chatbubble-ellipses-outline" size={20} color="#7c3aed" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.optTitle}>
                      Send SMS with download link
                      {!isConfigured.twilio && <Text style={styles.dim}> (Twilio not configured)</Text>}
                    </Text>
                    <Text style={styles.optSub}>
                      {isConfigured.twilio
                        ? "Texts a 48h secure link — no Drive needed"
                        : "Add Twilio credentials in Settings → Integrations"}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                </TouchableOpacity>

                {/* Drive (advanced / optional) */}
                <TouchableOpacity
                  testID="export-drive"
                  disabled={loading != null || !isConfigured.drive}
                  onPress={() => run("drive")}
                  style={[styles.optRow, !isConfigured.drive && styles.optRowDisabled]}
                >
                  <View style={[styles.optIcon, { backgroundColor: "#4285F422" }]}>
                    {loading === "drive"
                      ? <ActivityIndicator size="small" color="#4285F4" />
                      : <Ionicons name="cloud-upload-outline" size={20} color="#4285F4" />}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.optTitle}>
                      Upload to Google Drive
                      {!isConfigured.drive && <Text style={styles.dim}> (not configured)</Text>}
                    </Text>
                    <Text style={styles.optSub}>
                      {isConfigured.drive
                        ? "Only works with a Workspace Shared Drive (not personal Gmail folders)"
                        : "Requires Google Workspace + service account setup"}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                </TouchableOpacity>

                {error ? (
                  <View style={styles.errorBanner}>
                    <Ionicons name="alert-circle" size={16} color={colors.danger} />
                    <Text style={styles.errorText}>{error}</Text>
                  </View>
                ) : null}
              </View>
            )}
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>

      {/* SMS phone-number modal */}
      <Modal visible={smsOpen} transparent animationType="slide" onRequestClose={() => setSmsOpen(false)}>
        <View style={styles.backdrop}>
          <View style={[styles.sheet, { maxWidth: 460 }]}>
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>Send Drive link via SMS</Text>
              <TouchableOpacity onPress={() => setSmsOpen(false)}>
                <Ionicons name="close" size={22} color={colors.textMuted} />
              </TouchableOpacity>
            </View>
            <Text style={styles.label}>Phone number (E.164 format)</Text>
            <TextInput
              testID="sms-phone-input"
              value={smsPhone}
              onChangeText={setSmsPhone}
              placeholder="+14165551234"
              autoCapitalize="none"
              keyboardType="phone-pad"
              style={styles.input}
            />
            <Text style={styles.label}>Message (optional)</Text>
            <TextInput
              testID="sms-message-input"
              value={smsMessage}
              onChangeText={setSmsMessage}
              placeholder="Leave blank to auto-generate"
              multiline
              style={[styles.input, { height: 60 }]}
            />
            <TouchableOpacity
              testID="sms-send-btn"
              disabled={!smsPhone.trim() || loading === "sms"}
              onPress={async () => {
                setSmsOpen(false);
                const r = await run("sms", { sms_to: smsPhone.trim(), sms_message: smsMessage.trim() || undefined });
                if (r) setResult(r);
              }}
              style={[styles.doneBtn, (!smsPhone.trim() || loading === "sms") && { opacity: 0.6 }]}
            >
              {loading === "sms" ? <ActivityIndicator color="#fff" /> :
                <>
                  <Ionicons name="send-outline" size={16} color="#fff" />
                  <Text style={styles.doneBtnText}>Upload & send SMS</Text>
                </>}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  exportBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill },
  exportBtnDisabled: { opacity: 0.5 },
  exportBtnText: { color: "#fff", fontWeight: "800", fontSize: 13 },

  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", alignItems: "center", justifyContent: "center", padding: spacing.md },
  sheet: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, width: "100%", maxWidth: 520, ...shadows.soft },
  sheetHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sheetTitle: { fontSize: 18, fontWeight: "800", color: colors.text },

  optRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  optRowDisabled: { opacity: 0.55 },
  optIcon: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  optTitle: { color: colors.text, fontWeight: "800", fontSize: 14 },
  optSub: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  dim: { color: colors.textMuted, fontWeight: "500" },

  resultBanner: { flexDirection: "row", alignItems: "center", gap: 10, padding: 12, backgroundColor: "#ecfdf5", borderRadius: radius.md },
  resultTitle: { color: colors.text, fontWeight: "800" },
  resultFile: { color: colors.textMuted, fontSize: 12 },

  errorBanner: { flexDirection: "row", alignItems: "center", gap: 6, padding: 10, backgroundColor: "#fef2f2", borderRadius: radius.md },
  errorText: { color: colors.danger, fontSize: 13, flex: 1 },

  linkBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.primary },
  linkBtnText: { color: colors.primary, fontWeight: "700" },

  doneBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: radius.pill, backgroundColor: colors.primary },
  doneBtnText: { color: "#fff", fontWeight: "800", fontSize: 14 },

  label: { color: colors.textMuted, fontSize: 12, fontWeight: "700", letterSpacing: 1, marginTop: 6 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 10, color: colors.text, backgroundColor: colors.surfaceAlt, fontSize: 14 },
});
