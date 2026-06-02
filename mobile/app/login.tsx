import { useEffect, useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as storage from "../utils/secureStorage";
import { router, useLocalSearchParams } from "expo-router";
import { loginWithPIN, requestOTP } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import PinPad from "../components/app/PinPad";

function getJWTStage(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    return typeof payload.stage === "string" ? payload.stage : null;
  } catch {
    return null;
  }
}

type Phase = "phone" | "pin";

export default function LoginScreen() {
  // prefilled_phone comes from the welcome-back card — skip phone entry entirely.
  const { prefilled_phone } = useLocalSearchParams<{ prefilled_phone?: string }>();

  const [phase,         setPhase]         = useState<Phase>(prefilled_phone ? "pin" : "phone");
  const [phone,         setPhone]         = useState(prefilled_phone ?? "");
  const [loading,       setLoading]       = useState(false);
  const [forgotLoading, setForgotLoading] = useState(false);
  const [error,         setError]         = useState("");
  const [resetKey,      setResetKey]      = useState(0);  // bumped on wrong PIN

  // If a fully active session exists, skip phone entry and go to PIN.
  // If biometric is also enabled, attempt it immediately — on success the
  // user lands in the app without touching a PIN key.
  useEffect(() => {
    (async () => {
      const [token, storedPhone] = await Promise.all([
        storage.getItem("access"),
        storage.getItem("phone"),
      ]);
      if (!(token && storedPhone && getJWTStage(token) === "active")) return;

      setPhone(storedPhone);

      // Try biometric first if the user enabled it.
      const AsyncStorage = (await import("@react-native-async-storage/async-storage")).default;
      const bioEnabled   = (await AsyncStorage.getItem("biometric_enabled")) === "true";

      if (bioEnabled) {
        try {
          const LocalAuth = await import("expo-local-authentication");
          const hasHardware = await LocalAuth.hasHardwareAsync();
          const isEnrolled  = await LocalAuth.isEnrolledAsync();

          if (hasHardware && isEnrolled) {
            const result = await LocalAuth.authenticateAsync({
              promptMessage:         "Log in to WEPL",
              cancelLabel:           "Use PIN instead",
              disableDeviceFallback: false,
            });

            if (result.success) {
              // Biometric passed — go straight into the app.
              router.replace("/(drawer)/profile");
              return;
            }
            // Cancelled or failed — fall through to PIN screen.
          }
        } catch {
          // Biometric unavailable — fall through to PIN screen silently.
        }
      }

      setPhase("pin");
    })();
  }, []);

  // ── Phase 1: phone entry ─────────────────────────────────────────────────

  async function handleContinue() {
    const trimmed = phone.trim();
    if (!trimmed) { setError("Enter your phone number"); return; }
    setError("");
    setPhase("pin");
  }

  // ── Phase 2: PIN entry via numpad ────────────────────────────────────────

  async function handlePinComplete(pin: string) {
    setError("");
    setLoading(true);
    try {
      const data = await loginWithPIN(phone.trim(), pin);
      await storage.setItem("access",  data.access);
      await storage.setItem("refresh", data.refresh);
      await storage.setItem("phone",   phone.trim());
      // Fetch profile: store name for welcome-back screen AND check KYC status
      // to decide where to land (communities for verified, profile for unverified).
      // Fetch profile: store name AND check KYC so the drawer layout
      // knows which tabs to show before we arrive.
      try {
        const { getProfile } = await import("../api/auth");
        const profile = await getProfile();
        if (profile?.name) await storage.setItem("name", profile.name);
      } catch {}
      // Navigate to the drawer root — the tab layout picks the first
      // visible tab (Communities for verified, Profile for unverified).
      router.replace("/(drawer)" as any);
    } catch (e: any) {
      const msg = e?.response?.data?.error || "Wrong PIN. Try again.";
      setError(msg);
      setResetKey(k => k + 1);   // clears the dots via PinPad's useEffect
    } finally {
      setLoading(false);
    }
  }

  async function handleForgot() {
    const target = phone.trim();
    if (!target) {
      setPhase("phone");
      setError("Enter your phone number first, then tap Forgot PIN.");
      return;
    }
    setError("");
    setForgotLoading(true);
    try {
      // requestOTP no longer returns is_registered (removed for security).
      // The OTP verify response tells the app what to do via next_step.
      await requestOTP(target);
      router.push({ pathname: "/otp", params: { phone_number: target } });
    } catch (e: any) {
      setError(e?.response?.data?.error || "Failed to send reset code. Try again.");
    } finally {
      setForgotLoading(false);
    }
  }

  // ── Render: PIN numpad ───────────────────────────────────────────────────

  if (phase === "pin") {
    return (
      <PinPad
        icon="lock-closed"
        title="Verify your PIN"
        subtitle="to unlock"
        onComplete={handlePinComplete}
        onForgot={handleForgot}
        forgotLoading={forgotLoading}
        error={error}
        loading={loading}
        resetKey={resetKey}
        onBack={() => {
          // Allow switching phone number
          setPhase("phone");
          setError("");
        }}
      />
    );
  }

  // ── Render: phone entry ──────────────────────────────────────────────────

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={s.container}>

          <TouchableOpacity style={s.back} onPress={() => router.back()}>
            <Text style={s.backText}>← Back</Text>
          </TouchableOpacity>

          <View style={s.header}>
            <Text style={s.title}>Welcome back</Text>
            <Text style={s.subtitle}>Enter your phone number to continue.</Text>
          </View>

          <Text style={s.label}>Phone Number</Text>
          <TextInput
            placeholder="0712 345 678"
            placeholderTextColor={COLORS.textMuted}
            value={phone}
            onChangeText={(t) => { setPhone(t); setError(""); }}
            style={s.input}
            keyboardType="phone-pad"
            autoFocus
            returnKeyType="done"
            onSubmitEditing={handleContinue}
          />

          {error ? <Text style={s.error}>{error}</Text> : null}

          <TouchableOpacity
            style={[s.button, loading && s.buttonDisabled]}
            onPress={handleContinue}
            disabled={loading}
          >
            {loading
              ? <ActivityIndicator color={COLORS.white} />
              : <Text style={s.buttonText}>Continue</Text>}
          </TouchableOpacity>

          <View style={s.divider}>
            <View style={s.dividerLine} />
            <Text style={s.dividerText}>or</Text>
            <View style={s.dividerLine} />
          </View>

          <TouchableOpacity
            style={s.registerBtn}
            onPress={() => router.replace({ pathname: "/", params: { register: "1" } })}
          >
            <Text style={s.registerBtnText}>Create a new account</Text>
          </TouchableOpacity>

        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:  { flex: 1, backgroundColor: COLORS.background },
  flex:  { flex: 1 },

  container: {
    flex: 1,
    padding: 28,
  },

  back: { marginTop: 16, marginBottom: 36 },
  backText: { color: COLORS.primary, fontSize: FONTS.md, fontWeight: "600" },

  header: { marginBottom: 32 },
  title: {
    fontSize: FONTS.xxl,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: FONTS.md,
    color: COLORS.textSecondary,
    lineHeight: 22,
  },

  label: {
    fontSize: FONTS.sm,
    fontWeight: "600",
    color: COLORS.textSecondary,
    marginBottom: 8,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  input: {
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 15,
    fontSize: FONTS.md,
    color: COLORS.text,
    backgroundColor: COLORS.white,
    marginBottom: 6,
  },

  error: {
    color: COLORS.error,
    fontSize: FONTS.sm,
    marginBottom: 12,
    marginTop: 4,
  },

  button: {
    backgroundColor: COLORS.primary,
    padding: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
    marginTop: 20,
  },
  buttonDisabled: { opacity: 0.7 },
  buttonText: {
    color: COLORS.white,
    fontWeight: "700",
    fontSize: FONTS.md,
  },

  divider: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 24,
    gap: 10,
  },
  dividerLine:  { flex: 1, height: 1, backgroundColor: COLORS.border },
  dividerText:  { fontSize: FONTS.sm, color: COLORS.textMuted },

  registerBtn: {
    borderWidth: 1.5,
    borderColor: COLORS.border,
    padding: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
    backgroundColor: COLORS.white,
  },
  registerBtnText: {
    color: COLORS.text,
    fontWeight: "600",
    fontSize: FONTS.md,
  },
});
