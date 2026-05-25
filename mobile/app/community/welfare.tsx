import { useState, useCallback } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  ScrollView,
  Modal,
  RefreshControl,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useFocusEffect } from "expo-router";
import {
  getWelfareFund,
  getWelfareClaims,
  contributeToWelfare,
  submitWelfareClaim,
  voteWelfareClaim,
  WelfareFund,
  WelfareClaim,
} from "../../api/contributions";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";

export default function WelfareScreen() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const communityId = Number(id);

  const [fund, setFund] = useState<WelfareFund | null>(null);
  const [claims, setClaims] = useState<WelfareClaim[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Modals
  const [showContribute, setShowContribute] = useState(false);
  const [showClaim, setShowClaim] = useState(false);
  const [amount, setAmount] = useState("");
  const [claimReason, setClaimReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [f, c] = await Promise.all([
        getWelfareFund(communityId),
        getWelfareClaims(communityId),
      ]);
      setFund(f);
      setClaims(c);
    } catch {}
  }, [communityId]);

  useFocusEffect(useCallback(() => {
    load().finally(() => setLoading(false));
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleContribute = async () => {
    if (!amount || Number(amount) <= 0) {
      Alert.alert("Invalid", "Enter a valid amount.");
      return;
    }
    setSubmitting(true);
    try {
      const updated = await contributeToWelfare(communityId, Number(amount));
      setFund(updated);
      setShowContribute(false);
      setAmount("");
      Alert.alert("Thank you!", "Your welfare contribution has been recorded.");
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to contribute.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitClaim = async () => {
    if (!amount || !claimReason.trim()) {
      Alert.alert("Required", "Amount and reason are required.");
      return;
    }
    setSubmitting(true);
    try {
      const claim = await submitWelfareClaim(communityId, {
        amount_requested: Number(amount),
        reason: claimReason.trim(),
      });
      setClaims((prev) => [claim, ...prev]);
      setShowClaim(false);
      setAmount("");
      setClaimReason("");
      Alert.alert("Claim submitted", "Community members will vote on your request.");
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to submit claim.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleVote = async (claimId: number, action: 'approve' | 'reject') => {
    try {
      const updated = await voteWelfareClaim(claimId, action);
      setClaims((prev) => prev.map((c) => (c.id === claimId ? updated : c)));
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Vote failed.");
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
  const monthly = fund ? Number(fund.monthly_contribution) : 0;

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader title={name ? `${name} — Welfare` : "Welfare Fund"} variant="light" leading="back" />

      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        contentContainerStyle={{ paddingBottom: 32 }}
      >
        {/* Fund balance card */}
        <View style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>Welfare Fund Balance</Text>
          <Text style={styles.balanceAmount}>KES {balance.toLocaleString()}</Text>
          {monthly > 0 && (
            <Text style={styles.balanceSub}>
              Recommended: KES {monthly.toLocaleString()} / member / month
            </Text>
          )}
          <Text style={styles.balanceDesc}>
            Community emergency fund — members vote on disbursements. Covers funerals, hospital bills, and urgent needs.
          </Text>
        </View>

        {/* Actions */}
        <View style={styles.actionsRow}>
          <TouchableOpacity style={styles.primaryBtn} onPress={() => setShowContribute(true)}>
            <Text style={styles.primaryBtnText}>+ Contribute</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryBtn} onPress={() => setShowClaim(true)}>
            <Text style={styles.secondaryBtnText}>Request Help</Text>
          </TouchableOpacity>
        </View>

        {/* Claims list */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Claims</Text>
          {claims.length === 0 ? (
            <View style={styles.emptyBox}>
              <Ionicons name="heart-outline" size={36} color={COLORS.textMuted} style={{ marginBottom: 12 }} />
              <Text style={styles.emptyTitle}>No claims yet</Text>
              <Text style={styles.emptyText}>When a member needs help, their request will appear here for the community to vote on.</Text>
            </View>
          ) : (
            claims.map((claim) => (
              <View key={claim.id} style={styles.claimCard}>
                <View style={styles.claimHeader}>
                  <Text style={styles.claimAmount}>KES {Number(claim.amount_requested).toLocaleString()}</Text>
                  <View style={[styles.statusBadge, statusColor(claim.status)]}>
                    <Text style={styles.statusText}>{claim.status}</Text>
                  </View>
                </View>
                <Text style={styles.claimReason}>{claim.reason}</Text>
                <Text style={styles.claimMeta}>
                  From {claim.claimant_phone} · {claim.approve_count} vote{claim.approve_count !== 1 ? 's' : ''} to approve
                </Text>

                {claim.status === 'PENDING' && (
                  <View style={styles.voteRow}>
                    <TouchableOpacity
                      style={[styles.voteBtn, styles.voteApprove]}
                      onPress={() => handleVote(claim.id, 'approve')}
                    >
                      <Text style={styles.voteBtnText}>Support</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.voteBtn, styles.voteReject]}
                      onPress={() => handleVote(claim.id, 'reject')}
                    >
                      <Text style={styles.voteBtnText}>Decline</Text>
                    </TouchableOpacity>
                  </View>
                )}

                {claim.status === 'DISBURSED' && claim.disbursed_at && (
                  <Text style={styles.disbursedNote}>
                    Paid out on {new Date(claim.disbursed_at).toLocaleDateString()}
                  </Text>
                )}
              </View>
            ))
          )}
        </View>
      </ScrollView>

      {/* Contribute Modal */}
      <Modal visible={showContribute} transparent animationType="slide">
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Contribute to Welfare Fund</Text>
            {monthly > 0 && (
              <Text style={styles.modalHint}>
                Recommended: KES {monthly.toLocaleString()} this month
              </Text>
            )}
            <Text style={styles.modalLabel}>Amount (KES)</Text>
            <TextInput
              value={amount}
              onChangeText={setAmount}
              placeholder={monthly > 0 ? `e.g. ${monthly}` : "e.g. 500"}
              placeholderTextColor={COLORS.textMuted}
              style={[styles.modalInput, { fontSize: FONTS.xl, textAlign: "center" }]}
              keyboardType="numeric"
              autoFocus
            />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowContribute(false); setAmount(""); }}>
                <Text style={styles.cancelBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleContribute} disabled={submitting}>
                {submitting ? <ActivityIndicator color={COLORS.white} /> : <Text style={styles.confirmBtnText}>Contribute</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Claim Modal */}
      <Modal visible={showClaim} transparent animationType="slide">
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Request Welfare Support</Text>
            <Text style={styles.modalHint}>
              Your community will vote to approve your request. Current fund balance: KES {balance.toLocaleString()}.
            </Text>
            <Text style={styles.modalLabel}>Amount needed (KES)</Text>
            <TextInput
              value={amount}
              onChangeText={setAmount}
              placeholder="e.g. 5000"
              placeholderTextColor={COLORS.textMuted}
              style={styles.modalInput}
              keyboardType="numeric"
            />
            <Text style={styles.modalLabel}>Reason</Text>
            <TextInput
              value={claimReason}
              onChangeText={setClaimReason}
              placeholder="e.g. Hospital bill for my child, school fees emergency..."
              placeholderTextColor={COLORS.textMuted}
              style={[styles.modalInput, { height: 90, textAlignVertical: "top" }]}
              multiline
            />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowClaim(false); setAmount(""); setClaimReason(""); }}>
                <Text style={styles.cancelBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleSubmitClaim} disabled={submitting}>
                {submitting ? <ActivityIndicator color={COLORS.white} /> : <Text style={styles.confirmBtnText}>Submit</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

function statusColor(s: string) {
  switch (s) {
    case 'APPROVED':  return { backgroundColor: '#e6f4ea' };
    case 'DISBURSED': return { backgroundColor: '#e6f4ea' };
    case 'REJECTED':  return { backgroundColor: '#fce8e6' };
    default:          return { backgroundColor: '#fef7e0' };
  }
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  balanceCard: {
    backgroundColor: COLORS.primary,
    margin: 16, padding: 24, borderRadius: RADIUS.lg,
  },
  balanceLabel: { fontSize: FONTS.sm, color: "rgba(255,255,255,0.75)", marginBottom: 4, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.5 },
  balanceAmount: { fontSize: 36, fontWeight: "bold", color: COLORS.white, marginBottom: 4 },
  balanceSub: { fontSize: FONTS.sm, color: "rgba(255,255,255,0.8)", marginBottom: 12 },
  balanceDesc: { fontSize: FONTS.sm, color: "rgba(255,255,255,0.75)", lineHeight: 18 },

  actionsRow: { flexDirection: "row", gap: 12, paddingHorizontal: 16, marginBottom: 8 },
  primaryBtn: { flex: 1, paddingVertical: 14, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: "center" },
  primaryBtnText: { color: COLORS.white, fontWeight: "bold" },
  secondaryBtn: { flex: 1, paddingVertical: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.white, alignItems: "center" },
  secondaryBtnText: { color: COLORS.textSecondary, fontWeight: "600" },

  section: { paddingHorizontal: 16, paddingTop: 8 },
  sectionTitle: { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 12 },

  emptyBox: { backgroundColor: COLORS.white, padding: 24, borderRadius: RADIUS.lg, alignItems: "center" },
  emptyTitle: { fontSize: FONTS.md, fontWeight: "bold", color: COLORS.text, marginBottom: 6 },
  emptyText: { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  claimCard: { backgroundColor: COLORS.white, padding: 16, borderRadius: RADIUS.lg, marginBottom: 12, borderWidth: 1, borderColor: COLORS.border },
  claimHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  claimAmount: { fontSize: FONTS.lg, fontWeight: "bold", color: COLORS.text },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  statusText: { fontSize: 11, fontWeight: "700", color: COLORS.text },
  claimReason: { fontSize: FONTS.md, color: COLORS.textSecondary, marginBottom: 6, lineHeight: 20 },
  claimMeta: { fontSize: FONTS.sm, color: COLORS.textMuted },
  disbursedNote: { fontSize: FONTS.sm, color: COLORS.success, marginTop: 6, fontWeight: "600" },

  voteRow: { flexDirection: "row", gap: 8, marginTop: 12 },
  voteBtn: { flex: 1, paddingVertical: 10, borderRadius: RADIUS.md, alignItems: "center" },
  voteApprove: { backgroundColor: COLORS.success },
  voteReject: { backgroundColor: COLORS.error || "#dc2626" },
  voteBtnText: { color: COLORS.white, fontWeight: "bold" },

  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modal: { backgroundColor: COLORS.white, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40 },
  modalTitle: { fontSize: FONTS.xl, fontWeight: "bold", color: COLORS.text, marginBottom: 8 },
  modalHint: { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 12, lineHeight: 18 },
  modalLabel: { fontSize: FONTS.sm, color: COLORS.textSecondary, marginBottom: 6, marginTop: 8 },
  modalInput: { borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md, padding: 14, fontSize: FONTS.md, color: COLORS.text, backgroundColor: COLORS.background, marginBottom: 4 },
  modalActions: { flexDirection: "row", gap: 12, marginTop: 16 },
  cancelBtn: { flex: 1, paddingVertical: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, alignItems: "center" },
  cancelBtnText: { color: COLORS.textSecondary, fontWeight: "600" },
  confirmBtn: { flex: 1, paddingVertical: 14, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: "center" },
  confirmBtnText: { color: COLORS.white, fontWeight: "bold" },
});
