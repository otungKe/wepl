import { useState, useEffect } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { router, useLocalSearchParams } from "expo-router";
import * as storage from "../utils/secureStorage";
import { requestOTP } from "../api/auth";
import { API_BASE_URL } from "../constants/config";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

console.log("[config] API_BASE_URL =", API_BASE_URL);

/**
 * Decode a JWT payload (no signature verification — client-side read only).
 * Returns the `stage` claim or null if the token is malformed / has no stage.
 *
 * Stage values set by the backend:
 *   "active"       → fully registered user with a PIN set
 *   "otp_verified" → new user who verified OTP but hasn't set a PIN yet
 *   "otp_recovery" → existing user in PIN-reset flow (OTP verified, PIN not reset yet)
 */
function getJWTStage(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // base64url → standard base64
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    return typeof payload.stage === "string" ? payload.stage : null;
  } catch {
    return null;
  }
}

export default function WelcomeScreen() {
  const { register } = useLocalSearchParams<{ register?: string }>();
  const [showRegister, setShowRegister] = useState(register === "1");
  const [phone, setPhone]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");
  const [checking, setChecking]         = useState(true);

  // Returning-user data — shown on the welcome-back card
  const [savedName,  setSavedName]  = useState("");
  const [savedPhone, setSavedPhone] = useState("");
  const [bioEnabled, setBioEnabled] = useState(false);

  useEffect(() => {
    (async () => {
      const [token, storedPhone, storedName, bio] = await Promise.all([
        storage.getItem("access"),
        storage.getItem("phone"),
        storage.getItem("name"),
        AsyncStorage.getItem("biometric_enabled"),
      ]);

      // ── Active session: try biometric then go straight in ──────────────
      if (token && getJWTStage(token) === "active") {
        const bioOn = bio === "true";
        if (storedPhone) setSavedPhone(storedPhone);
        if (storedName)  setSavedName(storedName);
        setBioEnabled(bioOn);

        if (bioOn) {
          try {
            const LocalAuth  = await import("expo-local-authentication");
            const hasHardware = await LocalAuth.hasHardwareAsync();
            const isEnrolled  = await LocalAuth.isEnrolledAsync();
            if (hasHardware && isEnrolled) {
              const result = await LocalAuth.authenticateAsync({
                promptMessage:         "Log in to WEPL",
                cancelLabel:           "Use PIN instead",
                disableDeviceFallback: false,
              });
              if (result.success) {
                // Navigate to drawer root — the tab layout resolves
                // the correct first tab (Communities or Profile) once
                // it has checked isVerified.
                router.replace("/(drawer)" as any);
                return;
              }
              // Cancelled — show welcome-back card with PIN button
            }
          } catch {}
        } else {
          router.replace("/(drawer)" as any);
          return;
        }
        setChecking(false);
        return;
      }

      // ── Incomplete session: wipe and show fresh welcome ─────────────────
      if (token) {
        await storage.multiRemove(["access", "refresh", "phone", "name"]);
        await AsyncStorage.removeItem("biometric_enabled");  // reset for next user
      }

      // ── No token: check if we have saved user data for welcome-back card ─
      if (storedPhone && storedName) {
        setSavedPhone(storedPhone);
        setSavedName(storedName);
        setBioEnabled(bio === "true");
      }

      setChecking(false);
    })();
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
      console.error("[OTP] request failed:", e?.message, e?.code, e?.config?.url);
      setError(e?.response?.data?.error || "Failed to send OTP. Try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── Loading splash ──────────────────────────────────────────────────────────
  if (checking) {
    return (
      <View style={styles.splash}>
        <View style={styles.logoMark}>
          <Text style={styles.logoText}>W</Text>
        </View>
        <ActivityIndicator size="large" color={COLORS.primary} style={{ marginTop: 32 }} />
      </View>
    );
  }

  // ── Welcome back card ───────────────────────────────────────────────────────
  // Shown when the user has no active session but their name/phone are stored.
  // They don't need to type their number — one tap to PIN or biometric.
  if (savedPhone && savedName && !showRegister) {
    const { avatarColorFor, initialsFor } = require("../constants/theme");
    const palette = avatarColorFor(savedPhone);
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.welcomeBackContainer}>

          {/* Branding */}
          <View style={styles.brandArea}>
            <View style={styles.logoMark}>
              <Text style={styles.logoText}>W</Text>
            </View>
            <Text style={styles.brandName}>Wepl</Text>
          </View>

          {/* User card */}
          <View style={styles.userCard}>
            <View style={[styles.wbAvatar, { backgroundColor: palette.bg }]}>
              <Text style={[styles.wbAvatarText, { color: palette.text }]}>
                {initialsFor(savedName)}
              </Text>
            </View>
            <Text style={styles.wbGreeting}>Welcome back,</Text>
            <Text style={styles.wbName}>{savedName}</Text>
            <Text style={styles.wbPhone}>{savedPhone}</Text>
          </View>

          {/* Primary action */}
          <View style={styles.wbActions}>
            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={() => router.push({
                pathname: "/login",
                params: { prefilled_phone: savedPhone },
              })}
            >
              <Text style={styles.primaryBtnText}>
                {bioEnabled ? "Log in with biometrics / PIN" : "Log in with PIN"}
              </Text>
            </TouchableOpacity>

            {/* Switch account */}
            <TouchableOpacity
              style={styles.switchLink}
              onPress={async () => {
                await storage.multiRemove(["access", "refresh", "phone", "name"]);
                await AsyncStorage.removeItem("biometric_enabled");
                setBioEnabled(false);
                setSavedName("");
                setSavedPhone("");
              }}
            >
              <Text style={styles.switchLinkText}>
                Not {savedName.split(" ")[0]}?{" "}
                <Text style={styles.switchLinkBold}>Use a different account</Text>
              </Text>
            </TouchableOpacity>
          </View>

        </View>
      </SafeAreaView>
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

  // ── Welcome-back card ───────────────────────────────────────────────────
  welcomeBackContainer: {
    flex: 1,
    paddingHorizontal: 32,
    justifyContent: "space-between",
    paddingTop: 60,
    paddingBottom: 52,
  },
  userCard: {
    alignItems: "center",
    backgroundColor: COLORS.white,
    borderRadius: 16,
    paddingVertical: 28,
    paddingHorizontal: 24,
    borderWidth: 1,
    borderColor: COLORS.divider,
  },
  wbAvatar: {
    width: 80, height: 80, borderRadius: 40,
    justifyContent: "center", alignItems: "center",
    marginBottom: 16,
  },
  wbAvatarText: { fontSize: 32, fontWeight: "700" },
  wbGreeting:   { fontSize: FONTS.md, color: COLORS.textSecondary, marginBottom: 4 },
  wbName:       { fontSize: FONTS.xxl, fontWeight: "700", color: COLORS.text, marginBottom: 4 },
  wbPhone:      { fontSize: FONTS.sm, color: COLORS.textMuted },
  wbActions:    { gap: 12 },

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
