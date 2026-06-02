/**
 * KYC Status screen — shown when a user taps "View Status" or "Pending Review"
 * from their profile.
 *
 * Displays appropriate content based on the verification state:
 *
 *  email not verified  →  prompt to check email / resend
 *  under review        →  "all set, we'll let you know" + submitted checklist
 *  manual review       →  what additional info may be needed
 *  rejected            →  reason + re-submit (redirects to kyc.tsx)
 *  approved            →  shouldn't reach here, but handles gracefully
 */
import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity,
  ScrollView, ActivityIndicator, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getKYCStatus } from "../api/auth";
import API from "../api/client";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

type KYCData = {
  status:           "not_submitted" | "pending" | "approved" | "rejected";
  email_verified:   boolean;
  email:            string;
  rejection_reason: string;
  given_names:      string;
  id_front:         string | null;
  selfie:           string | null;
};

export default function KYCStatusScreen() {
  const [kyc,     setKyc]     = useState<KYCData | null>(null);
  const [loading, setLoading] = useState(true);
  const [resending, setResending] = useState(false);

  useFocusEffect(
    useCallback(() => {
      getKYCStatus()
        .then(data => setKyc(data as KYCData))
        .catch(() => {})
        .finally(() => setLoading(false));
    }, [])
  );

  const handleResendEmail = async () => {
    setResending(true);
    try {
      await API.post("users/kyc/resend-verification/");
      Alert.alert("Sent!", `A new verification link has been sent to ${kyc?.email}.`);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Could not resend. Please try again.");
    } finally {
      setResending(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Verification Status" variant="light" leading="back"
          onBack={() => router.replace("/(drawer)/profile")} />
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  if (!kyc || kyc.status === "not_submitted") {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Verification Status" variant="light" leading="back"
          onBack={() => router.replace("/(drawer)/profile")} />
        <View style={s.center}>
          <Text style={s.emptyText}>No KYC submission found.</Text>
          <TouchableOpacity style={s.primaryBtn} onPress={() => router.replace("/kyc")}>
            <Text style={s.primaryBtnText}>Start Verification</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  if (kyc.status === "approved") {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Verification Status" variant="light" leading="back"
          onBack={() => router.replace("/(drawer)/profile")} />
        <View style={s.center}>
          <Ionicons name="shield-checkmark" size={64} color={COLORS.success} style={{ marginBottom: 16 }} />
          <Text style={s.heroTitle}>You're fully verified</Text>
          <Text style={s.heroSub}>All features are unlocked. Welcome to WEPL!</Text>
          <TouchableOpacity style={[s.primaryBtn, { marginTop: 24 }]}
            onPress={() => router.replace("/(drawer)/profile")}>
            <Text style={s.primaryBtnText}>Back to profile</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ── Pending: email not yet verified ─────────────────────────────────────────
  if (kyc.status === "pending" && !kyc.email_verified) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Verification Status" variant="light" leading="back"
          onBack={() => router.replace("/(drawer)/profile")} />
        <ScrollView contentContainerStyle={s.scroll}>

          <View style={s.iconWrap}>
            <Ionicons name="mail-outline" size={48} color="#B45309" />
          </View>
          <Text style={s.heroTitle}>Verify your email to continue</Text>
          <Text style={s.heroSub}>
            We've received your documents. Before we can start the review,
            please verify the email address on your application.
          </Text>

          <View style={s.infoCard}>
            <Ionicons name="information-circle-outline" size={18} color={COLORS.primary} />
            <Text style={s.infoText}>
              A verification link was sent to{" "}
              <Text style={{ fontWeight: "700" }}>{kyc.email}</Text>.
              Check your inbox (and spam folder).
            </Text>
          </View>

          <TouchableOpacity
            style={[s.primaryBtn, resending && { opacity: 0.6 }]}
            onPress={handleResendEmail}
            disabled={resending}
          >
            {resending
              ? <ActivityIndicator color="#fff" />
              : <Text style={s.primaryBtnText}>Resend verification email</Text>
            }
          </TouchableOpacity>

          <Text style={s.note}>
            Once your email is verified, your documents will be reviewed automatically.
          </Text>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── Pending: email verified, under review ────────────────────────────────────
  if (kyc.status === "pending" && kyc.email_verified) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Verification Status" variant="light" leading="back"
          onBack={() => router.replace("/(drawer)/profile")} />
        <ScrollView contentContainerStyle={s.scroll}>

          <View style={s.iconWrap}>
            <Ionicons name="time-outline" size={48} color="#B45309" />
          </View>
          <Text style={s.heroTitle}>You're all set!</Text>
          <Text style={s.heroSub}>
            We've received everything we need. Your identity is being
            verified and we'll notify you the moment it's done.
          </Text>

          {/* Submitted checklist */}
          <View style={s.checklistCard}>
            <Text style={s.checklistTitle}>What we have from you</Text>
            {[
              { label: "Personal information",        done: true },
              { label: "National ID documents",       done: !!kyc.id_front },
              { label: "Selfie photo",                done: !!kyc.selfie },
              { label: "Email address verified",      done: kyc.email_verified },
              { label: "Physical address",            done: true },
              { label: "Financial profile",           done: true },
            ].map((item, i) => (
              <View key={i} style={s.checkRow}>
                <Ionicons
                  name={item.done ? "checkmark-circle" : "ellipse-outline"}
                  size={18}
                  color={item.done ? COLORS.success : COLORS.textMuted}
                />
                <Text style={[s.checkLabel, !item.done && { color: COLORS.textMuted }]}>
                  {item.label}
                </Text>
              </View>
            ))}
          </View>

          {/* Manual review note */}
          <View style={s.manualCard}>
            <Ionicons name="shield-outline" size={18} color={COLORS.primary} />
            <View style={{ flex: 1 }}>
              <Text style={s.manualTitle}>What happens next?</Text>
              <Text style={s.manualBody}>
                Your documents are checked against official records automatically.
                In most cases this takes under 5 minutes. If anything needs
                a closer look, our team will review it manually and may reach
                out to you — here's what might be requested:
              </Text>
              <View style={s.manualList}>
                {[
                  "A clearer photo of your national ID",
                  "An additional government-issued document",
                  "Proof of address (utility bill or bank statement)",
                  "A short video selfie for liveness verification",
                ].map((item, i) => (
                  <View key={i} style={s.manualItem}>
                    <Text style={s.manualBullet}>•</Text>
                    <Text style={s.manualItemText}>{item}</Text>
                  </View>
                ))}
              </View>
              <Text style={s.manualFooter}>
                You'll receive an in-app notification and email if any of the
                above is needed. No action required from you right now.
              </Text>
            </View>
          </View>

          <TouchableOpacity style={s.secondaryBtn} onPress={() => router.replace("/(drawer)/profile")}>
            <Text style={s.secondaryBtnText}>Back to profile</Text>
          </TouchableOpacity>

        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── Rejected ─────────────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={s.safe}>
      <AppHeader title="Verification Status" variant="light" leading="back"
        onBack={() => router.replace("/(drawer)/profile")} />
      <ScrollView contentContainerStyle={s.scroll}>

        <View style={s.iconWrap}>
          <Ionicons name="alert-circle-outline" size={48} color={COLORS.error} />
        </View>
        <Text style={s.heroTitle}>Action required</Text>
        <Text style={s.heroSub}>
          Your verification was not approved. Please review the reason below
          and re-submit with the corrected information.
        </Text>

        {kyc.rejection_reason ? (
          <View style={[s.infoCard, { borderLeftColor: COLORS.error, borderLeftWidth: 3 }]}>
            <Ionicons name="information-circle-outline" size={18} color={COLORS.error} />
            <Text style={[s.infoText, { color: COLORS.error }]}>{kyc.rejection_reason}</Text>
          </View>
        ) : null}

        <View style={s.checklistCard}>
          <Text style={s.checklistTitle}>Common reasons for rejection</Text>
          {[
            "ID photo was blurry or partially obscured",
            "Name on ID doesn't match the application",
            "ID document has expired",
            "Selfie didn't clearly show your face",
            "Date of birth mismatch",
          ].map((item, i) => (
            <View key={i} style={s.checkRow}>
              <Ionicons name="close-circle-outline" size={16} color={COLORS.error} />
              <Text style={[s.checkLabel, { color: COLORS.textSecondary }]}>{item}</Text>
            </View>
          ))}
        </View>

        <TouchableOpacity style={s.primaryBtn} onPress={() => router.replace("/kyc")}>
          <Text style={s.primaryBtnText}>Re-submit verification</Text>
        </TouchableOpacity>

        <Text style={s.note}>
          Need help? Contact us at{" "}
          <Text style={{ color: COLORS.primary }}>support@wepl.app</Text>
        </Text>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 32 },
  scroll: { padding: 24, paddingBottom: 48 },

  iconWrap: {
    width: 88, height: 88, borderRadius: 44,
    backgroundColor: COLORS.background,
    borderWidth: 2, borderColor: COLORS.border,
    justifyContent: "center", alignItems: "center",
    alignSelf: "center", marginBottom: 20,
  },

  heroTitle: {
    fontSize: FONTS.xxl, fontWeight: "700",
    color: COLORS.text, textAlign: "center", marginBottom: 10,
  },
  heroSub: {
    fontSize: FONTS.md, color: COLORS.textSecondary,
    textAlign: "center", lineHeight: 22, marginBottom: 24,
  },

  infoCard: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    backgroundColor: COLORS.primaryPale,
    borderRadius: RADIUS.md, padding: 14, marginBottom: 20,
  },
  infoText: { flex: 1, fontSize: FONTS.sm, color: COLORS.primary, lineHeight: 20 },

  checklistCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg, padding: 16,
    borderWidth: 1, borderColor: COLORS.border,
    marginBottom: 16, gap: 10,
  },
  checklistTitle: {
    fontSize: FONTS.sm, fontWeight: "700",
    color: COLORS.text, marginBottom: 4,
    textTransform: "uppercase", letterSpacing: 0.5,
  },
  checkRow:  { flexDirection: "row", alignItems: "center", gap: 10 },
  checkLabel:{ fontSize: FONTS.md, color: COLORS.text, flex: 1 },

  manualCard: {
    flexDirection: "row", alignItems: "flex-start", gap: 12,
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg, padding: 16,
    borderWidth: 1, borderColor: COLORS.border,
    borderLeftWidth: 3, borderLeftColor: COLORS.primary,
    marginBottom: 24,
  },
  manualTitle: {
    fontSize: FONTS.md, fontWeight: "700",
    color: COLORS.text, marginBottom: 6,
  },
  manualBody: {
    fontSize: FONTS.sm, color: COLORS.textSecondary,
    lineHeight: 20, marginBottom: 12,
  },
  manualList:     { gap: 6, marginBottom: 12 },
  manualItem:     { flexDirection: "row", gap: 6 },
  manualBullet:   { fontSize: FONTS.sm, color: COLORS.primary },
  manualItemText: { fontSize: FONTS.sm, color: COLORS.textSecondary, flex: 1, lineHeight: 19 },
  manualFooter:   { fontSize: FONTS.xs, color: COLORS.textMuted, lineHeight: 18, fontStyle: "italic" },

  primaryBtn: {
    backgroundColor: COLORS.primary, padding: 16,
    borderRadius: RADIUS.md, alignItems: "center", marginBottom: 12,
  },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: FONTS.md },

  secondaryBtn: {
    borderWidth: 1.5, borderColor: COLORS.border,
    padding: 15, borderRadius: RADIUS.md,
    alignItems: "center", backgroundColor: COLORS.white,
  },
  secondaryBtnText: { color: COLORS.text, fontWeight: "600", fontSize: FONTS.md },

  note: {
    fontSize: FONTS.sm, color: COLORS.textMuted,
    textAlign: "center", marginTop: 12, lineHeight: 20,
  },

  emptyText: {
    fontSize: FONTS.md, color: COLORS.textSecondary,
    textAlign: "center", marginBottom: 20,
  },
});
