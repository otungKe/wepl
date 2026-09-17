import { useState, useEffect, useCallback } from "react";
import {
  View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Alert,
  ScrollView, Modal, TextInput, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  getPoolActions, approvePoolAction, rejectPoolAction, cancelPoolAction,
  requestPoolExpense, requestDistribution, recordExternalIncome, PoolActionRequest,
} from "../../api/contributions";
import { getProfile } from "../../api/auth";
import { COLORS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";

type Sheet = null | "income" | "expense" | "distribute";

const STATUS_STYLE: Record<string, { bg: string; fg: string }> = {
  PENDING:   { bg: "#FDF6E3", fg: COLORS.warning },
  EXECUTED:  { bg: COLORS.primaryPale, fg: COLORS.primary },
  REJECTED:  { bg: "#F4E8E8", fg: COLORS.error },
  CANCELLED: { bg: "#EEF1EF", fg: COLORS.textMuted },
};

const apiErr = (e: any) =>
  e?.response?.data?.detail || e?.response?.data?.amount?.[0] || "Action failed.";

export default function ManagePoolScreen() {
  const params = useLocalSearchParams<{ id: string; title?: string }>();
  const contributionId = Number(params.id);

  const [actions, setActions]     = useState<PoolActionRequest[]>([]);
  const [myId, setMyId]           = useState<number | null>(null);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefresh]  = useState(false);
  const [sheet, setSheet]         = useState<Sheet>(null);
  const [amount, setAmount]       = useState("");
  const [note, setNote]           = useState("");
  const [apportion, setApportion] = useState<"pro_rata" | "per_capita">("pro_rata");
  const [submitting, setSubmit]   = useState(false);

  const load = useCallback(async () => {
    try {
      const [acts, profile] = await Promise.all([getPoolActions(contributionId), getProfile()]);
      setActions(acts);
      setMyId(profile.id);
    } catch {
      Alert.alert("Error", "Could not load pool activity.");
    } finally {
      setLoading(false);
      setRefresh(false);
    }
  }, [contributionId]);

  useEffect(() => { load(); }, [load]);

  const openSheet = (s: Sheet) => {
    setSheet(s); setAmount(""); setNote(""); setApportion("pro_rata");
  };

  const submit = async () => {
    const amt = amount.trim();
    if (!amt) return;
    setSubmit(true);
    try {
      if (sheet === "income") {
        await recordExternalIncome(contributionId, { amount: amt, source: note });
      } else if (sheet === "expense") {
        await requestPoolExpense(contributionId, { amount: amt, apportion, reason: note });
      } else if (sheet === "distribute") {
        await requestDistribution(contributionId, { amount: amt, apportion, reason: note });
      }
      const wasIncome = sheet === "income";
      setSheet(null);
      Alert.alert("Done", wasIncome ? "Income recorded." : "Proposed — a second admin must approve.");
      load();
    } catch (e: any) {
      Alert.alert("Error", apiErr(e));
    } finally {
      setSubmit(false);
    }
  };

  const run = (p: Promise<unknown>) =>
    p.then(() => load()).catch((e: any) => Alert.alert("Error", apiErr(e)));

  const confirmReject = (id: number) =>
    Alert.alert("Reject request?", "The proposal will be declined.", [
      { text: "Cancel", style: "cancel" },
      { text: "Reject", style: "destructive", onPress: () => run(rejectPoolAction(id)) },
    ]);

  const confirmCancel = (id: number) =>
    Alert.alert("Withdraw request?", "You can propose again later.", [
      { text: "Keep", style: "cancel" },
      { text: "Withdraw", style: "destructive", onPress: () => run(cancelPoolAction(id)) },
    ]);

  const sheetTitle =
    sheet === "income" ? "Record income" :
    sheet === "expense" ? "Propose expense" :
    sheet === "distribute" ? "Propose distribution" : "";

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <AppHeader title="Manage Pool" leading="back" />
      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={COLORS.primary} />
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefresh(true); load(); }} />}
        >
          {!!params.title && <Text style={styles.sub}>{params.title}</Text>}

          {/* Admin actions */}
          <View style={styles.actions}>
            <ActionCard icon="arrow-down-circle" label="Record income"
              hint="Business / external proceeds into the pool" onPress={() => openSheet("income")} />
            <ActionCard icon="cart" label="Propose expense"
              hint="Spend pool funds — needs a 2nd admin" onPress={() => openSheet("expense")} />
            <ActionCard icon="git-branch" label="Propose distribution"
              hint="Share out retained surplus — needs a 2nd admin" onPress={() => openSheet("distribute")} />
          </View>

          <Text style={styles.section}>Collective-fund activity</Text>
          {actions.length === 0 ? (
            <Text style={styles.empty}>No pool actions yet.</Text>
          ) : actions.map((a) => {
            const st = STATUS_STYLE[a.status] ?? STATUS_STYLE.CANCELLED;
            const isMine = myId != null && a.requested_by === myId;
            const pending = a.status === "PENDING";
            return (
              <View key={a.id} style={styles.card}>
                <View style={styles.cardTop}>
                  <Text style={styles.cardTitle}>
                    {a.action === "EXPENSE" ? "Pool expense" : "Surplus distribution"}
                  </Text>
                  <View style={[styles.badge, { backgroundColor: st.bg }]}>
                    <Text style={[styles.badgeText, { color: st.fg }]}>{a.status}</Text>
                  </View>
                </View>
                <Text style={styles.amount}>KES {Number(a.amount).toLocaleString()}</Text>
                <Text style={styles.meta}>
                  {a.apportion === "pro_rata" ? "Pro-rata" : "Per-capita"} · by {a.requested_by_name}
                  {pending ? ` · ${a.approval_count} approval(s)` : ""}
                </Text>
                {!!a.memo && <Text style={styles.memo}>{a.memo}</Text>}
                {!!a.decision_note && <Text style={styles.memo}>Note: {a.decision_note}</Text>}

                {pending && (
                  <View style={styles.row}>
                    {isMine ? (
                      <TouchableOpacity style={[styles.btn, styles.btnGhost]} onPress={() => confirmCancel(a.id)}>
                        <Text style={styles.btnGhostText}>Withdraw</Text>
                      </TouchableOpacity>
                    ) : (
                      <>
                        <TouchableOpacity style={[styles.btn, styles.btnApprove]} onPress={() => run(approvePoolAction(a.id))}>
                          <Ionicons name="checkmark" size={16} color="#fff" />
                          <Text style={styles.btnApproveText}>Approve</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={[styles.btn, styles.btnReject]} onPress={() => confirmReject(a.id)}>
                          <Text style={styles.btnRejectText}>Reject</Text>
                        </TouchableOpacity>
                      </>
                    )}
                  </View>
                )}
              </View>
            );
          })}
        </ScrollView>
      )}

      {/* Action sheet */}
      <Modal visible={sheet !== null} transparent animationType="slide" onRequestClose={() => setSheet(null)}>
        <View style={styles.sheetWrap}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>{sheetTitle}</Text>
            <TextInput
              style={styles.input} placeholder="Amount (KES)" keyboardType="numeric"
              value={amount} onChangeText={setAmount} placeholderTextColor={COLORS.textMuted}
            />
            {sheet !== "income" && (
              <View style={styles.toggle}>
                {(["pro_rata", "per_capita"] as const).map((m) => (
                  <TouchableOpacity key={m}
                    style={[styles.toggleBtn, apportion === m && styles.toggleBtnActive]}
                    onPress={() => setApportion(m)}>
                    <Text style={[styles.toggleText, apportion === m && styles.toggleTextActive]}>
                      {m === "pro_rata" ? "Pro-rata" : "Per-capita"}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
            <TextInput
              style={styles.input}
              placeholder={sheet === "income" ? "Source (optional)" : "Reason (optional)"}
              value={note} onChangeText={setNote} placeholderTextColor={COLORS.textMuted}
            />
            <View style={styles.row}>
              <TouchableOpacity style={[styles.btn, styles.btnGhost]} onPress={() => setSheet(null)}>
                <Text style={styles.btnGhostText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.btn, styles.btnPrimary]} onPress={submit} disabled={submitting || !amount.trim()}>
                <Text style={styles.btnPrimaryText}>{submitting ? "…" : sheet === "income" ? "Record" : "Propose"}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function ActionCard({ icon, label, hint, onPress }: {
  icon: any; label: string; hint: string; onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.actionCard} onPress={onPress}>
      <View style={styles.actionIcon}><Ionicons name={icon} size={20} color={COLORS.primary} /></View>
      <View style={{ flex: 1 }}>
        <Text style={styles.actionLabel}>{label}</Text>
        <Text style={styles.actionHint}>{hint}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.primaryBg },
  sub: { fontWeight: "500", color: COLORS.textSecondary, marginBottom: 14, fontSize: 14 },
  actions: { gap: 10, marginBottom: 24 },
  actionCard: {
    flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: COLORS.surface,
    borderRadius: RADIUS.lg, padding: 14, borderWidth: 1, borderColor: COLORS.border,
  },
  actionIcon: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: COLORS.primaryPale,
    alignItems: "center", justifyContent: "center",
  },
  actionLabel: { fontWeight: "600", color: COLORS.text, fontSize: 15 },
  actionHint: { fontWeight: "400", color: COLORS.textMuted, fontSize: 12, marginTop: 2 },
  section: { fontWeight: "600", color: COLORS.text, fontSize: 15, marginBottom: 10 },
  empty: { fontWeight: "400", color: COLORS.textMuted, fontSize: 14, paddingVertical: 8 },
  card: {
    backgroundColor: COLORS.surface, borderRadius: RADIUS.lg, padding: 14,
    borderWidth: 1, borderColor: COLORS.border, marginBottom: 10,
  },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  cardTitle: { fontWeight: "600", color: COLORS.text, fontSize: 14 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  badgeText: { fontWeight: "600", fontSize: 10, letterSpacing: 0.4 },
  amount: { fontWeight: "700", color: COLORS.text, fontSize: 20, marginTop: 6 },
  meta: { fontWeight: "400", color: COLORS.textSecondary, fontSize: 12, marginTop: 2 },
  memo: { fontWeight: "400", color: COLORS.textMuted, fontSize: 12, marginTop: 4 },
  row: { flexDirection: "row", gap: 10, marginTop: 12 },
  btn: {
    flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 44, borderRadius: RADIUS.md,
  },
  btnApprove: { backgroundColor: COLORS.primary },
  btnApproveText: { fontWeight: "600", color: "#fff", fontSize: 14 },
  btnReject: { backgroundColor: "#F4E8E8" },
  btnRejectText: { fontWeight: "600", color: COLORS.error, fontSize: 14 },
  btnGhost: { backgroundColor: "#EEF1EF" },
  btnGhostText: { fontWeight: "600", color: COLORS.textSecondary, fontSize: 14 },
  btnPrimary: { backgroundColor: COLORS.primary },
  btnPrimaryText: { fontWeight: "600", color: "#fff", fontSize: 14 },
  sheetWrap: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.35)" },
  sheet: { backgroundColor: COLORS.surface, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 20, gap: 12 },
  sheetTitle: { fontWeight: "700", color: COLORS.text, fontSize: 17 },
  input: {
    borderWidth: 1, borderColor: COLORS.border, borderRadius: RADIUS.md, paddingHorizontal: 14,
    height: 48, fontWeight: "400", color: COLORS.text, fontSize: 15,
  },
  toggle: { flexDirection: "row", gap: 8 },
  toggleBtn: {
    flex: 1, height: 40, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.border,
    alignItems: "center", justifyContent: "center",
  },
  toggleBtnActive: { backgroundColor: COLORS.primaryPale, borderColor: COLORS.primary },
  toggleText: { fontWeight: "500", color: COLORS.textSecondary, fontSize: 13 },
  toggleTextActive: { color: COLORS.primary },
});
