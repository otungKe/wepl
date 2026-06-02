/**
 * LockScreen — full-screen session-lock overlay.
 *
 * Rendered inside the authenticated drawer shell whenever the app returns
 * from background after the lock threshold has elapsed.
 *
 * Auth order:
 *   1. If biometric is enabled → auto-trigger biometric prompt.
 *      • Success → call onUnlock() immediately.
 *      • Cancelled / failed → fall through to PIN entry.
 *   2. PIN entry via PinPad.
 *      • Wrong PIN → error message, dots reset.
 *      • Correct PIN → call onUnlock().
 *   3. "Sign out" link at the bottom as a last resort.
 *
 * PIN is verified via a bare axios instance (no interceptors) so that a 401
 * (wrong PIN) is NOT mistaken for an expired token and does NOT log the user out.
 */
import { useEffect, useRef, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, AppState } from "react-native";
import axios from "axios";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { router } from "expo-router";
import * as storage from "../../utils/secureStorage";
import { API_BASE_URL } from "../../constants/config";
import PinPad from "./PinPad";
import { COLORS, FONTS } from "../../constants/theme";

const rawAxios = axios.create({ baseURL: API_BASE_URL });

type Props = {
  onUnlock: () => void;
};

export default function LockScreen({ onUnlock }: Props) {
  const [error,    setError]    = useState("");
  const [resetKey, setResetKey] = useState(0);
  const [loading,  setLoading]  = useState(false);
  const phoneRef = useRef("");

  // On mount: load phone + auto-trigger biometric if enabled.
  useEffect(() => {
    (async () => {
      phoneRef.current = (await storage.getItem("phone")) ?? "";
      await tryBiometric();
    })();
  }, []);

  async function tryBiometric() {
    try {
      const bioEnabled = (await AsyncStorage.getItem("biometric_enabled")) === "true";
      if (!bioEnabled) return;

      const LocalAuth  = await import("expo-local-authentication");
      const hasHardware = await LocalAuth.hasHardwareAsync();
      const isEnrolled  = await LocalAuth.isEnrolledAsync();
      if (!hasHardware || !isEnrolled) return;

      const result = await LocalAuth.authenticateAsync({
        promptMessage:         "Unlock WEPL",
        cancelLabel:           "Use PIN",
        disableDeviceFallback: false,
      });

      if (result.success) onUnlock();
      // Cancelled/failed — PIN pad is already visible.
    } catch {
      // Biometric unavailable — silently fall through to PIN.
    }
  }

  async function handlePIN(pin: string) {
    if (!phoneRef.current) {
      setError("Session expired. Please sign in again.");
      setResetKey(k => k + 1);
      return;
    }

    setLoading(true);
    setError("");
    try {
      await rawAxios.post("users/pin/login/", {
        phone_number: phoneRef.current,
        pin,
      });
      setLoading(false);
      onUnlock();
    } catch (e: any) {
      setLoading(false);
      const status = e?.response?.status;
      if (status === 429) {
        setError("Too many attempts. Account locked for 30 minutes.");
      } else if (status === 401) {
        setError("Incorrect PIN. Try again.");
      } else {
        setError("Could not verify. Check your connection and try again.");
      }
      setResetKey(k => k + 1);
    }
  }

  function handleSignOut() {
    storage.multiRemove(["access", "refresh", "phone", "name"]).then(() => {
      router.replace("/login");
    });
  }

  return (
    <View style={s.overlay}>
      <PinPad
        key="lock-screen"
        icon="lock-closed"
        title="Unlock WEPL"
        subtitle="Enter your PIN to continue"
        onComplete={handlePIN}
        error={error}
        loading={loading}
        resetKey={resetKey}
        onForgot={undefined}
      />

      {/* Biometric retry button */}
      <TouchableOpacity style={s.bioBtn} onPress={tryBiometric}>
        <Text style={s.bioBtnText}>Use biometric instead</Text>
      </TouchableOpacity>

      {/* Sign-out escape hatch */}
      <TouchableOpacity style={s.signOutBtn} onPress={handleSignOut}>
        <Text style={s.signOutText}>Sign out</Text>
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 999,
    backgroundColor: "#1A5C38", // same as PinPad BG so it's seamless
  },
  bioBtn: {
    position: "absolute",
    bottom: 96,
    alignSelf: "center",
    paddingVertical: 8,
    paddingHorizontal: 20,
  },
  bioBtnText: {
    color: "rgba(255,255,255,0.7)",
    fontSize: FONTS.sm,
    fontWeight: "600",
    textDecorationLine: "underline",
  },
  signOutBtn: {
    position: "absolute",
    bottom: 52,
    alignSelf: "center",
    paddingVertical: 8,
    paddingHorizontal: 20,
  },
  signOutText: {
    color: "rgba(255,255,255,0.5)",
    fontSize: FONTS.sm,
    fontWeight: "500",
  },
});
