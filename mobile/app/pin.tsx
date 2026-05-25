import { useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as storage from "../utils/secureStorage";
import { router, useLocalSearchParams } from "expo-router";
import { setPIN, resetPIN } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

export default function PINScreen() {
  const { phone_number, mode } = useLocalSearchParams<{ phone_number: string; mode?: string }>();
  const isReset = mode === "reset";

  const [pin,        setPin]        = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");

  const handleSetPIN = async () => {
    if (pin.length < 6)     { setError("PIN must be 6 digits"); return; }
    if (pin !== confirmPin) { setError("PINs do not match"); return; }
    setError("");
    setLoading(true);
    try {
      const data = isReset ? await resetPIN(pin) : await setPIN(pin);
      await storage.setItem("access",  data.access);
      await storage.setItem("refresh", data.refresh);
      if (phone_number) await storage.setItem("phone", phone_number);
      // New users go to KYC; PIN-reset users go straight to the app.
      router.replace(isReset ? "/(drawer)/index" : "/kyc");
    } catch (e: any) {
      setError(e?.response?.data?.error || "Failed to set PIN. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">

        <Text style={styles.title}>
          {isReset ? "Reset your PIN" : "Create your PIN"}
        </Text>
        <Text style={styles.subtitle}>
          {isReset
            ? "Choose a new 6-digit PIN for your account."
            : "You'll use this 6-digit PIN every time you log in."}
        </Text>

        <Text style={styles.label}>New PIN</Text>
        <TextInput
          placeholder="• • • • • •"
          placeholderTextColor={COLORS.textMuted}
          keyboardType="numeric"
          secureTextEntry
          maxLength={6}
          value={pin}
          onChangeText={t => { setPin(t); setError(""); }}
          style={[styles.input, styles.pinInput]}
          autoFocus
        />

        <Text style={[styles.label, { marginTop: 12 }]}>Confirm PIN</Text>
        <TextInput
          placeholder="• • • • • •"
          placeholderTextColor={COLORS.textMuted}
          keyboardType="numeric"
          secureTextEntry
          maxLength={6}
          value={confirmPin}
          onChangeText={t => { setConfirmPin(t); setError(""); }}
          style={[styles.input, styles.pinInput]}
        />

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleSetPIN}
          disabled={loading}
        >
          {loading
            ? <ActivityIndicator color={COLORS.white} />
            : <Text style={styles.buttonText}>
                {isReset ? "Reset PIN" : "Create Account"}
              </Text>}
        </TouchableOpacity>

      </ScrollView>
    </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:      { flex: 1, backgroundColor: COLORS.background },
  flex:      { flex: 1 },
  container: { flexGrow: 1, padding: 28, justifyContent: "center" },

  title:    { fontSize: FONTS.xxl, fontWeight: "700", color: COLORS.text, marginBottom: 8 },
  subtitle: { fontSize: FONTS.md, color: COLORS.textSecondary, marginBottom: 32, lineHeight: 22 },

  label: {
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 14, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.white, marginBottom: 6,
  },
  pinInput: { fontSize: FONTS.xxl, textAlign: "center", letterSpacing: 10 },

  error: { color: COLORS.error, fontSize: FONTS.sm, marginBottom: 12, marginTop: 4 },

  button:         { backgroundColor: COLORS.primary, padding: 16, borderRadius: RADIUS.md, alignItems: "center", marginTop: 24 },
  buttonDisabled: { opacity: 0.6 },
  buttonText:     { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
});
