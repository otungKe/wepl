import { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, router } from "expo-router";
import * as storage from "../utils/secureStorage";
import { verifyOTP, requestOTP } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

const RESEND_COOLDOWN = 60; // seconds before Resend is active again

export default function OTPScreen() {
  const { phone_number } = useLocalSearchParams<{ phone_number: string }>();

  const [otp,           setOTP]           = useState("");
  const [loading,       setLoading]       = useState(false);
  const [resending,     setResending]     = useState(false);
  const [error,         setError]         = useState("");
  const [resendSuccess, setResendSuccess] = useState(false);

  // Countdown timer — starts at RESEND_COOLDOWN, counts to 0, then Resend activates
  const [countdown, setCountdown] = useState(RESEND_COOLDOWN);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Start the countdown on mount (OTP was just sent by the previous screen)
  useEffect(() => {
    startCountdown();
    return () => clearTimer();
  }, []);

  function clearTimer() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function startCountdown() {
    clearTimer();
    setCountdown(RESEND_COOLDOWN);
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearTimer();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  // ── Verify ───────────────────────────────────────────────────────────────

  const handleVerify = async () => {
    if (otp.length < 4) {
      setError("Enter the OTP you received");
      return;
    }
    setError("");
    setResendSuccess(false);
    setLoading(true);
    try {
      const data = await verifyOTP(phone_number, otp);
      await storage.setItem("access",  data.access);
      await storage.setItem("refresh", data.refresh);
      await storage.setItem("phone",   phone_number);

      // Backend tells us what to do next:
      //   "set_pin"   → new user, go through full registration
      //   "reset_pin" → existing user recovering their PIN
      const mode = data.next_step === "reset_pin" ? "reset" : "register";
      router.push({ pathname: "/pin", params: { phone_number, mode } });
    } catch (e: any) {
      setError(e?.response?.data?.error || "Invalid OTP. Try again.");
    } finally {
      setLoading(false);
    }
  };

  // Auto-submit when all 6 digits are entered
  const handleOTPChange = (text: string) => {
    setOTP(text);
    setError("");
    setResendSuccess(false);
    if (text.length === 6) {
      // small delay so the user sees the last digit before submission
      setTimeout(() => handleVerifyWithPin(text), 100);
    }
  };

  const handleVerifyWithPin = async (pin: string) => {
    setError("");
    setLoading(true);
    try {
      const data = await verifyOTP(phone_number, pin);
      await storage.setItem("access",  data.access);
      await storage.setItem("refresh", data.refresh);
      await storage.setItem("phone",   phone_number);
      const mode = data.next_step === "reset_pin" ? "reset" : "register";
      router.push({ pathname: "/pin", params: { phone_number, mode } });
    } catch (e: any) {
      setError(e?.response?.data?.error || "Invalid OTP. Try again.");
      setOTP("");
    } finally {
      setLoading(false);
    }
  };

  // ── Resend ───────────────────────────────────────────────────────────────

  const handleResend = async () => {
    if (countdown > 0 || resending) return;
    setError("");
    setResendSuccess(false);
    setResending(true);
    setOTP("");
    try {
      await requestOTP(phone_number);
      setResendSuccess(true);
      startCountdown();
    } catch (e: any) {
      setError(e?.response?.data?.error || "Failed to resend. Try again.");
    } finally {
      setResending(false);
    }
  };

  const canResend = countdown === 0 && !resending;

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={styles.container}>

          <TouchableOpacity style={styles.back} onPress={() => router.back()}>
            <Text style={styles.backText}>← Back</Text>
          </TouchableOpacity>

          <View style={styles.header}>
            <Text style={styles.title}>Verify OTP</Text>
            <Text style={styles.subtitle}>We sent a code to</Text>
            <Text style={styles.phone}>{phone_number}</Text>
          </View>

          <View style={styles.form}>
            <Text style={styles.label}>One-Time Password</Text>
            <TextInput
              placeholder="• • • • • •"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="numeric"
              value={otp}
              onChangeText={handleOTPChange}
              style={[styles.input, styles.otpInput]}
              maxLength={6}
              autoFocus
              editable={!loading}
            />

            {/* Error */}
            {error ? (
              <Text style={styles.error}>{error}</Text>
            ) : resendSuccess ? (
              <Text style={styles.success}>New OTP sent to {phone_number}</Text>
            ) : null}

            {/* Verify button */}
            <TouchableOpacity
              style={[styles.button, (loading || otp.length < 4) && styles.buttonDisabled]}
              onPress={handleVerify}
              disabled={loading || otp.length < 4}
            >
              {loading
                ? <ActivityIndicator color={COLORS.white} />
                : <Text style={styles.buttonText}>Verify OTP</Text>
              }
            </TouchableOpacity>

            {/* Resend row */}
            <View style={styles.resendRow}>
              <Text style={styles.resendLabel}>Didn't receive it? </Text>

              {resending ? (
                <ActivityIndicator size="small" color={COLORS.primary} style={{ marginLeft: 4 }} />
              ) : canResend ? (
                <TouchableOpacity onPress={handleResend}>
                  <Text style={styles.resendActive}>Resend OTP</Text>
                </TouchableOpacity>
              ) : (
                <Text style={styles.resendCooldown}>
                  Resend in <Text style={styles.resendTimer}>{countdown}s</Text>
                </Text>
              )}
            </View>

          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  flex: { flex: 1 },

  container: {
    flex: 1,
    padding: 28,
    backgroundColor: COLORS.background,
  },

  back: { marginTop: 16, marginBottom: 32 },
  backText: { color: COLORS.primary, fontSize: FONTS.md, fontWeight: "600" },

  header: { marginBottom: 40 },
  title: {
    fontSize: FONTS.xxl,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: FONTS.md,
    color: COLORS.textSecondary,
  },
  phone: {
    fontSize: FONTS.lg,
    fontWeight: "600",
    color: COLORS.primary,
    marginTop: 4,
  },

  form: {},

  label: {
    fontSize: FONTS.sm,
    fontWeight: "600",
    color: COLORS.textSecondary,
    marginBottom: 8,
  },
  input: {
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 15,
    fontSize: FONTS.md,
    color: COLORS.text,
    backgroundColor: COLORS.white,
    marginBottom: 8,
  },
  otpInput: {
    fontSize: FONTS.xxl,
    textAlign: "center",
    letterSpacing: 10,
  },

  error: {
    color: COLORS.error,
    fontSize: FONTS.sm,
    marginBottom: 10,
    marginTop: 2,
    fontWeight: "500",
  },
  success: {
    color: COLORS.success,
    fontSize: FONTS.sm,
    marginBottom: 10,
    marginTop: 2,
    fontWeight: "500",
  },

  button: {
    backgroundColor: COLORS.primary,
    padding: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
    marginTop: 8,
  },
  buttonDisabled: { opacity: 0.5 },
  buttonText: {
    color: COLORS.white,
    fontWeight: "700",
    fontSize: FONTS.md,
  },

  // Resend row
  resendRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 24,
  },
  resendLabel: {
    fontSize: FONTS.sm,
    color: COLORS.textSecondary,
  },
  resendActive: {
    fontSize: FONTS.sm,
    fontWeight: "700",
    color: COLORS.primary,
    textDecorationLine: "underline",
  },
  resendCooldown: {
    fontSize: FONTS.sm,
    color: COLORS.textMuted,
  },
  resendTimer: {
    fontWeight: "700",
    color: COLORS.textSecondary,
  },
});
