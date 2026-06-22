/**
 * Display Name screen — shown once, right after a new user sets their PIN.
 *
 * Lets the user pick a display name before entering the app.
 * Their avatar initial updates live as they type.
 */
import { useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { updateProfile } from "../api/auth";
import * as storage from "../utils/secureStorage";
import { COLORS, FONTS, RADIUS, avatarColorFor, initialsFor } from "../constants/theme";

export default function DisplayNameScreen() {
  const [name,    setName]    = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const trimmed  = name.trim();
  const initials = trimmed ? initialsFor(trimmed) : "?";
  const palette  = avatarColorFor(trimmed || "new");

  async function handleContinue() {
    if (!trimmed) { setError("Please enter a display name."); return; }
    setError("");
    setLoading(true);
    try {
      await updateProfile({ name: trimmed });
      await storage.setItem("name", trimmed);
      router.replace("/(drawer)" as any);
    } catch {
      setError("Couldn't save your name. You can update it later in your profile.");
      // Don't block — let the user into the app even if the API failed
      setTimeout(() => router.replace("/(drawer)" as any), 1800);
    } finally {
      setLoading(false);
    }
  }

  function handleSkip() {
    router.replace("/(drawer)" as any);
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={s.container}>

          {/* Heading */}
          <View style={s.header}>
            <Text style={s.welcome}>Welcome to WEPL 👋</Text>
            <Text style={s.heading}>What should we call you?</Text>
            <Text style={s.sub}>
              This is the name your community members will see.
              You can change it anytime.
            </Text>
          </View>

          {/* Live avatar preview */}
          <View style={[s.avatar, { backgroundColor: palette.bg }]}>
            <Text style={[s.avatarText, { color: palette.text }]}>{initials}</Text>
          </View>

          {/* Name input */}
          <TextInput
            placeholder="Your display name"
            placeholderTextColor={COLORS.textMuted}
            value={name}
            onChangeText={(t) => { setName(t); setError(""); }}
            style={s.input}
            autoFocus
            maxLength={60}
            returnKeyType="done"
            onSubmitEditing={handleContinue}
          />

          {error ? <Text style={s.error}>{error}</Text> : null}

          {/* CTA */}
          <TouchableOpacity
            style={[s.btn, (!trimmed || loading) && s.btnDisabled]}
            onPress={handleContinue}
            disabled={!trimmed || loading}
          >
            {loading
              ? <ActivityIndicator color={COLORS.white} />
              : <Text style={s.btnText}>Get Started</Text>
            }
          </TouchableOpacity>

          {/* Skip */}
          <TouchableOpacity style={s.skip} onPress={handleSkip} disabled={loading}>
            <Text style={s.skipText}>Skip for now</Text>
          </TouchableOpacity>

        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  flex: { flex: 1 },
  container: {
    flex: 1,
    padding: 28,
    alignItems: "center",
    justifyContent: "center",
  },

  header: { alignItems: "center", marginBottom: 32 },
  welcome: {
    fontSize: FONTS.md,
    color: COLORS.textSecondary,
    marginBottom: 8,
  },
  heading: {
    fontSize: FONTS.xxl,
    fontWeight: "700",
    color: COLORS.text,
    textAlign: "center",
    marginBottom: 10,
  },
  sub: {
    fontSize: FONTS.sm,
    color: COLORS.textSecondary,
    textAlign: "center",
    lineHeight: 20,
  },

  avatar: {
    width: 100,
    height: 100,
    borderRadius: 50,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 28,
  },
  avatarText: {
    fontSize: 42,
    fontWeight: "700",
  },

  input: {
    width: "100%",
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 15,
    fontSize: FONTS.lg,
    color: COLORS.text,
    backgroundColor: COLORS.white,
    textAlign: "center",
    marginBottom: 8,
  },

  error: {
    color: COLORS.error,
    fontSize: FONTS.sm,
    textAlign: "center",
    marginBottom: 8,
  },

  btn: {
    width: "100%",
    backgroundColor: COLORS.primary,
    padding: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
    marginTop: 16,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },

  skip: { marginTop: 20, padding: 8 },
  skipText: {
    fontSize: FONTS.sm,
    color: COLORS.textMuted,
    textDecorationLine: "underline",
  },
});
