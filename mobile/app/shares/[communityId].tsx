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
import { getCommunitySharesFund, SharesFund, ShareHolding } from "../../api/contributions";
import { initiateSTKPush, checkSTKStatus } from "../../api/mpesa";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import Avatar from "../../components/app/Avatar";

export default function SharesScreen() {
  const { communityId, name } = useLocalSearchParams<{ communityId: string; name?: string }>();
  const cId = Number(communityId);

  const [fund, setFund]         = useState<SharesFund | null>(null);
  const [myPhone, setMyPhone]   = useState("");
  const [loading, setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [showAdd, setShowAdd]   = useState(false);
  const [amount, setAmount]     = useState("");
  const [phone, setPhone]       = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling]   = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [f, phone] = await Promise.all([
        getCommunitySharesFund(cId),
        storage.getItem("phone"),
      ]);
      setFund(f);
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

  const handleAdd = async () => {
    if (!amount || Number(amount) <= 0) { Alert.alert("Required", "Enter a valid amount."); return; }
    setSubmitting(true);
    try {
      const mpesaPhone = phone.trim() || myPhone;
      const result = await initiateSTKPush({
        payment_type: 'shares',
        community_id: cId,
        amount: Number(amount),
        phone_number: mpesaPhone,
      });
      setShowAdd(false);
      setAmount(""); setPhone("");
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

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title="Shares Fund" variant="light" leading="back" />
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  if (!fund) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title={name ? `${name} — Shares` : "Shares Fund"} variant="light" leading="back" />
        <View style={styles.center}>
          <Ionicons name="bar-chart-outline" size={48} color={COLORS.textMuted} />
          <Text style={styles.emptyTitle}>No shares fund found</Text>
        </View>
      </SafeAreaView>
    );
  }

  const myHolding: ShareHolding | undefined = fund.holdings.find((h) => h.phone_number === myPhone);
  const totalPool = Number(fund.total_pool);

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader
        title={name ? `${name} — Shares` : "Shares Fund"}
        variant="light"
        leading="back"
      />

      <FlatList
        data={fund.holdings}
        keyExtractor={(h) => String(h.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        contentContainerStyle={{ paddingBottom: 40 }}
        ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: COLORS.divider, marginLeft: 66 }} />}
        ListHeaderComponent={
          <>
            {/* My holdings hero */}
            <View style={styles.hero}>
              <Text style={styles.heroLabel}>MY SHAREHOLDING</Text>
              {myHolding ? (
                <>
                  <Text style={styles.heroShares}>{myHolding.shares_count} shares</Text>
                  <Text style={styles.heroContrib}>KES {Number(myHolding.total_contributed).toLocaleString()} contributed</Text>
                  <View style={styles.ownershipPill}>
                    <Text style={styles.ownershipPillText}>{myHolding.ownership_pct}% ownership</Text>
                  </View>
                </>
              ) : (
                <Text style={styles.noHolding}>You have no shares yet</Text>
              )}
              <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
                <Ionicons name="add-circle-outline" size={18} color={COLORS.white} />
                <Text style={styles.addBtnText}>Add to My Shares</Text>
              </TouchableOpacity>
            </View>

            {/* Fund stats */}
            <View style={styles.statsRow}>
              <View style={styles.stat}>
                <Text style={styles.statVal}>KES {totalPool.toLocaleString()}</Text>
                <Text style={styles.statLabel}>Total Pool</Text>
              </View>
              <View style={styles.statDivider} />
              <View style={styles.stat}>
                <Text style={styles.statVal}>KES {Number(fund.share_price).toLocaleString()}</Text>
                <Text style={styles.statLabel}>Share Price</Text>
              </View>
              <View style={styles.statDivider} />
              <View style={styles.stat}>
                <Text style={styles.statVal}>{Number(fund.total_shares).toLocaleString()}</Text>
                <Text style={styles.statLabel}>Total Shares</Text>
              </View>
            </View>

            {/* Section header */}
            <View style={styles.sectionHead}>
              <Text style={styles.sectionLabel}>MEMBER HOLDINGS</Text>
              <Text style={styles.sectionCount}>{fund.holdings.length}</Text>
            </View>
          </>
        }
        renderItem={({ item: h }) => {
          const isMe = h.phone_number === myPhone;
          return (
            <View style={[styles.holdingRow, isMe && styles.holdingRowMe]}>
              <Avatar name={h.name || h.phone_number} size={40} />
              <View style={styles.holdingInfo}>
                <Text style={styles.holdingName}>
                  {h.name || h.phone_number}{isMe ? " (you)" : ""}
                </Text>
                <Text style={styles.holdingSub}>
                  {Number(h.shares_count).toLocaleString()} shares · KES {Number(h.total_contributed).toLocaleString()}
                </Text>
              </View>
              <View style={styles.ownershipBadge}>
                <Text style={styles.ownershipText}>{h.ownership_pct}%</Text>
              </View>
            </View>
          );
        }}
        ListEmptyComponent={
          <View style={styles.emptyBox}>
            <Ionicons name="bar-chart-outline" size={52} color={COLORS.textMuted} />
            <Text style={styles.emptyTitle}>No holdings yet</Text>
            <Text style={styles.emptySub}>
              Be the first to add shares to this fund.
            </Text>
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

      {/* Add shares modal */}
      <Modal visible={showAdd} transparent animationType="slide">
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <View style={styles.overlay}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Add to My Shares</Text>
            <Text style={styles.sheetHint}>
              Each share costs KES {Number(fund.share_price).toLocaleString()}.
              {amount && Number(amount) > 0
                ? ` KES ${Number(amount).toLocaleString()} ≈ ${(Number(amount) / Number(fund.share_price)).toFixed(4)} shares.`
                : " An M-Pesa STK push will be sent to your phone."}
            </Text>
            <Text style={styles.fieldLabel}>Amount (KES)</Text>
            <TextInput
              value={amount}
              onChangeText={setAmount}
              placeholder={`e.g. ${Number(fund.share_price).toLocaleString()}`}
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              keyboardType="numeric"
              autoFocus
            />
            <Text style={styles.fieldLabel}>M-Pesa Phone (optional)</Text>
            <TextInput
              value={phone}
              onChangeText={setPhone}
              placeholder="07XX XXX XXX — leave blank to use yours"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              keyboardType="phone-pad"
            />
            <View style={styles.sheetActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowAdd(false); setAmount(""); setPhone(""); }}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleAdd} disabled={submitting}>
                {submitting
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={styles.confirmText}>Pay via M-Pesa</Text>}
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
  center: { flex: 1, justifyContent: "center", alignItems: "center", gap: 12 },

  hero: {
    backgroundColor: COLORS.primary,
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 32,
    alignItems: "center",
  },
  heroLabel:    { fontSize: 11, fontWeight: "700", color: "rgba(255,255,255,0.7)", letterSpacing: 1, marginBottom: 10 },
  heroShares:   { fontSize: 42, fontWeight: "800", color: COLORS.white, marginBottom: 4 },
  heroContrib:  { fontSize: FONTS.md, color: "rgba(255,255,255,0.85)", marginBottom: 12 },
  ownershipPill: {
    paddingHorizontal: 16, paddingVertical: 6,
    backgroundColor: "rgba(255,255,255,0.2)",
    borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.4)",
    marginBottom: 20,
  },
  ownershipPillText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
  noHolding: { fontSize: FONTS.lg, color: "rgba(255,255,255,0.75)", marginBottom: 20, marginTop: 8 },
  addBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 20, paddingVertical: 11,
    backgroundColor: "rgba(255,255,255,0.2)",
    borderRadius: RADIUS.full,
    borderWidth: 1.5, borderColor: "rgba(255,255,255,0.5)",
  },
  addBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },

  statsRow: {
    flexDirection: "row",
    backgroundColor: COLORS.white,
    marginHorizontal: 16, marginTop: 16,
    borderRadius: RADIUS.lg,
    padding: 16,
    borderWidth: 1, borderColor: COLORS.border,
  },
  stat:      { flex: 1, alignItems: "center" },
  statVal:   { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  statLabel: { fontSize: 11, color: COLORS.textMuted, marginTop: 3 },
  statDivider: { width: 1, backgroundColor: COLORS.border, marginHorizontal: 8 },

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

  holdingRow: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 13, paddingHorizontal: 16,
    backgroundColor: COLORS.white, gap: 12,
  },
  holdingRowMe: { backgroundColor: COLORS.primaryBg },
  holdingInfo: { flex: 1 },
  holdingName: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  holdingSub:  { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 2 },
  ownershipBadge: {
    paddingHorizontal: 10, paddingVertical: 5,
    backgroundColor: COLORS.primaryPale, borderRadius: RADIUS.full,
  },
  ownershipText: { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.primary },

  emptyBox:   { alignItems: "center", paddingTop: 48, paddingHorizontal: 32, gap: 12 },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

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
    marginBottom: 6, marginTop: 12, textTransform: "uppercase", letterSpacing: 0.4,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background,
  },
  sheetActions: { flexDirection: "row", gap: 12, marginTop: 20 },
  cancelBtn:  { flex: 1, padding: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, alignItems: "center" },
  cancelText: { color: COLORS.textSecondary, fontWeight: "600" },
  confirmBtn: { flex: 1, padding: 14, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: "center" },
  confirmText: { color: COLORS.white, fontWeight: "700" },
});
