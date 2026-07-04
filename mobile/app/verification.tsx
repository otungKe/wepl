/**
 * Verification Center — a single hub (à la PayPal / Payoneer) that consolidates
 * every verification requirement in one place instead of scattering them across
 * the profile. Each requirement is a row with its own status and action:
 *
 *   • Phone number        — verified at sign-up
 *   • Identity (KYC)       — ID + selfie; start / view status / re-submit
 *   • Email address        — verified as part of KYC
 *   • Supporting documents — requested only if a review needs them
 */
import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator,
  Modal, TextInput, Alert, Pressable, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { getKYCStatus, getProfile } from "../api/auth";
import {
  getVerificationRequests, respondToVerificationRequest,
  type VerificationRequest, type VerificationKind,
} from "../api/verification";
import { suppressNextLock } from "../utils/lockSuppress";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

const KIND_ICON: Record<VerificationKind, string> = {
  transaction_docs: "receipt-outline",
  address_proof:    "home-outline",
  kyc_supplement:   "id-card-outline",
  clarification:    "help-circle-outline",
  other:            "document-text-outline",
};

const REQ_STATUS_META: Record<string, { color: string; bg: string; icon: string }> = {
  open:      { color: COLORS.primary,   bg: COLORS.primaryPale, icon: "alert-circle" },
  submitted: { color: "#B45309",        bg: "#FEF3C7",          icon: "time" },
  resolved:  { color: COLORS.success,   bg: COLORS.primaryPale, icon: "checkmark-circle" },
};

type KYCStatus = "not_submitted" | "pending" | "approved" | "rejected";
type KYCData = {
  status: KYCStatus;
  email_verified: boolean;
  email: string;
  rejection_reason: string;
};

type ItemState = "done" | "pending" | "action" | "optional";

const STATE_META: Record<ItemState, { label: string; color: string; bg: string; icon: string }> = {
  done:     { label: "Verified",     color: COLORS.success,  bg: COLORS.primaryPale, icon: "checkmark-circle" },
  pending:  { label: "Under review", color: "#B45309",       bg: "#FEF3C7",          icon: "time" },
  action:   { label: "Required",     color: COLORS.primary,  bg: COLORS.primaryPale, icon: "alert-circle" },
  optional: { label: "If needed",    color: COLORS.textMuted, bg: COLORS.background,  icon: "lock-closed" },
};

const UNLOCKS = ["Payments", "Contributions", "Advances", "Communities"];

