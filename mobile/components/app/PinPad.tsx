/**
 * PinPad — full-screen PIN entry component.
 *
 * Features:
 *   - 6-dot progress indicator with show/hide toggle (eye icon)
 *   - 3×3 numpad + 0 + backspace
 *   - Loading overlay while async action is in flight
 *   - Vibrate + clear on error
 *   - Back button, Forgot PIN link
 */
import { useEffect, useState } from "react";
import {
  View, Text, TouchableOpacity, StyleSheet,
  ActivityIndicator, Vibration, Dimensions,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

const { width } = Dimensions.get("window");
const KEY_SIZE = Math.floor((width - 80) / 3);
const DOT_SIZE = 20;
const PIN_LEN  = 6;
const BG       = "#1A5C38";

const KEYS = [
  ["1", "2", "3"],
  ["4", "5", "6"],
  ["7", "8", "9"],
  ["",  "0", "⌫"],
];

type Props = {
  title:          string;
  subtitle?:      string;
  icon?:          string;
  onComplete:     (pin: string) => void;
  onForgot?:      () => void;
  forgotLoading?: boolean;
  error?:         string;
  loading?:       boolean;
  resetKey?:      number;
  onBack?:        () => void;
};

export default function PinPad({
  title, subtitle, icon = "lock-closed",
  onComplete, onForgot, forgotLoading,
  error, loading, resetKey, onBack,
}: Props) {
  const [pin,     setPin]     = useState("");
  const [visible, setVisible] = useState(false);  // show/hide PIN digits

  // Parent signals: reset dots (wrong PIN, mismatch, etc.)
  useEffect(() => {
    setPin("");
  }, [resetKey]);

  // Vibrate and clear on error
  useEffect(() => {
    if (error) {
      Vibration.vibrate([0, 80, 60, 80]);
      setPin("");
    }
  }, [error]);

  function press(key: string) {
    if (loading) return;

    if (key === "⌫") {
      setPin(p => p.slice(0, -1));
      return;
    }
    if (!key) return;

    const next = pin + key;
    setPin(next);

    if (next.length === PIN_LEN) {
      // Briefly keep dots full so the user sees the last digit fill,
      // then hand off to the parent handler.
      setTimeout(() => onComplete(next), 80);
    }
  }

  const showLoading = loading;

  return (
    <SafeAreaView style={s.safe}>

      {/* Back */}
      {onBack && (
        <TouchableOpacity style={s.back} onPress={onBack} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color="#fff" />
        </TouchableOpacity>
      )}

      {/* Icon + heading */}
      <View style={s.header}>
        <Ionicons name={icon as any} size={52} color="#fff" style={s.icon} />
        <Text style={s.title}>{title}</Text>
        {subtitle ? <Text style={s.subtitle}>{subtitle}</Text> : null}
      </View>

      {/* Dots row + eye toggle */}
      <View style={s.dotsWrap}>
        <View style={s.dots}>
          {Array.from({ length: PIN_LEN }).map((_, i) => {
            const filled = i < pin.length;
            if (visible && filled) {
              // Show actual digit
              return (
                <View key={i} style={[s.dot, s.dotFilled, s.dotDigit]}>
                  <Text style={s.digitText}>{pin[i]}</Text>
                </View>
              );
            }
            return (
              <View key={i} style={[s.dot, filled && s.dotFilled]} />
            );
          })}
        </View>

        {/* Eye toggle — show below the dots */}
        <TouchableOpacity
          style={s.eye}
          onPress={() => setVisible(v => !v)}
          hitSlop={10}
        >
          <Ionicons
            name={visible ? "eye-off-outline" : "eye-outline"}
            size={20}
            color="rgba(255,255,255,0.7)"
          />
          <Text style={s.eyeLabel}>
            {visible ? "Hide PIN" : "Show PIN"}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Error / placeholder */}
      {error
        ? <Text style={s.error}>{error}</Text>
        : <View style={s.errorPlaceholder} />
      }

      {/* Numpad — disabled + dimmed while loading */}
      <View style={[s.pad, showLoading && s.padDisabled]}>
        {KEYS.map((row, ri) => (
          <View key={ri} style={s.row}>
            {row.map((key, ki) => {
              const isEmpty = key === "";
              const isBack  = key === "⌫";
              return (
                <TouchableOpacity
                  key={ki}
                  style={[s.key, isEmpty && s.keyInvisible]}
                  onPress={() => press(key)}
                  disabled={isEmpty || !!loading}
                  activeOpacity={0.55}
                >
                  {isBack ? (
                    <Ionicons name="backspace-outline" size={28} color="#fff" />
                  ) : (
                    <Text style={s.keyText}>{key}</Text>
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        ))}
      </View>

      {/* Forgot PIN */}
      {onForgot ? (
        <TouchableOpacity
          style={s.forgot}
          onPress={onForgot}
          disabled={!!loading || !!forgotLoading}
        >
          {forgotLoading
            ? <ActivityIndicator color="rgba(255,255,255,0.8)" size="small" />
            : <Text style={s.forgotText}>Forgot PIN?</Text>
          }
        </TouchableOpacity>
      ) : (
        <View style={s.forgotPlaceholder} />
      )}

      {/* Full-screen loading overlay — shown while API call is in flight */}
      {showLoading && (
        <View style={s.loadingOverlay}>
          <ActivityIndicator color="#fff" size="large" />
          <Text style={s.loadingText}>Please wait…</Text>
        </View>
      )}

    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: BG,
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 16,
  },

  back: {
    position: "absolute",
    top: 52,
    left: 20,
    zIndex: 10,
    padding: 6,
  },

  header: {
    alignItems: "center",
    paddingTop: 28,
    paddingHorizontal: 28,
  },
  icon:  { marginBottom: 18, opacity: 0.95 },
  title: {
    fontSize: 24,
    fontWeight: "700",
    color: "#fff",
    textAlign: "center",
    letterSpacing: 0.3,
  },
  subtitle: {
    fontSize: 15,
    color: "rgba(255,255,255,0.75)",
    marginTop: 6,
    textAlign: "center",
  },

  dotsWrap: {
    alignItems: "center",
    gap: 12,
  },
  dots: {
    flexDirection: "row",
    gap: 16,
  },
  dot: {
    width:  DOT_SIZE,
    height: DOT_SIZE,
    borderRadius: DOT_SIZE / 2,
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.65)",
    backgroundColor: "transparent",
  },
  dotFilled: {
    backgroundColor: "#fff",
    borderColor: "#fff",
  },
  dotDigit: {
    alignItems: "center",
    justifyContent: "center",
  },
  digitText: {
    fontSize: 13,
    fontWeight: "700",
    color: BG,
    lineHeight: 18,
  },
  eye: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  eyeLabel: {
    color: "rgba(255,255,255,0.65)",
    fontSize: 13,
    fontWeight: "500",
  },

  error: {
    color: "#FFD6D6",
    fontSize: 13,
    fontWeight: "600",
    textAlign: "center",
    paddingHorizontal: 32,
    minHeight: 20,
  },
  errorPlaceholder: { minHeight: 20 },

  pad: {
    width: "100%",
    paddingHorizontal: 20,
    gap: 4,
    marginBottom: 4,
  },
  padDisabled: { opacity: 0.4 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  key: {
    width:  KEY_SIZE,
    height: KEY_SIZE * 0.72,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: KEY_SIZE / 2,
  },
  keyInvisible: { opacity: 0 },
  keyText: {
    fontSize: 34,
    fontWeight: "300",
    color: "#fff",
    lineHeight: 40,
  },

  forgot: {
    paddingVertical: 14,
    paddingHorizontal: 28,
    alignItems: "center",
    minHeight: 44,
    justifyContent: "center",
  },
  forgotPlaceholder: { minHeight: 44 },
  forgotText: {
    fontSize: 15,
    fontWeight: "700",
    color: "#fff",
    letterSpacing: 0.3,
  },

  // Full overlay while API call is in flight
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(26, 92, 56, 0.88)",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
    zIndex: 99,
  },
  loadingText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "600",
    opacity: 0.9,
  },
});
