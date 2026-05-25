import { useState } from "react";
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
import { verifyOTP } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

export default function OTPScreen() {
  const { phone_number } = useLocalSearchParams<{ phone_number: string }>();
  const [otp, setOTP] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleVerify = async () => {
    if (otp.length < 4) {
      setError("Enter the OTP you received");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const data = await verifyOTP(phone_number, otp);
      await storage.setItem("access", data.access);
      await storage.setItem("refresh", data.refresh);
      await storage.setItem("phone", phone_number);

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
            placeholder="• • • •"
            placeholderTextColor={COLORS.textMuted}
            keyboardType="numeric"
            value={otp}
            onChangeText={(t) => { setOTP(t); setError(""); }}
            style={[styles.input, styles.otpInput]}
            maxLength={6}
            autoFocus
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleVerify}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color={COLORS.white} />
            ) : (
              <Text style={styles.buttonText}>Verify OTP</Text>
            )}
          </TouchableOpacity>
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
    fontWeight: "bold",
    color: COLORS.text,
    marginBottom: 8,
  },

  subtitle: {
    fontSize: FONTS.md,
    color: COLORS.textSecondary,
  },

  phone: {
    fontSize: FONTS.lg,
    fontWeight: "bold",
    color: COLORS.primary,
    marginTop: 4,
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

  otpInput: {
    fontSize: FONTS.xxl,
    textAlign: "center",
    letterSpacing: 8,
  },

  error: {
    color: COLORS.error,
    fontSize: FONTS.sm,
    marginBottom: 12,
  },

  button: {
    backgroundColor: COLORS.primary,
    padding: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
    marginTop: 10,
  },

  buttonDisabled: { opacity: 0.7 },

  buttonText: {
    color: COLORS.white,
    fontWeight: "bold",
    fontSize: FONTS.md,
  },
});