export default function VerificationCenterScreen() {
  const [kyc, setKyc] = useState<KYCData | null>(null);
  const [phone, setPhone] = useState<string>("");
  const [requests, setRequests] = useState<VerificationRequest[]>([]);
  const [loading, setLoading] = useState(true);

  // Respond modal state
  const [active, setActive] = useState<VerificationRequest | null>(null);
  const [note, setNote] = useState("");
  const [doc, setDoc] = useState<{ uri: string; name: string; type: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadRequests = useCallback(() => {
    getVerificationRequests().then(setRequests).catch(() => {});
  }, []);

  useFocusEffect(useCallback(() => {
    Promise.all([
      getKYCStatus().then(d => setKyc(d as KYCData)).catch(() => {}),
      getProfile().then(p => setPhone(p?.phone_number ?? "")).catch(() => {}),
      getVerificationRequests().then(setRequests).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []));

  const openRespond = (req: VerificationRequest) => {
    setActive(req); setNote(""); setDoc(null);
  };

  const attachDocument = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "Allow photo access to attach a document.");
      return;
    }
    suppressNextLock();
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7 });
    if (result.canceled) return;
    const asset = result.assets[0];
    setDoc({
      uri: asset.uri,
      name: asset.uri.split("/").pop() ?? "document.jpg",
      type: asset.mimeType ?? "image/jpeg",
    });
  };

  const submitResponse = async () => {
    if (!active) return;
    if (!note.trim() && !doc) {
      Alert.alert("Add a response", "Enter a note or attach a document before submitting.");
      return;
    }
    setSubmitting(true);
    try {
      await respondToVerificationRequest(active.id, { response_note: note.trim(), document: doc ?? undefined });
      setActive(null);
      loadRequests();
    } catch {
      Alert.alert("Error", "Could not submit your response. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const status: KYCStatus = kyc?.status ?? "not_submitted";
  const isVerified = status === "approved";

  // Overall header state
  const overall = isVerified
    ? { title: "Account verified", sub: "All features are unlocked. We'll reach out here if anything ever needs your attention.", color: COLORS.success, icon: "shield-checkmark" }
    : status === "pending"
    ? { title: "Verification in review", sub: "We're checking your documents.", color: "#B45309", icon: "time" }
    : status === "rejected"
    ? { title: "Action needed", sub: "Your last submission needs attention.", color: COLORS.error, icon: "alert-circle" }
    : { title: "Get verified", sub: "Complete a quick check to unlock everything.", color: COLORS.primary, icon: "shield-outline" };

  // Identity row action + state
  const identityState: ItemState =
    status === "approved" ? "done" : status === "pending" ? "pending" : "action";
  const identityAction = () =>
    status === "pending" ? router.push("/kyc-status")
    : status === "rejected" ? router.push("/kyc")
    : router.push("/kyc");

  const emailState: ItemState =
    status === "not_submitted" ? "action" : kyc?.email_verified ? "done" : "pending";

  const items: {
    key: string; icon: string; title: string; sub: string;
    state: ItemState; onPress?: () => void;
  }[] = [
    {
      key: "phone", icon: "call-outline", title: "Phone number",
      sub: phone || "Verified at sign-up", state: "done",
    },
    {
      key: "identity", icon: "card-outline", title: "Identity (KYC)",
      sub: "National ID & selfie", state: identityState, onPress: identityAction,
    },
    {
      key: "email", icon: "mail-outline", title: "Email address",
      sub: status === "not_submitted" ? "Added during verification" : (kyc?.email || "Verified with your documents"),
      state: emailState,
      onPress: status === "pending" && !kyc?.email_verified ? () => router.push("/kyc-status") : undefined,
    },
    {
      key: "docs", icon: "document-text-outline", title: "Supporting documents",
      sub: "Requested only if a review needs them", state: "optional",
    },
  ];

  const completed = items.filter(i => i.state === "done").length;
  const required = items.filter(i => i.state !== "optional").length;

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Verification Center" variant="light" leading="back"
          onBack={() => router.back()} />
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader title="Verification Center" variant="light" leading="back"
        onBack={() => router.back()} />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* Overview */}
        <View style={s.overview}>
          <View style={[s.overviewIcon, { backgroundColor: overall.color + "18" }]}>
            <Ionicons name={overall.icon as any} size={30} color={overall.color} />
          </View>
          <Text style={s.overviewTitle}>{overall.title}</Text>
          <Text style={s.overviewSub}>{overall.sub}</Text>

          {/* Progress */}
          <View style={s.progressTrack}>
            <View style={[s.progressFill, { width: `${(completed / required) * 100}%`, backgroundColor: overall.color }]} />
          </View>
          <Text style={s.progressText}>{completed} of {required} completed</Text>

          {!isVerified && (
            <TouchableOpacity style={s.primaryBtn} onPress={identityAction}>
              <Ionicons name="arrow-forward-circle-outline" size={18} color="#fff" />
              <Text style={s.primaryBtnText}>
                {status === "pending" ? "View status" : status === "rejected" ? "Re-submit" : "Start verification"}
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Requirements list */}
        <Text style={s.sectionLabel}>REQUIREMENTS</Text>
        <View style={s.card}>
          {items.map((it, idx) => {
            const meta = STATE_META[it.state];
            const RowInner = (
              <>
                <View style={[s.rowIcon, { backgroundColor: meta.bg }]}>
                  <Ionicons name={it.icon as any} size={19} color={meta.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.rowTitle}>{it.title}</Text>
                  <Text style={s.rowSub} numberOfLines={1}>{it.sub}</Text>
                </View>
                <View style={[s.statusChip, { backgroundColor: meta.bg }]}>
                  <Ionicons name={meta.icon as any} size={12} color={meta.color} />
                  <Text style={[s.statusChipText, { color: meta.color }]}>{meta.label}</Text>
                </View>
                {it.onPress && <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} style={{ marginLeft: 4 }} />}
              </>
            );
            const rowStyle = [s.row, idx === items.length - 1 && { borderBottomWidth: 0 }];
            return it.onPress ? (
              <TouchableOpacity key={it.key} style={rowStyle} onPress={it.onPress} activeOpacity={0.7}>
                {RowInner}
              </TouchableOpacity>
            ) : (
              <View key={it.key} style={rowStyle}>{RowInner}</View>
            );
          })}
        </View>

        {/* Requests & documents — the Center stays in force after verification:
            this is where follow-up document requests, clarifications, or feedback
            on submitted items appear. */}
        <Text style={s.sectionLabel}>REQUESTS & DOCUMENTS</Text>

        {/* KYC rejection feedback (feedback on an already-submitted item) */}
        {status === "rejected" && kyc?.rejection_reason ? (
          <TouchableOpacity style={[s.requestCard, { marginBottom: 10 }]} activeOpacity={0.7} onPress={() => router.push("/kyc")}>
            <View style={[s.rowIcon, { backgroundColor: "#FEF2F2" }]}>
              <Ionicons name="alert-circle" size={19} color={COLORS.error} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.rowTitle}>Feedback on your submission</Text>
              <Text style={s.requestBody}>{kyc.rejection_reason}</Text>
              <Text style={s.requestAction}>Tap to update and re-submit →</Text>
            </View>
          </TouchableOpacity>
        ) : null}

        {/* Live compliance requests raised by the team */}
        {requests.map(req => {
          const meta = REQ_STATUS_META[req.status] ?? REQ_STATUS_META.open;
          const isOpen = req.status === "open";
          return (
            <View key={req.id} style={[s.requestCard, { borderLeftColor: meta.color, marginBottom: 10 }]}>
              <View style={[s.rowIcon, { backgroundColor: meta.bg }]}>
                <Ionicons name={(KIND_ICON[req.kind] ?? "document-text-outline") as any} size={19} color={meta.color} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={s.requestHead}>
                  <Text style={s.rowTitle} numberOfLines={1}>{req.title}</Text>
                  <View style={[s.statusChip, { backgroundColor: meta.bg }]}>
                    <Ionicons name={meta.icon as any} size={11} color={meta.color} />
                    <Text style={[s.statusChipText, { color: meta.color }]}>{req.status_label}</Text>
                  </View>
                </View>
                <Text style={s.requestBody}>{req.detail}</Text>
                {req.review_note ? <Text style={s.reviewNote}>Note: {req.review_note}</Text> : null}
                {isOpen ? (
                  <TouchableOpacity style={s.respondBtn} onPress={() => openRespond(req)}>
                    <Ionicons name="cloud-upload-outline" size={15} color="#fff" />
                    <Text style={s.respondBtnText}>Respond</Text>
                  </TouchableOpacity>
                ) : req.status === "submitted" ? (
                  <Text style={s.requestAction}>Submitted — we&apos;ll review and update you.</Text>
                ) : null}
              </View>
            </View>
          );
        })}

        {/* Empty state when nothing is outstanding */}
        {requests.length === 0 && !(status === "rejected" && kyc?.rejection_reason) && (
          <View style={s.emptyCard}>
            <Ionicons name="checkmark-done-outline" size={20} color={COLORS.textMuted} />
            <Text style={s.emptyText}>
              No outstanding requests. If we ever need supporting documents or a
              clarification — for example about a transaction or your address —
              it&apos;ll appear here.
            </Text>
          </View>
        )}

        {/* What verification unlocks */}
        {!isVerified && (
          <>
            <Text style={s.sectionLabel}>WHAT YOU UNLOCK</Text>
            <View style={s.unlockWrap}>
              {UNLOCKS.map(u => (
                <View key={u} style={s.unlockChip}>
                  <Ionicons name="lock-open-outline" size={13} color={COLORS.primary} />
                  <Text style={s.unlockChipText}>{u}</Text>
                </View>
              ))}
            </View>
          </>
        )}

        <Text style={s.note}>
          Your information is encrypted and used only to verify your identity.
        </Text>
      </ScrollView>

      {/* Respond modal */}
      <Modal visible={!!active} transparent animationType="slide" onRequestClose={() => setActive(null)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <Pressable style={StyleSheet.absoluteFillObject} onPress={() => setActive(null)} />
          <View style={s.sheet} onStartShouldSetResponder={() => true}>
            <View style={s.sheetHandle} />
            <Text style={s.sheetTitle}>{active?.title}</Text>
            <Text style={s.sheetDetail}>{active?.detail}</Text>

            <TextInput
              value={note}
              onChangeText={setNote}
              placeholder="Add a note (optional if you attach a document)"
              placeholderTextColor={COLORS.textMuted}
              style={s.sheetInput}
              multiline
            />

            <TouchableOpacity style={s.attachBtn} onPress={attachDocument}>
              <Ionicons name={doc ? "checkmark-circle" : "attach-outline"} size={18} color={doc ? COLORS.success : COLORS.primary} />
              <Text style={s.attachText} numberOfLines={1}>{doc ? doc.name : "Attach a document"}</Text>
            </TouchableOpacity>

            <TouchableOpacity style={[s.primaryBtn, submitting && { opacity: 0.6 }]} onPress={submitResponse} disabled={submitting}>
              {submitting ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryBtnText}>Submit response</Text>}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  scroll: { padding: 20, paddingBottom: 48 },

  overview: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg, padding: 22, alignItems: "center",
    borderWidth: 1, borderColor: COLORS.border,
  },
  overviewIcon: {
    width: 60, height: 60, borderRadius: 30,
    justifyContent: "center", alignItems: "center", marginBottom: 12,
  },
  overviewTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, textAlign: "center" },
  overviewSub:   { fontSize: FONTS.sm, color: COLORS.textSecondary, textAlign: "center", marginTop: 4, lineHeight: 20 },

  progressTrack: {
    alignSelf: "stretch", height: 6, borderRadius: 3,
    backgroundColor: COLORS.divider, marginTop: 18, overflow: "hidden",
  },
  progressFill: { height: "100%", borderRadius: 3 },
  progressText: { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 6, fontWeight: "600" },

  primaryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    alignSelf: "stretch", backgroundColor: COLORS.primary,
    paddingVertical: 13, borderRadius: RADIUS.md, marginTop: 18,
  },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: FONTS.md },

  sectionLabel: {
    fontSize: 11, fontWeight: "700", color: COLORS.textMuted,
    letterSpacing: 0.5, marginTop: 24, marginBottom: 8, marginLeft: 4,
  },
  card: {
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.border, overflow: "hidden",
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingHorizontal: 14, paddingVertical: 13,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  rowIcon: {
    width: 38, height: 38, borderRadius: 10,
    justifyContent: "center", alignItems: "center",
  },
  rowTitle: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  rowSub:   { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 2 },

  statusChip: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full,
  },
  statusChipText: { fontSize: 11, fontWeight: "700" },

  requestCard: {
    flexDirection: "row", alignItems: "flex-start", gap: 12,
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg, padding: 14,
    borderWidth: 1, borderColor: COLORS.border,
    borderLeftWidth: 3, borderLeftColor: COLORS.error,
  },
  requestHead:   { flexDirection: "row", alignItems: "center", gap: 8 },
  requestBody:   { fontSize: FONTS.sm, color: COLORS.textSecondary, marginTop: 3, lineHeight: 19 },
  requestAction: { fontSize: FONTS.xs, color: COLORS.primary, fontWeight: "700", marginTop: 6 },
  reviewNote:    { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 4, fontStyle: "italic" },
  respondBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    alignSelf: "flex-start", backgroundColor: COLORS.primary,
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.md, marginTop: 10,
  },
  respondBtnText: { color: "#fff", fontWeight: "700", fontSize: FONTS.sm },

  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 20, paddingBottom: 32, marginTop: "auto", gap: 12,
  },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2, backgroundColor: COLORS.border,
    alignSelf: "center", marginBottom: 4,
  },
  sheetTitle:  { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  sheetDetail: { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 20 },
  sheetInput: {
    borderWidth: 1, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 12, minHeight: 80, textAlignVertical: "top",
    fontSize: FONTS.md, color: COLORS.text,
  },
  attachBtn: {
    flexDirection: "row", alignItems: "center", gap: 8,
    borderWidth: 1, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 12,
  },
  attachText: { flex: 1, fontSize: FONTS.sm, color: COLORS.textSecondary, fontWeight: "600" },
  emptyCard: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg, padding: 14,
    borderWidth: 1, borderColor: COLORS.border,
  },
  emptyText: { flex: 1, fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 19 },

  unlockWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  unlockChip: {
    flexDirection: "row", alignItems: "center", gap: 5,
    backgroundColor: COLORS.primaryPale,
    paddingHorizontal: 12, paddingVertical: 7, borderRadius: RADIUS.full,
  },
  unlockChipText: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },

  note: {
    fontSize: FONTS.xs, color: COLORS.textMuted,
    textAlign: "center", marginTop: 24, lineHeight: 18, paddingHorizontal: 20,
  },
});
