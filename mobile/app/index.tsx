import { useState, useEffect } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import * as storage from "../utils/secureStorage";
import { requestOTP } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

export default function WelcomeScreen() {
  const { register } = useLocalSearchParams<{ register?: string }>();
  const [showRegister, setShowRegister] = useState(register === "1");
  const [phone, setPhone]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");
  const [checking, setChecking]         = useState(true);

  // Redirect already-authenticated users straight to the app
  useEffect(() => {
    storage.getItem("access").then((token) => {
      if (token) router.replace("/(drawer)");
      else setChecking(false);
    });
  }, []);

  const handleSendCode = async () => {
    if (!phone.trim()) {
      setError("Please enter your phone number");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await requestOTP(phone.trim());
      router.push({ pathname: "/otp", params: { phone_number: phone.trim() } });
    } catch (e: any) {
      setError(e?.response?.data?.error || "Failed to send OTP. Try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── Loading splash ──────────────────────────────────────────────────────────
  if (checking) {
    return (
      <View style={styles.splash}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  // ── Register step — enter phone for OTP ────────────────────────────────────
  if (showRegister) {
    return (
      <SafeAreaView style={styles.safe}>
        <KeyboardAvoidingView
          style={styles.flex}
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <View style={styles.container}>
            <TouchableOpacity
              style={styles.back}
              onPress={() => { setShowRegister(false); setError(""); setPhone(""); }}
            >
              <Text style={styles.backText}>← Back</Text>
            </TouchableOpacity>

            <Text style={styles.pageTitle}>Create account</Text>
            <Text style={styles.pageSubtitle}>
              Enter your phone number. We'll send a one-time code to verify it.
            </Text>

            <Text style={styles.label}>Phone Number</Text>
            <TextInput
              placeholder="0712 345 678"
              placeholderTextColor={COLORS.textMuted}
              value={phone}
              onChangeText={(t) => { setPhone(t); setError(""); }}
              keyboardType="phone-pad"
              style={styles.input}
              autoFocus
            />

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[styles.primaryBtn, loading && styles.btnDisabled]}
              onPress={handleSendCode}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color={COLORS.white} />
                : <Text style={styles.primaryBtnText}>Send Code</Text>}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.switchLink}
              onPress={() => { setShowRegister(false); router.push("/login"); }}
            >
              <Text style={styles.switchLinkText}>
                Already have an account?{" "}
                <Text style={styles.switchLinkBold}>Log in</Text>
              </Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  // ── Welcome screen ──────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.welcomeContainer}>

        {/* Branding */}
        <View style={styles.brandArea}>
          <View style={styles.logoMark}>
            <Text style={styles.logoText}>W</Text>
          </View>
          <Text style={styles.brandName}>Wepl</Text>
          <Text style={styles.brandTagline}>Community savings, together.</Text>
        </View>

        {/* CTAs */}
        <View style={styles.ctaArea}>
          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={() => router.push("/login")}
          >
            <Text style={styles.primaryBtnText}>Log In</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.secondaryBtn}
            onPress={() => setShowRegister(true)}
          >
            <Text style={styles.secondaryBtnText}>Create Account</Text>
          </TouchableOpacity>
        </View>

      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: COLORS.background,
  },
  safe: { flex: 1, backgroundColor: COLORS.background },
  flex: { flex: 1 },

  // ── Welcome layout ──────────────────────────────────────────────────────────
  welcomeContainer: {
    flex: 1,
    paddingHorizontal: 32,
    justifyContent: "space-between",
    paddingTop: 80,
    paddingBottom: 52,
  },
  brandArea: {
    alignItems: "center",
    gap: 12,
  },
  logoMark: {
    width: 72,
    height: 72,
    borderRadius: 20,
    backgroundColor: COLORS.primary,
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 4,
  },
  logoText: {
    fontSize: 38,
    fontWeight: "800",
    color: COLORS.white,
  },
  brandName: {
    fontSize: FONTS.hero,
    fontWeight: "800",
    color: COLORS.text,
    letterSpacing: -0.5,
  },
  brandTagline: {
    fontSize: FONTS.md,
    color: COLORS.textSecondary,
    textAlign: "center",
    lineHeight: 22,
  },

  ctaArea: {
    gap: 12,
  },

  // ── Register layout ─────────────────────────────────────────────────────────
  container: {
    flex: 1,
    padding: 28,
  },
  back: { marginTop: 16, marginBottom: 32 },
  backText: { color: COLORS.primary, fontSize: FONTS.md, fontWeight: "600" },

  pageTitle: {
    fontSize: FONTS.xxl,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 8,
  },
  pageSubtitle: {
    fontSize: FONTS.md,
    color: COLORS.textSecondary,
    marginBottom: 32,
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

  switchLink: { marginTop: 24, alignItems: "center" },
  switchLinkText: { fontSize: FONTS.sm, color: COLORS.textSecondary },
  switchLinkBold: { color: COLORS.primary, fontWeight: "700" },

  // ── Shared buttons ──────────────────────────────────────────────────────────
  primaryBtn: {
    backgroundColor: COLORS.primary,
    padding: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
  },
  primaryBtnText: {
    color: COLORS.white,
    fontWeight: "700",
    fontSize: FONTS.md,
  },
  secondaryBtn: {
    backgroundColor: COLORS.white,
    padding: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
    borderWidth: 1.5,
    borderColor: COLORS.border,
  },
  secondaryBtnText: {
    color: COLORS.text,
    fontWeight: "600",
    fontSize: FONTS.md,
  },
  btnDisabled: { opacity: 0.6 },
});
