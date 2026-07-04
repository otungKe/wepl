/**
 * Payment Methods — a scalable "wallet" of linked payout/collection rails.
 * M-Pesa is live today; Card and Bank account have their UIs in place so the
 * screen doesn't need reshaping when those rails are wired (the backend already
 * models all three; card/bank linking returns "coming soon").
 */
import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator,
  Modal, Pressable, TextInput, Alert, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getProfile } from "../api/auth";
import {
  getPaymentMethods, linkMpesa, setDefaultPaymentMethod, removePaymentMethod,
  type PaymentMethod, type PaymentKind,
} from "../api/paymentMethods";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

const KIND_META: Record<PaymentKind, { icon: string; color: string; label: string; sub: string }> = {
  mpesa: { icon: "phone-portrait-outline", color: COLORS.primary, label: "M-Pesa",              sub: "Pay and get paid with your Safaricom line" },
  card:  { icon: "card-outline",           color: "#2563EB",       label: "Debit or credit card", sub: "Visa or Mastercard" },
  bank:  { icon: "business-outline",       color: COLORS.accent,   label: "Bank account",         sub: "Direct bank transfer" },
};

export default function PaymentMethodsScreen() {
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(true);

  const [picker, setPicker] = useState(false);
  const [addKind, setAddKind] = useState<PaymentKind | null>(null);

  const load = useCallback(() => {
    getPaymentMethods().then(setMethods).catch(() => {});
  }, []);

  useFocusEffect(useCallback(() => {
    Promise.all([
      getPaymentMethods().then(setMethods).catch(() => {}),
      getProfile().then(p => setPhone(p?.phone_number ?? "")).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []));

  const onManage = (m: PaymentMethod) => {
    const actions: any[] = [];
    if (!m.is_default) {
      actions.push({ text: "Set as default", onPress: async () => { await setDefaultPaymentMethod(m.id); load(); } });
    }
    actions.push({
      text: "Remove", style: "destructive",
      onPress: () => Alert.alert("Remove method", `Unlink ${m.display}?`, [
        { text: "Cancel", style: "cancel" },
        { text: "Remove", style: "destructive", onPress: async () => { await removePaymentMethod(m.id); load(); } },
      ]),
    });
    actions.push({ text: "Cancel", style: "cancel" });
    Alert.alert(m.kind_label, m.display, actions);
  };

  const openAdd = (kind: PaymentKind) => { setPicker(false); setTimeout(() => setAddKind(kind), 250); };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Payment Methods" variant="light" leading="back" onBack={() => router.back()} />
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader title="Payment Methods" variant="light" leading="back" onBack={() => router.back()} />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <Text style={s.sectionLabel}>LINKED METHODS</Text>
        {methods.length === 0 ? (
          <View style={s.emptyCard}>
            <Ionicons name="wallet-outline" size={22} color={COLORS.textMuted} />
            <Text style={s.emptyText}>
              No methods linked yet. Add your M-Pesa number so money can move to and from your account.
            </Text>
          </View>
        ) : (
          <View style={s.card}>
            {methods.map((m, i) => {
              const meta = KIND_META[m.kind];
              return (
                <TouchableOpacity
                  key={m.id}
                  style={[s.row, i === methods.length - 1 && { borderBottomWidth: 0 }]}
                  onPress={() => onManage(m)}
                  activeOpacity={0.7}
                >
                  <View style={[s.rowIcon, { backgroundColor: meta.color + "18" }]}>
                    <Ionicons name={meta.icon as any} size={20} color={meta.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={s.rowTitleLine}>
                      <Text style={s.rowTitle}>{m.label || meta.label}</Text>
                      {m.is_default && (
                        <View style={s.defaultChip}><Text style={s.defaultChipText}>Default</Text></View>
                      )}
                    </View>
                    <Text style={s.rowSub}>{m.display}</Text>
                  </View>
                  <Ionicons name="ellipsis-horizontal" size={18} color={COLORS.textMuted} />
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        <TouchableOpacity style={s.addBtn} onPress={() => setPicker(true)}>
          <Ionicons name="add-circle-outline" size={20} color={COLORS.primary} />
          <Text style={s.addBtnText}>Add payment method</Text>
        </TouchableOpacity>

        <View style={s.note}>
          <Ionicons name="lock-closed-outline" size={15} color={COLORS.textMuted} />
          <Text style={s.noteText}>
            Your details are encrypted. WEPL never stores full card numbers — only the last four digits.
          </Text>
        </View>
      </ScrollView>

      {/* Type picker */}
      <Modal visible={picker} transparent animationType="slide" onRequestClose={() => setPicker(false)}>
        <Pressable style={s.backdrop} onPress={() => setPicker(false)}>
          <Pressable style={s.sheet} onStartShouldSetResponder={() => true}>
            <View style={s.handle} />
            <Text style={s.sheetTitle}>Add a payment method</Text>
            {(["mpesa", "card", "bank"] as PaymentKind[]).map(kind => {
              const meta = KIND_META[kind];
              const soon = kind !== "mpesa";
              return (
                <TouchableOpacity key={kind} style={s.typeRow} onPress={() => openAdd(kind)} activeOpacity={0.7}>
                  <View style={[s.rowIcon, { backgroundColor: meta.color + "18" }]}>
                    <Ionicons name={meta.icon as any} size={20} color={meta.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={s.rowTitleLine}>
                      <Text style={s.rowTitle}>{meta.label}</Text>
                      {soon && <View style={s.soonChip}><Text style={s.soonChipText}>Coming soon</Text></View>}
                    </View>
                    <Text style={s.rowSub}>{meta.sub}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                </TouchableOpacity>
              );
            })}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Add form (M-Pesa live; card/bank scaffolded) */}
      <AddSheet
        kind={addKind}
        defaultPhone={phone}
        onClose={() => setAddKind(null)}
        onLinked={() => { setAddKind(null); load(); }}
      />
    </SafeAreaView>
  );
}

// ─── Add sheet — one component, three rails ──────────────────────────────────

function AddSheet({
  kind, defaultPhone, onClose, onLinked,
}: {
  kind: PaymentKind | null;
  defaultPhone: string;
  onClose: () => void;
  onLinked: () => void;
}) {
  const [mpesa, setMpesa] = useState("");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);

  const meta = kind ? KIND_META[kind] : null;
  const isMpesa = kind === "mpesa";

  const submitMpesa = async () => {
    const num = (mpesa || defaultPhone).trim();
    if (!num) { Alert.alert("Number required", "Enter the M-Pesa number to link."); return; }
    setSaving(true);
    try {
      await linkMpesa(num, { label: label.trim() || undefined });
      setMpesa(""); setLabel("");
      onLinked();
    } catch (e: any) {
      Alert.alert("Could not link", e?.response?.data?.error || "Please check the number and try again.");
    } finally { setSaving(false); }
  };

  return (
    <Modal visible={!!kind} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <Pressable style={s.backdrop} onPress={onClose}>
          <Pressable style={s.sheet} onStartShouldSetResponder={() => true}>
            <View style={s.handle} />
            {meta && (
              <View style={s.sheetHead}>
                <View style={[s.rowIcon, { backgroundColor: meta.color + "18" }]}>
                  <Ionicons name={meta.icon as any} size={20} color={meta.color} />
                </View>
                <Text style={s.sheetTitle}>Link {meta.label}</Text>
              </View>
            )}

            {isMpesa ? (
              <>
                <Text style={s.fieldLabel}>M-Pesa number</Text>
                <TextInput
                  value={mpesa}
                  onChangeText={setMpesa}
                  placeholder={defaultPhone || "0712 345 678"}
                  placeholderTextColor={COLORS.textMuted}
                  keyboardType="phone-pad"
                  style={s.input}
                  autoFocus
                />
                <Text style={s.fieldLabel}>Label (optional)</Text>
                <TextInput
                  value={label}
                  onChangeText={setLabel}
                  placeholder="e.g. My Safaricom line"
                  placeholderTextColor={COLORS.textMuted}
                  style={s.input}
                />
                <TouchableOpacity style={[s.primaryBtn, saving && { opacity: 0.6 }]} onPress={submitMpesa} disabled={saving}>
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryBtnText}>Link M-Pesa</Text>}
                </TouchableOpacity>
              </>
            ) : (
              // Card / Bank — UI is present and shaped; linking is not enabled yet.
              <>
                {kind === "card" ? (
                  <>
                    <Text style={s.fieldLabel}>Card number</Text>
                    <View style={s.inputFake}><Text style={s.inputFakeText}>•••• •••• •••• ••••</Text></View>
                    <View style={{ flexDirection: "row", gap: 12 }}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.fieldLabel}>Expiry</Text>
                        <View style={s.inputFake}><Text style={s.inputFakeText}>MM / YY</Text></View>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={s.fieldLabel}>CVC</Text>
                        <View style={s.inputFake}><Text style={s.inputFakeText}>•••</Text></View>
                      </View>
                    </View>
                  </>
                ) : (
                  <>
                    <Text style={s.fieldLabel}>Bank</Text>
                    <View style={s.inputFake}><Text style={s.inputFakeText}>Select your bank</Text></View>
                    <Text style={s.fieldLabel}>Account number</Text>
                    <View style={s.inputFake}><Text style={s.inputFakeText}>••••••••••</Text></View>
                  </>
                )}

                <View style={s.soonBanner}>
                  <Ionicons name="time-outline" size={16} color={COLORS.accent} />
                  <Text style={s.soonBannerText}>
                    {meta?.label} linking is coming soon. Right now, WEPL moves money over M-Pesa —
                    we&apos;ll let you know the moment this is available.
                  </Text>
                </View>
                <TouchableOpacity style={[s.primaryBtn, { backgroundColor: COLORS.textMuted }]} disabled>
                  <Text style={s.primaryBtnText}>Coming soon</Text>
                </TouchableOpacity>
              </>
            )}
          </Pressable>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  scroll: { padding: 16, paddingBottom: 48 },

  sectionLabel: {
    fontSize: 11, fontWeight: "700", color: COLORS.textMuted,
    letterSpacing: 0.6, marginTop: 8, marginBottom: 8, marginLeft: 4,
  },
  card: { backgroundColor: COLORS.white, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: COLORS.divider },
  rowIcon: { width: 40, height: 40, borderRadius: 11, justifyContent: "center", alignItems: "center" },
  rowTitleLine: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowTitle: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  rowSub: { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 2 },

  defaultChip: { backgroundColor: COLORS.primaryPale, paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full },
  defaultChipText: { fontSize: 11, fontWeight: "700", color: COLORS.primary },
  soonChip: { backgroundColor: COLORS.accent + "1F", paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full },
  soonChipText: { fontSize: 11, fontWeight: "700", color: COLORS.accent },

  emptyCard: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg, padding: 16,
    borderWidth: 1, borderColor: COLORS.border,
  },
  emptyText: { flex: 1, fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 20 },

  addBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    marginTop: 14, paddingVertical: 14, borderRadius: RADIUS.md,
    borderWidth: 1.5, borderColor: COLORS.primary, borderStyle: "dashed",
  },
  addBtnText: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.primary },

  note: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 20, paddingHorizontal: 4 },
  noteText: { flex: 1, fontSize: FONTS.xs, color: COLORS.textMuted, lineHeight: 18 },

  // Sheets
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: COLORS.white, borderTopLeftRadius: 22, borderTopRightRadius: 22,
    padding: 20, paddingBottom: Platform.OS === "ios" ? 34 : 22, gap: 4,
  },
  handle: { width: 40, height: 4, backgroundColor: COLORS.border, borderRadius: 2, alignSelf: "center", marginBottom: 14 },
  sheetHead: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 8 },
  sheetTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginBottom: 8 },

  typeRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 },

  fieldLabel: { fontSize: FONTS.sm, color: COLORS.textSecondary, fontWeight: "600", marginBottom: 6, marginTop: 8 },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 12, fontSize: FONTS.md, color: COLORS.text, backgroundColor: COLORS.background,
  },
  inputFake: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, backgroundColor: COLORS.background,
  },
  inputFakeText: { fontSize: FONTS.md, color: COLORS.textMuted, letterSpacing: 1 },

  soonBanner: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    backgroundColor: COLORS.accent + "12", borderRadius: RADIUS.md, padding: 12, marginTop: 16,
  },
  soonBannerText: { flex: 1, fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 19 },

  primaryBtn: {
    backgroundColor: COLORS.primary, borderRadius: RADIUS.md,
    paddingVertical: 14, alignItems: "center", marginTop: 18,
  },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: FONTS.md },
});
