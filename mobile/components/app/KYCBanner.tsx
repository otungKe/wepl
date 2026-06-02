/**
 * KYCBanner — persistent top-of-screen prompt shown when the user's
 * KYC is not yet approved.
 *
 * - not_submitted → amber "Verify your identity" banner
 * - pending        → blue  "Under review" banner
 * - rejected       → red   "Action required" banner
 * - approved       → renders nothing
 * - loading        → renders nothing (avoid flash)
 */
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { FONTS, RADIUS } from "../../constants/theme";
import { KYCStatus } from "../../hooks/useKYCGate";

type Config = {
  bg:       string;
  text:     string;
  icon:     string;
  label:    string;
  cta:      string;
};

const CONFIGS: Record<string, Config> = {
  not_submitted: {
    bg:    "#FEF3C7",
    text:  "#92400E",
    icon:  "shield-outline",
    label: "Verify your identity to unlock payments & contributions.",
    cta:   "Verify Now →",
  },
  pending: {
    bg:    "#EFF6FF",
    text:  "#1E40AF",
    icon:  "time-outline",
    label: "Your KYC is under review. Features are limited until approved.",
    cta:   "View Status →",
  },
  rejected: {
    bg:    "#FEF2F2",
    text:  "#991B1B",
    icon:  "alert-circle-outline",
    label: "KYC not approved. Please re-submit your documents.",
    cta:   "Re-submit →",
  },
};

type Props = {
  status: KYCStatus;
};

export default function KYCBanner({ status }: Props) {
  if (status === "approved" || status === "loading") return null;

  const cfg = CONFIGS[status] ?? CONFIGS.not_submitted;

  return (
    <TouchableOpacity
      style={[s.banner, { backgroundColor: cfg.bg }]}
      onPress={() => router.push("/kyc")}
      activeOpacity={0.85}
    >
      <Ionicons name={cfg.icon as any} size={18} color={cfg.text} style={s.icon} />
      <Text style={[s.label, { color: cfg.text }]} numberOfLines={2}>
        {cfg.label}
      </Text>
      <Text style={[s.cta, { color: cfg.text }]}>{cfg.cta}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  banner: {
    flexDirection:  "row",
    alignItems:     "center",
    paddingHorizontal: 14,
    paddingVertical:   10,
    marginHorizontal:  12,
    marginTop:         8,
    borderRadius:      RADIUS.md,
    gap: 8,
  },
  icon: { flexShrink: 0 },
  label: {
    flex:       1,
    fontSize:   FONTS.sm,
    fontWeight: "500",
    lineHeight: 18,
  },
  cta: {
    fontSize:   FONTS.sm,
    fontWeight: "700",
    flexShrink: 0,
  },
});
