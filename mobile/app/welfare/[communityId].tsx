import { useState, useCallback, useRef, useEffect } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert, FlatList, Modal, RefreshControl,
  KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useFocusEffect } from "expo-router";
import * as storage from "../../utils/secureStorage";
import {
  getWelfareFund, getWelfareClaims, getWelfareActivity,
  submitWelfareClaim, voteWelfareClaim,
  WelfareFund, WelfareClaim, WelfareActivity,
} from "../../api/contributions";
import { initiateSTKPush, checkSTKStatus } from "../../api/mpesa";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import { useKYCGate } from "../../hooks/useKYCGate";

function statusBg(s: string) {
  switch (s) {
    case 'APPROVED': case 'DISBURSED': return { bg: COLORS.primaryPale, text: COLORS.primary };
    case 'REJECTED':                   return { bg: '#fce8e6',           text: '#c0392b' };
    default:                           return { bg: '#fef7e0',           text: '#b7791f' };
  }
}

export default function WelfareScreen() {
  const { communityId, name, isAdmin: isAdminParam } = useLocalSearchParams<{ communityId: string; name?: string; isAdmin?: string }>();
  const cId     = Number(communityId);
  const isAdmin = isAdminParam === "1";

  const [fund, setFund]         = useState<WelfareFund | null>(null);
  const [claims, setClaims]     = useState<WelfareClaim[]>([]);
  const [activity, setActivity] = useState<WelfareActivity[]>([]);
  const [myPhone, setMyPhone]   = useState("");
  const [loading, setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [showPay, setShowPay]     = useState(false);
  const [showClaim, setShowClaim] = useState(false);

  const { requireKYC } = useKYCGate();
  const [wAmount, setWAmount]     = useState("");
  const [wReason, setWReason]     = useState("");
  const [wPhone, setWPhone]       = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling]       = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [f, c, act, phone] = await Promise.all([
        getWelfareFund(cId),
        getWelfareClaims(cId),
        getWelfareActivity(cId),
        storage.getItem("phone"),
      ]);
      setFund(f);
      setClaims(c);
      setActivity(act);
      if (phone) setMyPhone(phone);
    } catch {}
  }, [cId]);

  // Clear any running poll when the component unmounts
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  useFocusEffect(useCallback(() => {
    load().finally(() => setLoading(false));
    // Clear any stale poll when the screen loses focus
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setPolling(false);
      }
    };
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handlePay = async () => {
    if (!wAmount || Number(wAmount) <= 0) { Alert.alert("Required", "Enter a valid amount."); return; }
    setSubmitting(true);
    try {
      const phone = wPhone.trim() || (await storage.getItem("phone")) || "";
      const result = await initiateSTKPush({
        payment_type: 'welfare',
        community_id: cId,
        amount: Number(wAmount),
        phone_number: phone,
      });
      setShowPay(false);
      setWAmount(""); setWPhone("");
      setPolling(true);

      let attempts = 0;
      pollRef.current = setInterval(async () => {
        attempts++;
        try {
          const s = await checkSTKStatus(result.checkout_request_id);
          if (s.status === 'SUCCESS') {
            clearInterval(pollRef.current!);
            setPolling(false);
            Alert.alert("Payment Received", `M-Pesa receipt: ${s.mpesa_receipt}`);
            await load();
          } else if (s.status === 'FAILED' || attempts >= 12) {
            clearInterval(pollRef.current!);
            setPolling(false);
            if (s.status === 'FAILED') Alert.alert("Payment Failed", "M-Pesa payment was not completed.");
            else Alert.alert("Timeout", "Could not confirm payment. Check your M-Pesa messages.");
          }
        } catch { clearInterval(pollRef.current!); setPolling(false); }
      }, 5000);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to initiate payment.");
    } finally { setSubmitting(false); }
  };

  const handleClaim = async () => {
    if (!wAmount || !wReason.trim()) { Alert.alert("Required", "Amount and reason are required."); return; }
    setSubmitting(true);
    try {
      await submitWelfareClaim(cId, { amount_requested: Number(wAmount), reason: wReason.trim() });
      setShowClaim(false);
      setWAmount(""); setWReason("");
      await load();
      Alert.alert("Submitted", "Admins will review your claim and notify you of the decision.");
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    } finally { setSubmitting(false); }
  };

  const handleVote = async (claimId: number, action: 'approve' | 'reject') => {
    try {
      const updated = await voteWelfareClaim(claimId, action);
      setClaims((prev) => prev.map((c) => c.id === claimId ? updated : c));
      await load();
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title="Welfare Fund" variant="light" leading="back" />
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  const balance = fund ? Number(fund.balance) : 0;

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader
        title={name ? `${name} — Welfare` : "Welfare Fund"}
        variant="light"
        leading="back"
      />

      <FlatList
        data={claims}
        keyExtractor={(c) => String(c.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        contentContainerStyle={{ paddingBottom: 40 }}
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        ListHeaderComponent={
          <>
            {/* Hero */}
            <View style={styles.hero}>
              <Text style={styles.heroLabel}>TOTAL WELFARE POOL</Text>
              <Text style={styles.heroAmount}>KES {balance.toLocaleString()}</Text>
              <View style={styles.heroBtns}>
                <TouchableOpacity style={styles.heroBtn} onPress={() => { if (requireKYC()) setShowPay(true); }}>
                  <Ionicons name="add-circle-outline" size={18} color={COLORS.white} />
                  <Text style={styles.heroBtnText}>Contribute</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.heroBtn, styles.heroBtnOutline]} onPress={() => { if (requireKYC()) setShowClaim(true); }}>
                  <Ionicons name="hand-left-outline" size={18} color={COLORS.white} />
                  <Text style={styles.heroBtnText}>Submit Claim</Text>
                </TouchableOpacity>
              </View>
            </View>

            {/* Info note */}
            <View style={styles.infoRow}>
              <Ionicons name="information-circle-outline" size={16} color={COLORS.textMuted} />
              <Text style={styles.infoText}>
                Claims are reviewed and approved by community admins before funds are released.
              </Text>
            </View>

            {/* Section header */}
            <View style={styles.sectionHead}>
              <Text style={styles.sectionLabel}>CLAIMS</Text>
              <Text style={styles.sectionCount}>{claims.length}</Text>
            </View>
          </>
        }
        renderItem={({ item: c }) => {
          const { bg, text } = statusBg(c.status);
          return (
            <View style={styles.card}>
              <View style={styles.cardHead}>
                <Text style={styles.cardAmount}>KES {Number(c.amount_requested).toLocaleString()}</Text>
                <View style={[styles.pill, { backgroundColor: bg }]}>
                  <Text style={[styles.pillText, { color: text }]}>{c.status}</Text>
                </View>
              </View>
              <Text style={styles.cardReason}>{c.reason}</Text>
              <View style={styles.cardMeta}>
                <Ionicons name="person-outline" size={12} color={COLORS.textMuted} />
                <Text style={styles.cardMetaText}>{c.claimant_phone}</Text>
                <Text style={styles.cardDot}>·</Text>
                <Ionicons name="checkmark-circle-outline" size={12} color={COLORS.textMuted} />
                <Text style={styles.cardMetaText}>{c.approve_count} approved</Text>
                <Text style={styles.cardDot}>·</Text>
                <Text style={styles.cardMetaText}>{new Date(c.created_at).toLocaleDateString()}</Text>
              </View>
              {c.status === 'PENDING' && isAdmin && c.claimant_phone !== myPhone && (
                <View style={styles.voteRow}>
                  <TouchableOpacity
                    style={[styles.voteBtn, { backgroundColor: COLORS.success }]}
                    onPress={() => handleVote(c.id, 'approve')}
                  >
                    <Ionicons name="thumbs-up-outline" size={14} color={COLORS.white} />
                    <Text style={styles.voteBtnText}>Approve</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.voteBtn, { backgroundColor: COLORS.error }]}
                    onPress={() => handleVote(c.id, 'reject')}
                  >
                    <Ionicons name="thumbs-down-outline" size={14} color={COLORS.white} />
                    <Text style={styles.voteBtnText}>Reject</Text>
                  </TouchableOpacity>
                </View>
              )}
              {c.status === 'PENDING' && c.claimant_phone === myPhone && (
                <Text style={styles.pendingNote}>Awaiting admin review — you submitted this claim</Text>
              )}
              {c.status === 'PENDING' && !isAdmin && c.claimant_phone !== myPhone && (
                <Text style={styles.pendingNote}>Awaiting admin review</Text>
              )}
            </View>
          );
        }}
        ListEmptyComponent={
          <View style={styles.emptyBox}>
            <Ionicons name="heart-outline" size={52} color={COLORS.textMuted} />
            <Text style={styles.emptyTitle}>No claims yet</Text>
            <Text style={styles.emptySub}>
              Members can submit a claim when they need emergency support from the pool.
            </Text>
          </View>
        }
        ListFooterComponent={
          <View style={{ marginTop: 24 }}>
            {/* Activity header */}
            <View style={styles.sectionHead}>
              <Text style={styles.sectionLabel}>TRANSACTION HISTORY</Text>
              <Text style={styles.sectionCount}>{activity.length}</Text>
            </View>

            {activity.length === 0 ? (
              <View style={styles.activityEmpty}>
                <Ionicons name="receipt-outline" size={32} color={COLORS.textMuted} />
                <Text style={styles.activityEmptyText}>No transactions yet</Text>
              </View>
            ) : (
              activity.map((a, i) => {
                const isDeposit = a.type === 'DEPOSIT';
                return (
                  <View key={i} style={styles.activityRow}>
                    <View style={[styles.activityIcon, { backgroundColor: isDeposit ? '#e6f4ea' : '#fce8e6' }]}>
                      <Ionicons
                        name={isDeposit ? "arrow-down-outline" : "arrow-up-outline"}
                        size={18}
                        color={isDeposit ? COLORS.success : COLORS.error}
                      />
                    </View>
                    <View style={styles.activityInfo}>
                      <Text style={styles.activityName}>{a.name || a.phone}</Text>
                      <Text style={styles.activityNote} numberOfLines={1}>{a.note}</Text>
                      {a.mpesa_receipt ? (
                        <Text style={styles.activityReceipt}>Receipt: {a.mpesa_receipt}</Text>
                      ) : null}
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={[styles.activityAmount, { color: isDeposit ? COLORS.success : COLORS.error }]}>
                        {isDeposit ? '+' : '-'} KES {Number(a.amount).toLocaleString()}
                      </Text>
                      <Text style={styles.activityDate}>
                        {new Date(a.date).toLocaleDateString([], { day: 'numeric', month: 'short', year: '2-digit' })}
                      </Text>
                      {!isDeposit && a.status && (
                        <View style={[styles.activityStatusPill, { backgroundColor: a.status === 'DISBURSED' ? COLORS.primaryPale : '#fef7e0' }]}>
                          <Text style={[styles.activityStatusText, { color: a.status === 'DISBURSED' ? COLORS.primary : '#b7791f' }]}>{a.status}</Text>
                        </View>
                      )}
                    </View>
                  </View>
                );
              })
            )}
          </View>
        }
      />

      {/* Polling banner */}
      {polling && (
        <View style={styles.pollingBanner}>
          <ActivityIndicator size="small" color={COLORS.white} />
          <Text style={styles.pollingText}>Waiting for M-Pesa confirmation…</Text>
        </View>
      )}

      {/* Contribute modal */}
      <Modal visible={showPay} transparent animationType="slide">
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <View style={styles.overlay}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Top up Welfare Fund</Text>
            <Text style={styles.sheetHint}>An M-Pesa STK push will be sent to your phone. Enter your PIN to confirm.</Text>
            <Text style={styles.fieldLabel}>Amount (KES)</Text>
            <TextInput
              value={wAmount}
              onChangeText={setWAmount}
              placeholder="e.g. 500"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              keyboardType="numeric"
              autoFocus
            />
            <Text style={styles.fieldLabel}>M-Pesa Phone (optional)</Text>
            <TextInput
              value={wPhone}
              onChangeText={setWPhone}
              placeholder="07XX XXX XXX — leave blank to use yours"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              keyboardType="phone-pad"
            />
            <View style={styles.sheetActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowPay(false); setWAmount(""); setWPhone(""); }}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handlePay} disabled={submitting}>
                {submitting
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={styles.confirmText}>Pay via M-Pesa</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Claim modal */}
      <Modal visible={showClaim} transparent animationType="slide">
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <View style={styles.overlay}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Submit Welfare Claim</Text>
            <Text style={styles.sheetHint}>Describe your need clearly so members can make an informed vote.</Text>
            <Text style={styles.fieldLabel}>Amount Requested (KES)</Text>
            <TextInput
              value={wAmount}
              onChangeText={setWAmount}
              placeholder="e.g. 5000"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              keyboardType="numeric"
            />
            <Text style={styles.fieldLabel}>Reason</Text>
            <TextInput
              value={wReason}
              onChangeText={setWReason}
              placeholder="Briefly explain your need"
              placeholderTextColor={COLORS.textMuted}
              style={[styles.input, { height: 100, textAlignVertical: "top" }]}
              multiline
            />
            <View style={styles.sheetActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowClaim(false); setWAmount(""); setWReason(""); }}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleClaim} disabled={submitting}>
                {submitting
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={styles.confirmText}>Submit</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  hero: {
    backgroundColor: "#c0392b",
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 32,
    alignItems: "center",
  },
  heroLabel:  { fontSize: 11, fontWeight: "700", color: "rgba(255,255,255,0.7)", letterSpacing: 1, marginBottom: 8 },
  heroAmount: { fontSize: 42, fontWeight: "800", color: COLORS.white, marginBottom: 24 },
  heroBtns:   { flexDirection: "row", gap: 12 },
  heroBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 18, paddingVertical: 10,
    backgroundColor: "rgba(255,255,255,0.2)",
    borderRadius: RADIUS.full,
    borderWidth: 1.5, borderColor: "rgba(255,255,255,0.4)",
  },
  heroBtnOutline: { backgroundColor: "transparent" },
  heroBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },

  infoRow: {
    flexDirection: "row", alignItems: "flex-start", gap: 8,
    marginHorizontal: 16, marginTop: 16, marginBottom: 4,
  },
  infoText: { flex: 1, fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  sectionHead: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: 16, paddingVertical: 12,
  },
  sectionLabel: { fontSize: 11, fontWeight: "700", color: COLORS.textMuted, letterSpacing: 0.8 },
  sectionCount: {
    minWidth: 22, height: 22, borderRadius: 11,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center", alignItems: "center",
    paddingHorizontal: 6,
    fontSize: 12, fontWeight: "700", color: COLORS.primary,
  } as any,

  card: {
    backgroundColor: COLORS.white,
    marginHorizontal: 16,
    borderRadius: RADIUS.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  cardHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  cardAmount: { fontSize: FONTS.xl, fontWeight: "800", color: COLORS.text },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: RADIUS.full },
  pillText: { fontSize: 11, fontWeight: "700" },
  cardReason: { fontSize: FONTS.md, color: COLORS.textSecondary, marginBottom: 8, lineHeight: 20 },
  cardMeta: { flexDirection: "row", alignItems: "center", gap: 4, flexWrap: "wrap" },
  cardMetaText: { fontSize: 12, color: COLORS.textMuted },
  cardDot: { fontSize: 12, color: COLORS.textMuted, marginHorizontal: 2 },
  pendingNote: { fontSize: FONTS.sm, color: COLORS.textMuted, fontStyle: "italic", marginTop: 10 },

  activityEmpty:     { alignItems: "center", paddingVertical: 24, gap: 8 },
  activityEmptyText: { fontSize: FONTS.sm, color: COLORS.textMuted },
  activityRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingHorizontal: 16, paddingVertical: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  activityIcon:       { width: 38, height: 38, borderRadius: 19, justifyContent: "center", alignItems: "center" },
  activityInfo:       { flex: 1 },
  activityName:       { fontSize: FONTS.sm, fontWeight: "600", color: COLORS.text },
  activityNote:       { fontSize: 12, color: COLORS.textMuted, marginTop: 1 },
  activityReceipt:    { fontSize: 11, color: COLORS.primary, marginTop: 2 },
  activityAmount:     { fontSize: FONTS.md, fontWeight: "700" },
  activityDate:       { fontSize: 11, color: COLORS.textMuted, marginTop: 2 },
  activityStatusPill: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full, marginTop: 4 },
  activityStatusText: { fontSize: 10, fontWeight: "700" },
  voteRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  voteBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 10, borderRadius: RADIUS.md },
  voteBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },

  emptyBox: { alignItems: "center", paddingTop: 48, paddingHorizontal: 32, gap: 12 },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub: { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  pollingBanner: {
    flexDirection: "row", alignItems: "center", gap: 10,
    backgroundColor: COLORS.primary,
    paddingHorizontal: 20, paddingVertical: 14,
  },
  pollingText: { color: COLORS.white, fontWeight: "600", fontSize: FONTS.sm },

  overlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    padding: 24, paddingBottom: 40,
  },
  sheetTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, marginBottom: 4 },
  sheetHint:  { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 16, lineHeight: 18 },
  fieldLabel: {
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginBottom: 6, marginTop: 12,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background,
  },
  sheetActions: { flexDirection: "row", gap: 12, marginTop: 20 },
  cancelBtn:  { flex: 1, padding: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, alignItems: "center" },
  cancelText: { color: COLORS.textSecondary, fontWeight: "600" },
  confirmBtn: { flex: 1, padding: 14, borderRadius: RADIUS.md, backgroundColor: "#c0392b", alignItems: "center" },
  confirmText: { color: COLORS.white, fontWeight: "700" },
});
