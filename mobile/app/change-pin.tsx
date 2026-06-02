/**
 * Change PIN — self-contained 4-step flow.
 *
 *  Step 1  Enter current PIN   → verify via backend (raw axios, bypasses interceptor)
 *  Step 2  Enter new PIN
 *  Step 3  Confirm new PIN
 *  Step 4  OTP verification    → inline (no navigation), calls resetPIN directly
 *          ↓ success
 *          Navigate to Settings ✅
 *
 * Keeping all 4 steps in one screen means the new PIN stays in a ref and
 * never touches navigation params, storage, or URL query strings.
 */
import { useEffect, useRef, useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import axios from "axios";
import { router } from "expo-router";
import * as storage from "../utils/secureStorage";
import { requestOTP, verifyOTP, resetPIN } from "../api/auth";
import { API_BASE_URL } from "../constants/config";
import PinPad from "../components/app/PinPad";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

const RESEND_COOLDOWN = 60;

/** Plain axios — no interceptors — so a 401 (wrong PIN) is not mistaken for
 *  an expired token and does NOT trigger logout. */
const rawAxios = axios.create({ baseURL: API_BASE_URL });

async function verifyCurrentPIN(phone: string, pin: string): Promise<void> {
  await rawAxios.post("users/pin/login/", { phone_number: phone, pin });
}

type Step = "current" | "new" | "confirm" | "otp";

export default function ChangePINScreen() {
  const [step,     setStep]     = useState<Step>("current");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");
  const [resetKey, setResetKey] = useState(0);

  // New PIN stored in a ref — never leaves this component.
  const newPinRef   = useRef("");
  const phoneRef    = useRef("");

  // OTP step state
  const [otp,           setOTP]           = useState("");
  const [countdown,     setCountdown]     = useState(RESEND_COOLDOWN);
  const [resending,     setResending]     = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  function startCountdown() {
    if (timerRef.current) clearInterval(timerRef.current);
    setCountdown(RESEND_COOLDOWN);
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(timerRef.current!); return 0; }
        return prev - 1;
      });
    }, 1000);
  }

  // ── Step 1: verify current PIN ───────────────────────────────────────────

  async function handleCurrentPIN(pin: string) {
    setError("");
    setLoading(true);
    try {
      const phone = await storage.getItem("phone") ?? "";
      if (!phone) throw new Error("Phone number not found. Please sign out and sign in again.");
      phoneRef.current = phone;

      await verifyCurrentPIN(phone, pin);

      setLoading(false);
      setStep("new");
    } catch (e: any) {
      setLoading(false);
      const status = e?.response?.status;
      if (status === 429) {
        setError("Account temporarily locked after too many attempts. Try again in 30 minutes.");
      } else if (status === 401) {
        setError("Incorrect PIN. Please try again.");
      } else {
        setError(e?.response?.data?.error || e?.message || "Could not verify your PIN. Try again.");
      }
      setResetKey(k => k + 1);
    }
  }

  // ── Step 2: capture new PIN ──────────────────────────────────────────────

  function handleNewPIN(pin: string) {
    newPinRef.current = pin;
    setError("");
    setStep("confirm");
  }

  // ── Step 3: confirm + send OTP ───────────────────────────────────────────

  async function handleConfirmPIN(pin: string) {
    if (pin !== newPinRef.current) {
      setError("PINs don't match. Please try again.");
      setResetKey(k => k + 1);
      setTimeout(() => {
        newPinRef.current = "";
        setStep("new");
        setError("");
      }, 1400);
      return;
    }

    setError("");
    setLoading(true);
    try {
      await requestOTP(phoneRef.current);
      setLoading(false);
      setOTP("");
      setError("");
      setResendSuccess(false);
      startCountdown();
      setStep("otp");
    } catch (e: any) {
      setLoading(false);
      setError(e?.response?.data?.error || "Could not send verification code. Try again.");
      setResetKey(k => k + 1);
    }
  }

  // ── Step 4: OTP verify + resetPIN ────────────────────────────────────────

  async function handleVerifyOTP() {
    if (otp.length < 6) { setError("Enter the 6-digit code we sent you."); return; }
    setError("");
    setLoading(true);
    try {
      // Verify OTP — this returns an otp_recovery token.
      const data = await verifyOTP(phoneRef.current, otp);
      await storage.setItem("access",  data.access);
      await storage.setItem("refresh", data.refresh);

      // Use the otp_recovery token to set the new PIN.
      await resetPIN(newPinRef.current);

      // Issue a fresh active session token by re-reading what resetPIN returned.
      // resetPIN already stores the new active token via the calling code below.
    } catch (e: any) {
      setLoading(false);
      setError(e?.response?.data?.error || "Verification failed. Check the code and try again.");
      return;
    }

    // Re-login with the new PIN to get a fresh active-stage token.
    try {
      const { loginWithPIN } = await import("../api/auth");
      const loginData = await rawAxios.post("users/pin/login/", {
        phone_number: phoneRef.current,
        pin: newPinRef.current,
      });
      await storage.setItem("access",  loginData.data.access);
      await storage.setItem("refresh", loginData.data.refresh);
    } catch {
      // Non-critical — user still has the otp_recovery token session; they can
      // log in again. Don't block navigation.
    }

    newPinRef.current = "";
    setLoading(false);
    router.replace({ pathname: "/(drawer)/settings", params: { pinChanged: "1" } });
  }

  async function handleResendOTP() {
    if (countdown > 0 || resending) return;
    setResending(true);
    setError("");
    setResendSuccess(false);
    setOTP("");
    try {
      await requestOTP(phoneRef.current);
      setResendSuccess(true);
      startCountdown();
    } catch (e: any) {
      setError(e?.response?.data?.error || "Failed to resend code. Try again.");
    } finally {
      setResending(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  if (step === "otp") {
    return (
      <SafeAreaView style={ots.safe}>
        <KeyboardAvoidingView
          style={ots.flex}
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <View style={ots.container}>
            <TouchableOpacity style={ots.back} onPress={() => { setStep("confirm"); setError(""); }}>
              <Text style={ots.backText}>← Back</Text>
            </TouchableOpacity>

            <View style={ots.header}>
              <Text style={ots.title}>Verify change</Text>
              <Text style={ots.subtitle}>Enter the code sent to</Text>
              <Text style={ots.phone}>{phoneRef.current}</Text>
            </View>

            <Text style={ots.label}>One-Time Password</Text>
            <TextInput
              placeholder="• • • • • •"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="numeric"
              value={otp}
              onChangeText={(t) => { setOTP(t); setError(""); setResendSuccess(false); }}
              style={[ots.input, ots.otpInput]}
              maxLength={6}
              autoFocus
              editable={!loading}
            />

            {error
              ? <Text style={ots.error}>{error}</Text>
              : resendSuccess
              ? <Text style={ots.success}>New code sent to {phoneRef.current}</Text>
              : null
            }

            <TouchableOpacity
              style={[ots.btn, (loading || otp.length < 6) && ots.btnDisabled]}
              onPress={handleVerifyOTP}
              disabled={loading || otp.length < 6}
            >
              {loading
                ? <ActivityIndicator color={COLORS.white} />
                : <Text style={ots.btnText}>Confirm PIN change</Text>
              }
            </TouchableOpacity>

            <View style={ots.resendRow}>
              <Text style={ots.resendLabel}>Didn't receive it? </Text>
              {resending ? (
                <ActivityIndicator size="small" color={COLORS.primary} />
              ) : countdown > 0 ? (
                <Text style={ots.resendCooldown}>
                  Resend in <Text style={ots.resendTimer}>{countdown}s</Text>
                </Text>
              ) : (
                <TouchableOpacity onPress={handleResendOTP}>
                  <Text style={ots.resendActive}>Resend code</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  if (step === "confirm") {
    return (
      <PinPad
        key="change-confirm"
        icon="shield-checkmark"
        title="Confirm new PIN"
        subtitle="Enter your new PIN once more"
        onComplete={handleConfirmPIN}
        error={error}
        loading={loading}
        resetKey={resetKey}
        onBack={() => {
          newPinRef.current = "";
          setStep("new");
          setError("");
          setResetKey(k => k + 1);
        }}
      />
    );
  }

  if (step === "new") {
    return (
      <PinPad
        key="change-new"
        icon="lock-open-outline"
        title="New PIN"
        subtitle="Choose a new 6-digit PIN"
        onComplete={handleNewPIN}
        error={error}
        loading={false}
        resetKey={resetKey}
        onBack={() => {
          setStep("current");
          setError("");
          setResetKey(k => k + 1);
        }}
      />
    );
  }

  return (
    <PinPad
      key="change-current"
      icon="key-outline"
      title="Enter current PIN"
      subtitle="Confirm your identity before changing your PIN"
      onComplete={handleCurrentPIN}
      error={error}
      loading={loading}
      resetKey={resetKey}
      onBack={() => router.back()}
    />
  );
}

// ── OTP step styles ──────────────────────────────────────────────────────────

const ots = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: COLORS.background },
  flex:    { flex: 1 },
  container: { flex: 1, padding: 28 },

  back:     { marginTop: 16, marginBottom: 32 },
  backText: { color: COLORS.primary, fontSize: FONTS.md, fontWeight: "600" },

  header:   { marginBottom: 36 },
  title:    { fontSize: FONTS.xxl, fontWeight: "700", color: COLORS.text, marginBottom: 8 },
  subtitle: { fontSize: FONTS.md, color: COLORS.textSecondary },
  phone:    { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.primary, marginTop: 4 },

  label: {
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 15, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.white, marginBottom: 8,
  },
  otpInput: { fontSize: FONTS.xxl, textAlign: "center", letterSpacing: 10 },

  error:   { color: COLORS.error,   fontSize: FONTS.sm, marginBottom: 10, fontWeight: "500" },
  success: { color: COLORS.success, fontSize: FONTS.sm, marginBottom: 10, fontWeight: "500" },

  btn: {
    backgroundColor: COLORS.primary, padding: 16,
    borderRadius: RADIUS.md, alignItems: "center", marginTop: 8,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },

  resendRow: {
    flexDirection: "row", alignItems: "center",
    justifyContent: "center", marginTop: 24,
  },
  resendLabel:    { fontSize: FONTS.sm, color: COLORS.textSecondary },
  resendCooldown: { fontSize: FONTS.sm, color: COLORS.textMuted },
  resendTimer:    { fontWeight: "700", color: COLORS.textSecondary },
  resendActive:   { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.primary, textDecorationLine: "underline" },
});
