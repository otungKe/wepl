import { useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as storage from "../utils/secureStorage";
import { router } from "expo-router";
import { loginWithPIN, requestOTP } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

export default function LoginScreen() {
  const [phone, setPhone]       = useState("");
  const [pin, setPin]           = useState("");
  const [loading, setLoading]   = useState(false);
  const [forgotLoading, setForgotLoading] = useState(false);
  const [error, setError]       = useState("");

  const handleLogin = async () => {
    if (!phone.trim() || pin.length < 6) {
      setError("Enter your phone number and 6-digit PIN");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const data = await loginWithPIN(phone.trim(), pin);
      await storage.setItem("access",  data.access);
      await storage.setItem("refresh", data.refresh);
      await storage.setItem("phone",   phone.trim());
      router.replace("/(drawer)/index");
    } catch (e: any) {
      setError(e?.response?.data?.error || "Invalid phone number or PIN.");
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPIN = async () => {
    const target = phone.trim();
    if (!target) {
      setError("Enter your phone number above first, then tap Forgot PIN.");
      return;
    }
    setError("");
    setForgotLoading(true);
    try {
      const data = await requestOTP(target);
      if (!data.is_registered) {
        setError("No account found for this number. Please register instead.");
        return;
      }
      // OTP screen will detect next_step === "reset_pin" and route to /pin?mode=reset
      router.push({ pathname: "/otp", params: { phone_number: target } });
    } catch (e: any) {
      setError(e?.response?.data?.error || "Failed to send reset code. Try again.");
    } finally {
      setForgotLoading(false);
    }
  };

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
            <Text style={styles.title}>Welcome back</Text>
            <Text style={styles.subtitle}>Log in with your phone number and PIN.</Text>
          </View>

          <View style={styles.form}>
            <Text style={styles.label}>Phone Number</Text>
            <TextInput
              placeholder="0712 345 678"
              placeholderTextColor={COLORS.textMuted}
              value={phone}
              onChangeText={(t) => { setPhone(t); setError(""); }}
              style={styles.input}
              keyboardType="phone-pad"
              autoFocus
            />

            <Text style={[styles.label, { marginTop: 16 }]}>PIN</Text>
            <TextInput
              placeholder="• • • • • •"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="numeric"
              secureTextEntry
              maxLength={6}
              value={pin}
              onChangeText={(t) => { setPin(t); setError(""); }}
              style={[styles.input, styles.pinInput]}
            />

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[styles.button, loading && styles.buttonDisabled]}
              onPress={handleLogin}
              disabled={loading || forgotLoading}
            >
              {loading
                ? <ActivityIndicator color={COLORS.white} />
                : <Text style={styles.buttonText}>Log In</Text>}
            </TouchableOpacity>

            {/* Forgot PIN — sends OTP to the phone typed above */}
            <TouchableOpacity
              style={styles.forgotLink}
              onPress={handleForgotPIN}
              disabled={loading || forgotLoading}
            >
              {forgotLoading
                ? <ActivityIndicator size="small" color={COLORS.primary} />
                : <Text style={styles.forgotLinkText}>Forgot PIN?</Text>}
            </TouchableOpacity>

            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <TouchableOpacity
              style={styles.registerBtn}
              onPress={() => router.replace({ pathname: "/", params: { register: "1" } })}
            >
              <Text style={styles.registerBtnText}>Create a new account</Text>
            </TouchableOpacity>
          </View>

        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:  { flex: 1, backgroundColor: COLORS.background },
  flex:  { flex: 1 },

  container: {
    flex: 1,
    padding: 28,
    backgroundColor: COLORS.background,
  },

  back: { marginTop: 16, marginBottom: 32 },
  backText: { color: COLORS.primary, fontSize: FONTS.md, fontWeight: "600" },

  header: { marginBottom: 36 },
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

  form: {},

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
  pinInput: {
    fontSize: FONTS.xxl,
    textAlign: "center",
    letterSpacing: 10,
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

  forgotLink: {
    marginTop: 16,
    alignItems: "center",
    minHeight: 24,
    justifyContent: "center",
  },
  forgotLinkText: {
    fontSize: FONTS.sm,
    color: COLORS.primary,
    fontWeight: "600",
  },

  divider: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 24,
    gap: 10,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: COLORS.border },
  dividerText: { fontSize: FONTS.sm, color: COLORS.textMuted },

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
