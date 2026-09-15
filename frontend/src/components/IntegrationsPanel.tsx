/**
 * Admin Settings — Integrations section.
 *
 * Renders forms for Google Drive service account + Twilio SMS credentials.
 * Secrets are write-only (server never returns them) — inputs show
 * "•••••• configured" placeholders when saved, and typing new text replaces.
 */
import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator, Alert,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { adminApi } from "@/src/adminApi";
import { colors, spacing, radius, shadows } from "@/src/theme";

type State = {
  crypto_ready: boolean;
  email: {
    configured: boolean;
    recipient: string;
    last_test_ok: boolean | null;
    last_test_at: string | null;
  };
  google_drive: {
    configured: boolean;
    folder_id: string;
    user_email: string;
    client_email: string;
    last_test_ok: boolean | null;
    last_test_at: string | null;
  };
  twilio: {
    configured: boolean;
    account_sid: string;
    from_number: string;
    last_test_ok: boolean | null;
    last_test_at: string | null;
  };
};

export default function IntegrationsPanel() {
  const [state, setState] = useState<State | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingEmail, setSavingEmail] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);
  const [emailTestResult, setEmailTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [savingDrive, setSavingDrive] = useState(false);
  const [savingTwilio, setSavingTwilio] = useState(false);
  const [testingDrive, setTestingDrive] = useState(false);
  const [testingTwilio, setTestingTwilio] = useState(false);
  const [driveTestResult, setDriveTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [twilioTestResult, setTwilioTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  // Email form
  const [emailRecipient, setEmailRecipient] = useState("");
  const [emailTestOverride, setEmailTestOverride] = useState("");

  // Drive form fields
  const [saJson, setSaJson] = useState("");
  const [folderId, setFolderId] = useState("");
  const [userEmail, setUserEmail] = useState("");

  // Twilio form fields
  const [sid, setSid] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [fromNumber, setFromNumber] = useState("");

  // Test-Twilio phone
  const [twilioTestTo, setTwilioTestTo] = useState("");

  const load = async () => {
    setLoading(true);
    const r = await adminApi.get<State>("/admin/integrations");
    if (r.ok) {
      setState(r.data);
      setEmailRecipient(r.data.email?.recipient || "");
      setFolderId(r.data.google_drive.folder_id || "");
      setUserEmail(r.data.google_drive.user_email || "");
      setSid(r.data.twilio.account_sid || "");
      setFromNumber(r.data.twilio.from_number || "");
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const saveEmail = async () => {
    if (!emailRecipient.trim()) {
      Alert.alert("Missing", "Enter the email address that should receive exports.");
      return;
    }
    setSavingEmail(true);
    const r = await adminApi.put<any>("/admin/integrations/email", { recipient: emailRecipient.trim() });
    setSavingEmail(false);
    if (r.ok) { await load(); Alert.alert("Saved", "Recipient email saved."); }
    else Alert.alert("Save failed", r.error);
  };

  const testEmail = async () => {
    setTestingEmail(true); setEmailTestResult(null);
    const body: any = {};
    if (emailTestOverride.trim()) body.to = emailTestOverride.trim();
    const r = await adminApi.post<any>("/admin/integrations/email/test", body);
    setTestingEmail(false);
    if (r.ok) setEmailTestResult({ ok: true, msg: `✓ Test email sent to ${r.data?.to}` });
    else setEmailTestResult({ ok: false, msg: r.error });
    await load();
  };

  const saveDrive = async () => {
    if (!folderId.trim() || !userEmail.trim()) {
      Alert.alert("Missing fields", "Folder ID and user email are required.");
      return;
    }
    setSavingDrive(true);
    const body: any = { folder_id: folderId.trim(), user_email: userEmail.trim() };
    if (saJson.trim()) body.service_account_json = saJson.trim();
    const r = await adminApi.put<any>("/admin/integrations/google-drive", body);
    setSavingDrive(false);
    if (r.ok) { setSaJson(""); await load(); Alert.alert("Saved", "Google Drive credentials saved."); }
    else Alert.alert("Save failed", r.error);
  };

  const testDrive = async () => {
    setTestingDrive(true); setDriveTestResult(null);
    const r = await adminApi.post<any>("/admin/integrations/google-drive/test", {});
    setTestingDrive(false);
    if (r.ok) setDriveTestResult({ ok: true, msg: `✓ Connected — folder: ${r.data?.folder?.name || "OK"}` });
    else setDriveTestResult({ ok: false, msg: r.error });
    await load();
  };

  const saveTwilio = async () => {
    if (!sid.trim() || !fromNumber.trim()) {
      Alert.alert("Missing fields", "Account SID and From number are required.");
      return;
    }
    setSavingTwilio(true);
    const body: any = { account_sid: sid.trim(), from_number: fromNumber.trim() };
    if (authToken.trim()) body.auth_token = authToken.trim();
    const r = await adminApi.put<any>("/admin/integrations/twilio", body);
    setSavingTwilio(false);
    if (r.ok) { setAuthToken(""); await load(); Alert.alert("Saved", "Twilio credentials saved."); }
    else Alert.alert("Save failed", r.error);
  };

  const testTwilio = async () => {
    if (!twilioTestTo.trim()) {
      Alert.alert("Phone required", "Enter your phone number in E.164 format (e.g. +14165551234) to receive the test SMS.");
      return;
    }
    setTestingTwilio(true); setTwilioTestResult(null);
    const r = await adminApi.post<any>("/admin/integrations/twilio/test", { to_number: twilioTestTo.trim() });
    setTestingTwilio(false);
    if (r.ok) setTwilioTestResult({ ok: true, msg: `✓ Test SMS sent — status: ${r.data?.status || "queued"}` });
    else setTwilioTestResult({ ok: false, msg: r.error });
    await load();
  };

  if (loading || !state) return <ActivityIndicator color={colors.primary} />;

  return (
    <View style={{ gap: spacing.md }}>
      {!state.crypto_ready && (
        <View style={styles.errorBanner}>
          <Ionicons name="alert-circle" size={18} color={colors.danger} />
          <Text style={styles.errorText}>
            Encryption key missing. Add INTEGRATIONS_FERNET_KEY to backend/.env and redeploy.
          </Text>
        </View>
      )}

      {/* --------------- Email card (PRIMARY) --------------- */}
      <View style={[styles.card, { borderLeftWidth: 4, borderLeftColor: colors.primary }]}>
        <View style={styles.headRow}>
          <View style={[styles.brandDot, { backgroundColor: colors.primary }]}>
            <Ionicons name="mail-outline" size={16} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Email exports · Recommended</Text>
            <Text style={styles.desc}>Sends XLS reports to your inbox with a secure 48-hour download link. No setup fees.</Text>
          </View>
          <StatusBadge configured={state.email.configured && !!state.email.recipient} lastTestOk={state.email.last_test_ok} />
        </View>

        <Text style={styles.label}>Recipient email</Text>
        <Text style={styles.helper}>Every &quot;Email me the report&quot; export goes here. Change any time.</Text>
        <TextInput
          testID="email-recipient"
          value={emailRecipient} onChangeText={setEmailRecipient}
          placeholder="you@yourcompany.com"
          autoCapitalize="none" keyboardType="email-address"
          style={styles.input}
        />

        <View style={styles.btnRow}>
          <TouchableOpacity testID="email-save" onPress={saveEmail} disabled={savingEmail}
            style={[styles.btnPrimary, savingEmail && { opacity: 0.6 }]}>
            {savingEmail ? <ActivityIndicator color="#fff" size="small" /> :
              <><Ionicons name="save-outline" size={14} color="#fff" /><Text style={styles.btnPrimaryText}>Save</Text></>}
          </TouchableOpacity>
        </View>

        {state.email.configured && (
          <View style={{ marginTop: spacing.sm, gap: 4 }}>
            <Text style={styles.label}>Send a test email to</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
              <TextInput
                testID="email-test-to" value={emailTestOverride} onChangeText={setEmailTestOverride}
                placeholder={emailRecipient || "leave blank to use configured"} autoCapitalize="none"
                keyboardType="email-address"
                style={[styles.input, { flex: 1 }]}
              />
              <TouchableOpacity testID="email-test" onPress={testEmail} disabled={testingEmail}
                style={[styles.btnOutline, testingEmail && { opacity: 0.5 }]}>
                {testingEmail ? <ActivityIndicator color={colors.primary} size="small" /> :
                  <><Ionicons name="send-outline" size={14} color={colors.primary} /><Text style={styles.btnOutlineText}>Send test</Text></>}
              </TouchableOpacity>
            </View>
          </View>
        )}

        {emailTestResult && (
          <View style={[styles.testBanner, emailTestResult.ok ? styles.testOk : styles.testFail]}>
            <Ionicons name={emailTestResult.ok ? "checkmark-circle" : "alert-circle"} size={16}
              color={emailTestResult.ok ? colors.success : colors.danger} />
            <Text style={styles.testText}>{emailTestResult.msg}</Text>
          </View>
        )}
      </View>

      {/* --------------- Google Drive card --------------- */}
      <View style={[styles.card, { borderLeftWidth: 4, borderLeftColor: "#4285F4" }]}>
        <View style={styles.headRow}>
          <View style={[styles.brandDot, { backgroundColor: "#4285F4" }]}>
            <Ionicons name="cloud-upload-outline" size={16} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Google Drive · Optional / Advanced</Text>
            <Text style={styles.desc}>Only works if the folder lives in a Google Workspace Shared Drive. Personal Gmail folders will fail with storageQuotaExceeded — use Email exports instead.</Text>
          </View>
          <StatusBadge configured={state.google_drive.configured} lastTestOk={state.google_drive.last_test_ok} />
        </View>

        <Text style={styles.label}>Service account JSON</Text>
        <Text style={styles.helper}>
          {state.google_drive.configured
            ? `Currently configured — service account: ${state.google_drive.client_email || "hidden"}. Paste new JSON to replace, or leave blank.`
            : "Paste the entire JSON key file downloaded from Google Cloud Console → Service Accounts → Keys."}
        </Text>
        <TextInput
          testID="drive-sa-json"
          value={saJson}
          onChangeText={setSaJson}
          placeholder={state.google_drive.configured ? '{ …existing key hidden… }' : '{"type":"service_account", ...}'}
          multiline
          autoCapitalize="none"
          autoCorrect={false}
          style={[styles.input, { minHeight: 100, fontFamily: "monospace" as any, fontSize: 11 }]}
          placeholderTextColor={colors.textMuted}
        />

        <Text style={styles.label}>Drive folder ID</Text>
        <Text style={styles.helper}>
          The share URL is like https://drive.google.com/drive/folders/<Text style={{ fontWeight: "800" }}>FOLDER_ID</Text> —
          copy just the ID. IMPORTANT: share this folder with the service-account email as Editor.
        </Text>
        <TextInput
          testID="drive-folder-id"
          value={folderId} onChangeText={setFolderId}
          placeholder="1AbCd2XyZ..."
          autoCapitalize="none"
          style={styles.input}
        />

        <Text style={styles.label}>Owner email (share files back to)</Text>
        <TextInput
          testID="drive-user-email"
          value={userEmail} onChangeText={setUserEmail}
          placeholder="you@yourcompany.com"
          autoCapitalize="none"
          keyboardType="email-address"
          style={styles.input}
        />

        <View style={styles.btnRow}>
          <TouchableOpacity testID="drive-save" onPress={saveDrive} disabled={savingDrive} style={[styles.btnPrimary, savingDrive && { opacity: 0.6 }]}>
            {savingDrive ? <ActivityIndicator color="#fff" size="small" /> :
              <><Ionicons name="save-outline" size={14} color="#fff" /><Text style={styles.btnPrimaryText}>Save</Text></>}
          </TouchableOpacity>
          <TouchableOpacity testID="drive-test" onPress={testDrive} disabled={testingDrive || !state.google_drive.configured}
            style={[styles.btnOutline, (testingDrive || !state.google_drive.configured) && { opacity: 0.5 }]}>
            {testingDrive ? <ActivityIndicator color={colors.primary} size="small" /> :
              <><Ionicons name="checkmark-circle-outline" size={14} color={colors.primary} /><Text style={styles.btnOutlineText}>Test connection</Text></>}
          </TouchableOpacity>
        </View>

        {driveTestResult && (
          <View style={[styles.testBanner, driveTestResult.ok ? styles.testOk : styles.testFail]}>
            <Ionicons name={driveTestResult.ok ? "checkmark-circle" : "alert-circle"} size={16}
              color={driveTestResult.ok ? colors.success : colors.danger} />
            <Text style={styles.testText}>{driveTestResult.msg}</Text>
          </View>
        )}
      </View>

      {/* --------------- Twilio card --------------- */}
      <View style={[styles.card, { borderLeftWidth: 4, borderLeftColor: "#F22F46" }]}>
        <View style={styles.headRow}>
          <View style={[styles.brandDot, { backgroundColor: "#F22F46" }]}>
            <Ionicons name="chatbubble-ellipses-outline" size={16} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Twilio SMS</Text>
            <Text style={styles.desc}>Used to text Drive share links to phone numbers.</Text>
          </View>
          <StatusBadge configured={state.twilio.configured} lastTestOk={state.twilio.last_test_ok} />
        </View>

        <Text style={styles.label}>Account SID</Text>
        <Text style={styles.helper}>Find in Twilio Console → dashboard. Starts with &quot;AC&quot;.</Text>
        <TextInput
          testID="twilio-sid" value={sid} onChangeText={setSid}
          placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
          autoCapitalize="none" style={styles.input}
        />

        <Text style={styles.label}>Auth token</Text>
        <Text style={styles.helper}>
          {state.twilio.configured ? "Currently configured. Enter a new token to replace, or leave blank." : "Auth token (kept secret). Reveal in Twilio Console."}
        </Text>
        <TextInput
          testID="twilio-token" value={authToken} onChangeText={setAuthToken}
          placeholder={state.twilio.configured ? "•••• configured ••••" : "your auth token"}
          autoCapitalize="none" secureTextEntry
          style={styles.input}
        />

        <Text style={styles.label}>From number (E.164)</Text>
        <Text style={styles.helper}>Twilio phone number that will send the SMS. E.g. +14165551234.</Text>
        <TextInput
          testID="twilio-from" value={fromNumber} onChangeText={setFromNumber}
          placeholder="+14165551234"
          autoCapitalize="none" keyboardType="phone-pad" style={styles.input}
        />

        <View style={styles.btnRow}>
          <TouchableOpacity testID="twilio-save" onPress={saveTwilio} disabled={savingTwilio} style={[styles.btnPrimary, savingTwilio && { opacity: 0.6 }]}>
            {savingTwilio ? <ActivityIndicator color="#fff" size="small" /> :
              <><Ionicons name="save-outline" size={14} color="#fff" /><Text style={styles.btnPrimaryText}>Save</Text></>}
          </TouchableOpacity>
        </View>

        {state.twilio.configured && (
          <View style={{ marginTop: spacing.sm, gap: 4 }}>
            <Text style={styles.label}>Test SMS to</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
              <TextInput
                testID="twilio-test-to" value={twilioTestTo} onChangeText={setTwilioTestTo}
                placeholder="+14165551234" autoCapitalize="none" keyboardType="phone-pad"
                style={[styles.input, { flex: 1 }]}
              />
              <TouchableOpacity testID="twilio-test" onPress={testTwilio} disabled={testingTwilio}
                style={[styles.btnOutline, testingTwilio && { opacity: 0.5 }]}>
                {testingTwilio ? <ActivityIndicator color={colors.primary} size="small" /> :
                  <><Ionicons name="send-outline" size={14} color={colors.primary} /><Text style={styles.btnOutlineText}>Send test</Text></>}
              </TouchableOpacity>
            </View>
          </View>
        )}

        {twilioTestResult && (
          <View style={[styles.testBanner, twilioTestResult.ok ? styles.testOk : styles.testFail]}>
            <Ionicons name={twilioTestResult.ok ? "checkmark-circle" : "alert-circle"} size={16}
              color={twilioTestResult.ok ? colors.success : colors.danger} />
            <Text style={styles.testText}>{twilioTestResult.msg}</Text>
          </View>
        )}
      </View>
    </View>
  );
}

function StatusBadge({ configured, lastTestOk }: { configured: boolean; lastTestOk: boolean | null }) {
  if (!configured) {
    return (
      <View style={[styles.badge, { backgroundColor: colors.surfaceAlt, borderColor: colors.border }]}>
        <Text style={[styles.badgeText, { color: colors.textMuted }]}>Not configured</Text>
      </View>
    );
  }
  if (lastTestOk === true) {
    return (
      <View style={[styles.badge, { backgroundColor: "#DCFCE7", borderColor: "#22c55e" }]}>
        <Ionicons name="checkmark-circle" size={12} color={colors.success} />
        <Text style={[styles.badgeText, { color: colors.success }]}>Connected</Text>
      </View>
    );
  }
  if (lastTestOk === false) {
    return (
      <View style={[styles.badge, { backgroundColor: "#FEE2E2", borderColor: colors.danger }]}>
        <Ionicons name="alert-circle" size={12} color={colors.danger} />
        <Text style={[styles.badgeText, { color: colors.danger }]}>Test failed</Text>
      </View>
    );
  }
  return (
    <View style={[styles.badge, { backgroundColor: "#FEF3C7", borderColor: "#F59E0B" }]}>
      <Text style={[styles.badgeText, { color: "#B45309" }]}>Saved — not tested</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.sm, ...shadows.soft },
  headRow: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 4 },
  brandDot: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  title: { color: colors.text, fontWeight: "800", fontSize: 14 },
  desc: { color: colors.textMuted, fontSize: 11, marginTop: 2 },

  label: { color: colors.textMuted, letterSpacing: 2, fontSize: 10, fontWeight: "800", marginTop: 6 },
  helper: { color: colors.textMuted, fontSize: 11, lineHeight: 15 },
  input: { backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 10, paddingVertical: 8, color: colors.text, fontSize: 13 },

  btnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  btnPrimary: { flexDirection: "row", gap: 6, alignItems: "center", backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.pill },
  btnPrimaryText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  btnOutline: { flexDirection: "row", gap: 6, alignItems: "center", borderWidth: 1, borderColor: colors.primary, paddingHorizontal: 12, paddingVertical: 10, borderRadius: radius.pill },
  btnOutlineText: { color: colors.primary, fontWeight: "800", fontSize: 13 },

  badge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1 },
  badgeText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },

  testBanner: { flexDirection: "row", alignItems: "center", gap: 6, padding: 10, borderRadius: radius.md, marginTop: spacing.sm },
  testOk: { backgroundColor: "#ecfdf5", borderWidth: 1, borderColor: "#a7f3d0" },
  testFail: { backgroundColor: "#fef2f2", borderWidth: 1, borderColor: "#fecaca" },
  testText: { color: colors.text, fontSize: 12, flex: 1, flexWrap: "wrap" },

  errorBanner: { flexDirection: "row", alignItems: "center", gap: 6, padding: 10, backgroundColor: "#fef2f2", borderRadius: radius.md, borderWidth: 1, borderColor: "#fecaca" },
  errorText: { color: colors.danger, fontSize: 12, flex: 1 },
});
