import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API_BASE_URL } from "../../constants/config";
import PinPad from "../../components/app/PinPad";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Switch,
  Alert,
  ActivityIndicator,
  Platform,
  Modal,
  Pressable,
  TextInput,
  KeyboardAvoidingView,
  Linking,
  Animated,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";
import Constants from "expo-constants";
import * as storage from "../../utils/secureStorage";
import API from "../../api/client";
import { getProfile, updateProfile } from "../../api/auth";
import { getNotifPrefs, updateNotifPrefs } from "../../api/notifications";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";

// ─── Storage keys ────────────────────────────────────────────────────────────
const NOTIF_KEY     = "notif_prefs_v1";
const BIOMETRIC_KEY = "biometric_enabled";

type NotifPrefs = {
  push:          boolean;
  payments:      boolean;
  contributions: boolean;
  reminders:     boolean;
  communities:   boolean;
  advances:      boolean;
};

const DEFAULT_NOTIF: NotifPrefs = {
  push:          true,
  payments:      true,
  contributions: true,
  reminders:     true,
  communities:   true,
  advances:      true,
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function SectionHeader({ title }: { title: string }) {
  return <Text style={s.sectionHeader}>{title}</Text>;
}

type RowProps = {
  icon:       string;
  iconColor?: string;
  iconBg?:    string;
  label:      string;
  value?:     string;
  onPress?:   () => void;
  rightEl?:   React.ReactNode;
  showArrow?: boolean;
  danger?:    boolean;
};

function Row({
  icon, iconColor, iconBg, label, value,
  onPress, rightEl, showArrow = true, danger,
}: RowProps) {
  const ic  = iconColor ?? (danger ? COLORS.error : COLORS.primary);
  const ibg = iconBg    ?? ic + "18";
  return (
    <TouchableOpacity
      style={s.row}
      onPress={onPress}
      disabled={!onPress && !rightEl}
      activeOpacity={0.7}
    >
      <View style={[s.rowIcon, { backgroundColor: ibg }]}>
        <Ionicons name={icon as any} size={17} color={ic} />
      </View>
      <Text style={[s.rowLabel, danger && { color: COLORS.error }]}>{label}</Text>
      <View style={s.rowRight}>
        {rightEl ?? (
          <>
            {value ? <Text style={[s.rowValue, danger && { color: COLORS.error }]}>{value}</Text> : null}
            {onPress && showArrow && (
              <Ionicons name="chevron-forward" size={15} color={COLORS.textMuted} style={{ marginLeft: 4 }} />
            )}
          </>
        )}
      </View>
    </TouchableOpacity>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <View style={s.card}>{children}</View>;
}

function Divider() {
  return <View style={s.divider} />;
}

function ToggleRow({
  icon, iconColor, label, value, onChange,
}: {
  icon: string; iconColor?: string; label: string;
  value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <Row
      icon={icon}
      iconColor={iconColor}
      label={label}
      showArrow={false}
      rightEl={
        <Switch
          value={value}
          onValueChange={onChange}
          trackColor={{ false: COLORS.border, true: COLORS.primary + "80" }}
          thumbColor={value ? COLORS.primary : COLORS.textMuted}
          ios_backgroundColor={COLORS.border}
        />
      }
    />
  );
}

// ─── Main screen ─────────────────────────────────────────────────────────────

type Profile = {
  name:         string;
  bio:          string;
  phone_number: string;
  kyc_status:   "approved" | "pending" | "rejected" | "not_submitted";
};

export default function SettingsScreen() {
  const [profile,        setProfile]        = useState<Profile>({ name: "", bio: "", phone_number: "", kyc_status: "not_submitted" });
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [notif,          setNotif]          = useState<NotifPrefs>(DEFAULT_NOTIF);
  const [biometric,      setBiometric]      = useState(false);

  // PIN confirmation overlay for biometric toggle
  const [pinOverlay,      setPinOverlay]      = useState(false);
  const [pinError,        setPinError]        = useState("");
  const [pinResetKey,     setPinResetKey]     = useState(0);
  const [pinLoading,      setPinLoading]      = useState(false);
  const pendingBioVal     = useRef<boolean | null>(null);   // value awaiting PIN confirm

  // Raw axios — bypasses the 401 interceptor so a wrong PIN doesn't log the user out
  const rawAxios = axios.create({ baseURL: API_BASE_URL });

  // Edit modal
  const [editVisible, setEditVisible] = useState(false);
  const [editName,    setEditName]    = useState("");
  const [editBio,     setEditBio]     = useState("");
  const [saving,      setSaving]      = useState(false);

  // Success banner — shown when returning from change-pin with pinChanged=1
  const { pinChanged } = useLocalSearchParams<{ pinChanged?: string }>();
  const bannerAnim  = useRef(new Animated.Value(0)).current;
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    if (pinChanged !== "1") return;
    setShowBanner(true);
    // Fade in
    Animated.timing(bannerAnim, {
      toValue: 1, duration: 300, useNativeDriver: true,
    }).start();
    // Auto-dismiss after 3.5 seconds
    const t = setTimeout(() => {
      Animated.timing(bannerAnim, {
        toValue: 0, duration: 400, useNativeDriver: true,
      }).start(() => setShowBanner(false));
    }, 3500);
    return () => clearTimeout(t);
  }, [pinChanged]);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      (async () => {
        try {
          const [p, serverPrefs, rawBio] = await Promise.all([
            getProfile().catch(() => null),
            getNotifPrefs().catch(() => null),       // load from backend
            AsyncStorage.getItem(BIOMETRIC_KEY),
          ]);
          if (!active) return;
          if (p) setProfile(p);
          if (serverPrefs) {
            // Map server field names → local state shape
            setNotif({
              push:          serverPrefs.push_enabled,
              payments:      serverPrefs.payments,
              contributions: serverPrefs.contributions,
              reminders:     serverPrefs.reminders,
              communities:   serverPrefs.communities,
              advances:      serverPrefs.advances,
            });
          }
          setBiometric(rawBio === "true");
        } finally {
          if (active) setLoadingProfile(false);
        }
      })();
      return () => { active = false; };
    }, [])
  );

  async function saveNotifPref(key: keyof NotifPrefs, val: boolean) {
    // Optimistic local update
    const updated = { ...notif, [key]: val };
    setNotif(updated);

    // Persist to server (map local key → server field name)
    const serverKey = key === "push" ? "push_enabled" : key;
    try {
      await updateNotifPrefs({ [serverKey]: val } as any);
    } catch {
      // Revert on failure
      setNotif(notif);
    }
  }

  /** Step 1 — user taps toggle: open PIN overlay first */
  function saveBiometric(val: boolean) {
    pendingBioVal.current = val;
    setPinError("");
    setPinResetKey(k => k + 1);
    setPinOverlay(true);
  }

  /** Step 2 — PIN verified: proceed with enable/disable */
  async function confirmBiometricWithPin(pin: string) {
    const phone = profile.phone_number || (await storage.getItem("phone")) || "";
    if (!phone) {
      setPinError("Phone number not found. Please sign out and sign in again.");
      setPinResetKey(k => k + 1);
      return;
    }

    setPinLoading(true);
    try {
      await rawAxios.post("users/pin/login/", { phone_number: phone, pin });
    } catch (e: any) {
      setPinLoading(false);
      const status = e?.response?.status;
      if (status === 429) {
        setPinError("Account temporarily locked after too many attempts. Try again in 30 minutes.");
      } else if (status === 401) {
        setPinError("Incorrect PIN. Please try again.");
      } else {
        setPinError(e?.response?.data?.error || "Could not verify PIN. Try again.");
      }
      setPinResetKey(k => k + 1);
      return;
    }
    setPinLoading(false);

    // PIN correct — close overlay and proceed
    setPinOverlay(false);
    const val = pendingBioVal.current!;

    if (val) {
      // Enabling: check hardware + run live biometric test
      const LocalAuth = await import("expo-local-authentication");
      const hasHardware = await LocalAuth.hasHardwareAsync();
      const isEnrolled  = await LocalAuth.isEnrolledAsync();

      if (!hasHardware || !isEnrolled) {
        Alert.alert(
          "Biometric not available",
          !hasHardware
            ? "This device does not have biometric hardware."
            : "No biometrics enrolled. Add a fingerprint or face in your device Settings first.",
        );
        return;
      }

      const result = await LocalAuth.authenticateAsync({
        promptMessage:         "Confirm biometric login",
        cancelLabel:           "Cancel",
        disableDeviceFallback: false,
      });
      if (!result.success) return;   // user cancelled — don't enable
    }

    setBiometric(val);
    await AsyncStorage.setItem(BIOMETRIC_KEY, String(val));

    Alert.alert(
      val ? "Biometric login enabled" : "Biometric login disabled",
      val
        ? "You can now log in using your fingerprint or face."
        : "You'll use your PIN to log in from now on.",
    );
  }

  function openEditProfile() {
    setEditName(profile.name);
    setEditBio(profile.bio);
    setEditVisible(true);
  }

  async function handleSaveProfile() {
    if (!editName.trim()) {
      Alert.alert("Name required", "Please enter your display name.");
      return;
    }
    setSaving(true);
    try {
      const updated = await updateProfile({ name: editName.trim(), bio: editBio.trim() });
      setProfile(p => ({ ...p, name: updated.name ?? editName.trim(), bio: updated.bio ?? editBio.trim() }));
      if (editName.trim()) await storage.setItem("name", editName.trim());
      setEditVisible(false);
    } catch {
      Alert.alert("Error", "Could not save profile. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  function handleResetPIN() {
    // New flow: verify current PIN → new PIN → confirm → OTP → done.
    // All steps handled by the change-pin screen.
    router.push("/change-pin");
  }

  async function handleClearCache() {
    Alert.alert(
      "Clear Cache",
      "This clears cached preferences and local data. Your account data is not affected.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text:    "Clear",
          style:   "destructive",
          onPress: async () => {
            const allKeys  = await AsyncStorage.getAllKeys();
            const safeKeys = allKeys.filter(k => !["access","refresh","phone","name"].includes(k));
            if (safeKeys.length) await AsyncStorage.multiRemove(safeKeys);
            setNotif(DEFAULT_NOTIF);
            setBiometric(false);
            Alert.alert("Done", "Cache cleared successfully.");
          },
        },
      ]
    );
  }

  function handleDeleteAccount() {
    Alert.alert(
      "Delete your account?",
      "Your personal data will be permanently erased. Financial records are retained for legal compliance. This cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text:  "Delete Account",
          style: "destructive",
          onPress: () =>
            Alert.alert(
              "Are you absolutely sure?",
              "Type DELETE in the next step to confirm, or tap Cancel.",
              [
                { text: "Cancel", style: "cancel" },
                {
                  text:    "Yes, delete my account",
                  style:   "destructive",
                  onPress: async () => {
                    try {
                      await API.delete("users/account/");
                      await storage.multiRemove(["access", "refresh", "phone", "name"]);
                      await AsyncStorage.removeItem(BIOMETRIC_KEY);
                      router.replace("/");
                    } catch (e: any) {
                      const msg = e?.response?.data?.error;
                      Alert.alert(
                        "Cannot delete account",
                        msg || "Please resolve any outstanding advances or community ownership before deleting.",
                      );
                    }
                  },
                },
              ]
            ),
        },
      ]
    );
  }

  function handleSignOut() {
    Alert.alert("Sign out", "Are you sure you want to sign out?", [
      { text: "Cancel", style: "cancel" },
      {
        text:    "Sign out",
        style:   "destructive",
        onPress: async () => {
          await storage.multiRemove(["access", "refresh", "phone", "name"]);
          await AsyncStorage.removeItem(BIOMETRIC_KEY);
          // Navigate to the welcome/landing screen and replace the full stack
          // so the user cannot press Back to re-enter the app.
          router.replace("/login");
        },
      },
    ]);
  }

  const version  = Constants.expoConfig?.version ?? "1.0.0";
  const kycLabel = {
    approved:      "Verified ✓",
    pending:       "Under Review",
    rejected:      "Action Required",
    not_submitted: "Not Submitted",
  }[profile.kyc_status] ?? "Not Submitted";

  const kycColor = {
    approved:      COLORS.success,
    pending:       COLORS.warning,
    rejected:      COLORS.error,
    not_submitted: COLORS.textMuted,
  }[profile.kyc_status] ?? COLORS.textMuted;

  if (loadingProfile) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Settings" variant="light" leading="back" onBack={() => router.replace("/(drawer)/profile")} />
        <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
          <ActivityIndicator color={COLORS.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader title="Settings" variant="light" leading="back" onBack={() => router.replace("/(drawer)/profile")} />

      {/* PIN-changed success banner */}
      {showBanner && (
        <Animated.View style={[s.successBanner, { opacity: bannerAnim }]}>
          <Ionicons name="checkmark-circle" size={18} color="#166534" />
          <Text style={s.successBannerText}>PIN changed successfully</Text>
        </Animated.View>
      )}

      <ScrollView contentContainerStyle={s.body} showsVerticalScrollIndicator={false}>

        {/* ── Account ─────────────────────────────────────── */}
        <SectionHeader title="Account" />
        <Card>
          <Row
            icon="person-circle-outline"
            label="Display Name"
            value={profile.name || "Tap to set"}
            onPress={openEditProfile}
          />
          <Divider />
          <Row
            icon="call-outline"
            label="Phone Number"
            value={profile.phone_number}
            showArrow={false}
          />
          <Divider />
          <Row
            icon="shield-checkmark-outline"
            iconColor={kycColor}
            iconBg={kycColor + "18"}
            label="Identity (KYC)"
            value={kycLabel}
            onPress={
              profile.kyc_status === "approved"   ? undefined :
              profile.kyc_status === "pending"     ? () => router.push("/kyc-status") :
              /* not_submitted | rejected */          () => router.push("/kyc")
            }
            showArrow={profile.kyc_status !== "approved"}
          />
        </Card>

        {/* ── Security ─────────────────────────────────────── */}
        <SectionHeader title="Security" />
        <Card>
          <Row
            icon="key-outline"
            label="Change PIN"
            onPress={handleResetPIN}
          />
          <Divider />
          <ToggleRow
            icon="finger-print-outline"
            label="Biometric Login"
            value={biometric}
            onChange={saveBiometric}
          />
        </Card>

        {/* ── Notifications ────────────────────────────────── */}
        <SectionHeader title="Notifications" />
        <Card>
          <ToggleRow
            icon="notifications-outline"
            label="Push Notifications"
            value={notif.push}
            onChange={v => saveNotifPref("push", v)}
          />
          {notif.push && (
            <>
              <Divider />
              <View style={s.subSection}>
                <Text style={s.subSectionLabel}>Notify me about</Text>
              </View>
              <ToggleRow
                icon="card-outline"
                iconColor={COLORS.accent}
                label="Payments & M-Pesa"
                value={notif.payments}
                onChange={v => saveNotifPref("payments", v)}
              />
              <Divider />
              <ToggleRow
                icon="wallet-outline"
                label="Contributions"
                value={notif.contributions}
                onChange={v => saveNotifPref("contributions", v)}
              />
              <Divider />
              <ToggleRow
                icon="alarm-outline"
                label="Reminders"
                value={notif.reminders}
                onChange={v => saveNotifPref("reminders", v)}
              />
              <Divider />
              <ToggleRow
                icon="people-outline"
                label="Community Activity"
                value={notif.communities}
                onChange={v => saveNotifPref("communities", v)}
              />
              <Divider />
              <ToggleRow
                icon="trending-up-outline"
                label="Advances & Repayments"
                value={notif.advances}
                onChange={v => saveNotifPref("advances", v)}
              />
            </>
          )}
        </Card>

        {/* ── Preferences ──────────────────────────────────── */}
        <SectionHeader title="Preferences" />
        <Card>
          <Row icon="language-outline"      label="Language"  value="English" showArrow={false} />
          <Divider />
          <Row icon="cash-outline"          label="Currency"  value="KES (Kenyan Shilling)" showArrow={false} />
          <Divider />
          <Row icon="color-palette-outline" label="Theme"     value="Light" showArrow={false} />
        </Card>

        {/* ── Privacy & Data ───────────────────────────────── */}
        <SectionHeader title="Privacy & Data" />
        <Card>
          <Row
            icon="download-outline"
            label="Export My Data"
            onPress={() => Linking.openURL("mailto:support@wepl.app?subject=Data%20Export%20Request")}
          />
          <Divider />
          <Row
            icon="trash-bin-outline"
            label="Clear Cache"
            onPress={handleClearCache}
          />
          <Divider />
          <Row
            icon="document-text-outline"
            label="Privacy Policy"
            onPress={() => Linking.openURL("https://wepl.app/privacy")}
          />
          <Divider />
          <Row
            icon="reader-outline"
            label="Terms of Service"
            onPress={() => Linking.openURL("https://wepl.app/terms")}
          />
        </Card>

        {/* ── About ────────────────────────────────────────── */}
        <SectionHeader title="About" />
        <Card>
          <Row
            icon="information-circle-outline"
            label="App Version"
            value={`v${version}`}
            showArrow={false}
          />
          <Divider />
          <Row
            icon="help-circle-outline"
            label="Help & Support"
            onPress={() => Linking.openURL("mailto:support@wepl.app")}
          />
          <Divider />
          <Row
            icon="star-outline"
            iconColor={COLORS.accent}
            label="Rate WEPL"
            onPress={() =>
              Alert.alert("Rate WEPL", "App Store rating coming soon. Thank you for using WEPL!")
            }
          />
        </Card>

        {/* ── Danger Zone ──────────────────────────────────── */}
        <SectionHeader title="Danger Zone" />
        <Card>
          <Row
            icon="log-out-outline"
            label="Sign out"
            danger
            onPress={handleSignOut}
            showArrow={false}
          />
          <Divider />
          <Row
            icon="close-circle-outline"
            label="Delete Account"
            danger
            onPress={handleDeleteAccount}
            showArrow={false}
          />
        </Card>

        <View style={{ height: 40 }} />
      </ScrollView>

      {/* ── Edit Profile Modal ───────────────────────────── */}
      <Modal
        visible={editVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setEditVisible(false)}
      >
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === "ios" ? "padding" : "height"}
        >
          <Pressable style={s.backdrop} onPress={() => setEditVisible(false)}>
            <Pressable style={s.sheet} onStartShouldSetResponder={() => true}>
              <View style={s.handle} />
              <Text style={s.sheetTitle}>Edit Profile</Text>

              <Text style={s.fieldLabel}>Display Name</Text>
              <TextInput
                value={editName}
                onChangeText={setEditName}
                placeholder="Your name"
                placeholderTextColor={COLORS.textMuted}
                style={s.input}
                autoFocus
              />

              <Text style={s.fieldLabel}>Bio</Text>
              <TextInput
                value={editBio}
                onChangeText={setEditBio}
                placeholder="Tell others about yourself..."
                placeholderTextColor={COLORS.textMuted}
                style={[s.input, s.textarea]}
                multiline
              />

              <TouchableOpacity
                style={[s.saveBtn, saving && { opacity: 0.6 }]}
                onPress={handleSaveProfile}
                disabled={saving}
              >
                {saving
                  ? <ActivityIndicator color={COLORS.white} size="small" />
                  : <Text style={s.saveBtnText}>Save Changes</Text>
                }
              </TouchableOpacity>
            </Pressable>
          </Pressable>
        </KeyboardAvoidingView>
      </Modal>

      {/* PIN confirmation overlay for biometric toggle */}
      <Modal
        visible={pinOverlay}
        animationType="slide"
        presentationStyle="fullScreen"
        onRequestClose={() => {
          setPinOverlay(false);
          pendingBioVal.current = null;
        }}
      >
        <PinPad
          key={`bio-pin-${pinResetKey}`}
          icon="finger-print"
          title="Confirm your PIN"
          subtitle={
            pendingBioVal.current
              ? "Enter your PIN to enable biometric login"
              : "Enter your PIN to disable biometric login"
          }
          onComplete={confirmBiometricWithPin}
          error={pinError}
          loading={pinLoading}
          resetKey={pinResetKey}
          onBack={() => {
            setPinOverlay(false);
            pendingBioVal.current = null;
            setPinError("");
          }}
        />
      </Modal>
    </SafeAreaView>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },

  successBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "#DCFCE7",
    borderLeftWidth: 4,
    borderLeftColor: "#16A34A",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  successBannerText: {
    fontSize: FONTS.sm,
    fontWeight: "600",
    color: "#166534",
    flex: 1,
  },
  body: { paddingHorizontal: 16, paddingTop: 8, gap: 4 },

  sectionHeader: {
    fontSize: FONTS.xs,
    fontWeight: "600",
    color: COLORS.textMuted,
    marginTop: 16,
    marginBottom: 6,
    paddingHorizontal: 4,
  },

  card: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    overflow: "hidden",
  },

  divider: {
    height: 1,
    backgroundColor: COLORS.divider,
    marginLeft: 52,
  },

  subSection: {
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 4,
  },
  subSectionLabel: {
    fontSize: FONTS.xs,
    color: COLORS.textMuted,
    fontWeight: "600",
  },

  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  rowIcon: {
    width: 32,
    height: 32,
    borderRadius: RADIUS.md,
    justifyContent: "center",
    alignItems: "center",
    marginRight: 12,
  },
  rowLabel: {
    flex: 1,
    fontSize: FONTS.md,
    color: COLORS.text,
    fontWeight: "500",
  },
  rowRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  rowValue: {
    fontSize: FONTS.sm,
    color: COLORS.textSecondary,
    maxWidth: 160,
  },

  // Edit modal
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    paddingBottom: Platform.OS === "ios" ? 34 : 20,
  },
  handle: {
    width: 40, height: 4,
    backgroundColor: COLORS.border,
    borderRadius: RADIUS.full,
    alignSelf: "center",
    marginBottom: 16,
  },
  sheetTitle: {
    fontSize: FONTS.lg,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 18,
  },
  fieldLabel: {
    fontSize: FONTS.sm,
    color: COLORS.textSecondary,
    fontWeight: "600",
    marginBottom: 6,
    marginTop: 4,
  },
  input: {
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 12,
    fontSize: FONTS.md,
    color: COLORS.text,
    backgroundColor: COLORS.background,
    marginBottom: 12,
  },
  textarea: {
    height: 90,
    textAlignVertical: "top",
  },
  saveBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: RADIUS.md,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 4,
  },
  saveBtnText: {
    color: COLORS.white,
    fontWeight: "700",
    fontSize: FONTS.md,
  },
});
