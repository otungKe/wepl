import { useState, useEffect } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert, ScrollView, KeyboardAvoidingView, Platform, Switch, Modal,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  createContribution, TenureType, Frequency, AmountType, VotingThreshold,
} from "../../api/contributions";
import { getMyCommunities, getCommunityMembers, Community, CommunityMember } from "../../api/communities";
import DateTimePicker from "@react-native-community/datetimepicker";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import Avatar from "../../components/app/Avatar";

const TOTAL_STEPS = 5;
const DRAFT_KEY   = "wepl_contribution_draft";

const MONTHS = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];

/** Pure-JS calendar modal — no native modules, works in Expo Go. */
function CalendarPicker({
  visible, value, onConfirm, onClose,
}: {
  visible: boolean;
  value: string | null;             // YYYY-MM-DD or null
  onConfirm: (date: string) => void;
  onClose: () => void;
}) {
  const today    = new Date();
  const initDate = value ? new Date(value) : new Date(today.getFullYear(), today.getMonth() + 1, 1);
  const [year,  setYear]  = useState(initDate.getFullYear());
  const [month, setMonth] = useState(initDate.getMonth()); // 0-based

  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const daysIn   = new Date(year, month + 1, 0).getDate();

  const cells: (number | null)[] = [
    ...Array(firstDay).fill(null),
    ...Array.from({ length: daysIn }, (_, i) => i + 1),
  ];

  const isPast = (d: number) => {
    const sel = new Date(year, month, d);
    const min = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
    return sel < min;
  };

  const selected = value ? new Date(value) : null;
  const isSelected = (d: number) =>
    selected &&
    selected.getFullYear() === year &&
    selected.getMonth()    === month &&
    selected.getDate()     === d;

  const prevMonth = () => { if (month === 0) { setMonth(11); setYear(y => y - 1); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 11) { setMonth(0); setYear(y => y + 1); } else setMonth(m => m + 1); };

  const pick = (d: number) => {
    if (isPast(d)) return;
    const mm   = String(month + 1).padStart(2, '0');
    const dd   = String(d).padStart(2, '0');
    onConfirm(`${year}-${mm}-${dd}`);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.45)" }}>
        <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={onClose} />
        <View style={calStyles.sheet}>
          <View style={calStyles.handle} />

          {/* Header */}
          <View style={calStyles.header}>
            <TouchableOpacity onPress={prevMonth} style={calStyles.navBtn}>
              <Ionicons name="chevron-back" size={20} color={COLORS.primary} />
            </TouchableOpacity>
            <Text style={calStyles.monthLabel}>{MONTHS[month]} {year}</Text>
            <TouchableOpacity onPress={nextMonth} style={calStyles.navBtn}>
              <Ionicons name="chevron-forward" size={20} color={COLORS.primary} />
            </TouchableOpacity>
          </View>

          {/* Day-of-week row */}
          <View style={calStyles.row}>
            {["Su","Mo","Tu","We","Th","Fr","Sa"].map(d => (
              <Text key={d} style={calStyles.dow}>{d}</Text>
            ))}
          </View>

          {/* Calendar grid */}
          <View style={calStyles.grid}>
            {cells.map((d, i) => {
              if (!d) return <View key={`e${i}`} style={calStyles.cell} />;
              const past = isPast(d);
              const sel  = isSelected(d);
              return (
                <TouchableOpacity
                  key={`d${d}`}
                  style={[calStyles.cell, sel && calStyles.cellSel, past && calStyles.cellPast]}
                  onPress={() => pick(d)}
                  disabled={past}
                >
                  <Text style={[calStyles.dayText, sel && calStyles.dayTextSel, past && calStyles.dayTextPast]}>
                    {d}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity style={calStyles.closeBtn} onPress={onClose}>
            <Text style={calStyles.closeBtnText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const calStyles = StyleSheet.create({
  sheet:      { backgroundColor: "#fff", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, paddingBottom: 36 },
  handle:     { width: 40, height: 4, backgroundColor: "#e0e0e0", borderRadius: 2, alignSelf: "center", marginBottom: 16 },
  header:     { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 14 },
  navBtn:     { padding: 8 },
  monthLabel: { fontSize: 17, fontWeight: "700", color: "#111" },
  row:        { flexDirection: "row", marginBottom: 6 },
  dow:        { flex: 1, textAlign: "center", fontSize: 12, fontWeight: "600", color: "#888" },
  grid:       { flexDirection: "row", flexWrap: "wrap" },
  cell:       { width: `${100/7}%` as any, aspectRatio: 1, justifyContent: "center", alignItems: "center", borderRadius: 100 },
  cellSel:    { backgroundColor: "#1A5C38" },
  cellPast:   { opacity: 0.35 },
  dayText:    { fontSize: 14, color: "#111", fontWeight: "500" },
  dayTextSel: { color: "#fff", fontWeight: "700" },
  dayTextPast:{ color: "#aaa" },
  closeBtn:   { marginTop: 16, padding: 14, borderRadius: 12, borderWidth: 1.5, borderColor: "#e0e0e0", alignItems: "center" },
  closeBtnText:{ fontWeight: "600", color: "#555" },
});

/** YYYY-MM-DD and must be at least tomorrow */
function isValidFutureDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(s);
  if (isNaN(d.getTime())) return false;
  const tomorrow = new Date();
  tomorrow.setHours(0, 0, 0, 0);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return d >= tomorrow;
}

// ── Chip helper ────────────────────────────────────────────────────────────
function Chip({
  label, active, onPress, disabled,
}: { label: string; active: boolean; onPress: () => void; disabled?: boolean }) {
  return (
    <TouchableOpacity
      style={[styles.chip, active && styles.chipActive, disabled && styles.chipDisabled]}
      onPress={onPress}
      disabled={disabled}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

// ── Option card ────────────────────────────────────────────────────────────
function OptionCard({
  label, desc, active, onPress,
}: { label: string; desc: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity
      style={[styles.optCard, active && styles.optCardActive]}
      onPress={onPress}
    >
      <View style={[styles.radio, active && styles.radioActive]}>
        {active && <View style={styles.radioDot} />}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.optLabel, active && styles.optLabelActive]}>{label}</Text>
        <Text style={styles.optDesc}>{desc}</Text>
      </View>
    </TouchableOpacity>
  );
}

export default function CreateContributionScreen() {
  const { bottom: bottomInset } = useSafeAreaInsets();
  const { communityId: forcedId } = useLocalSearchParams<{ communityId?: string }>();
  const forcedCommunityId = forcedId ? Number(forcedId) : null;

  const [step, setStep]           = useState(1);
  const [saving, setSaving]       = useState(false);
  const [dateError, setDateError] = useState("");
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [customPct, setCustomPct] = useState("");      // custom governance %
  const [useCustomPct, setUseCustomPct] = useState(false);
  const [communities, setCommunities]     = useState<Community[]>([]);
  const [members, setMembers]             = useState<CommunityMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Step 1: Basics
  const [title, setTitle]           = useState("");
  const [description, setDesc]      = useState("");
  const [communityId, setCommunityId] = useState<number | null>(forcedCommunityId);
  const [visibility, setVisibility] = useState<'closed' | 'open'>(forcedCommunityId ? 'closed' : 'open');

  // Step 2: Term & Target
  const [tenureType, setTenureType]         = useState<TenureType>('open');
  const [endDate, setEndDate]               = useState("");
  const [periodMonths, setPeriodMonths]     = useState<number | null>(null);
  const [target, setTarget]                 = useState("");
  const [memberTarget, setMemberTarget]     = useState("");   // per-member target amount

  // Step 3: Schedule
  const [frequency, setFrequency]     = useState<Frequency>('anytime');
  const [amountType, setAmountType]   = useState<AmountType>('open');
  const [fixedAmount, setFixedAmount] = useState("");

  // Step 4: Members
  const [addAll, setAddAll]               = useState(true);
  const [selectedPhones, setSelectedPhones] = useState<Set<string>>(new Set());

  // Campaign flag (open contributions only)
  const [isCampaign, setIsCampaign] = useState(false);

  // Step 5: Governance — disbursement threshold
  const [votingThreshold, setVotingThreshold] = useState<VotingThreshold>('admins');

  // Section C governance settings
  const [txVisibility,          setTxVisibility]          = useState<'all'|'own'|'admins_all'>('all');
  const [amendmentProposer,     setAmendmentProposer]     = useState<'creator'|'admins'|'members'>('creator');
  const [amendmentThreshold,    setAmendmentThreshold]    = useState<VotingThreshold>('admins');
  const [latePolicy,            setLatePolicy]            = useState<'open'|'strict'|'grace'>('open');
  const [lateGraceDays,         setLateGraceDays]         = useState("7");

  // Restore draft on mount (Issue 09)
  useEffect(() => {
    getMyCommunities().then(setCommunities).catch(() => {});
    if (forcedCommunityId) return; // don't restore when launched from a specific community
    AsyncStorage.getItem(DRAFT_KEY).then((raw) => {
      if (!raw) return;
      try {
        const d = JSON.parse(raw);
        if (!d.title) return;
        setStep(d.step ?? 1);
        setTitle(d.title ?? "");
        setDesc(d.description ?? "");
        if (!forcedCommunityId) setCommunityId(d.communityId ?? null);
        setVisibility(d.visibility ?? 'open');
        setTenureType(d.tenureType ?? 'open');
        setEndDate(d.endDate ?? "");
        setPeriodMonths(d.periodMonths ?? null);
        setTarget(d.target ?? "");
        setMemberTarget(d.memberTarget ?? "");
        setFrequency(d.frequency ?? 'anytime');
        setAmountType(d.amountType ?? 'open');
        setFixedAmount(d.fixedAmount ?? "");
        setAddAll(d.addAll ?? true);
        setSelectedPhones(new Set(d.selectedPhones ?? []));
        setIsCampaign(d.isCampaign ?? false);
        setVotingThreshold(d.votingThreshold ?? 'admins');
      } catch {}
    });
  }, []);

  // Persist draft after each change (Issue 09)
  useEffect(() => {
    if (forcedCommunityId) return; // ephemeral flow, no draft needed
    if (!title && step === 1) return; // nothing to save yet
    const draft = {
      step, title, description, communityId, visibility,
      tenureType, endDate, periodMonths, target, memberTarget,
      frequency, amountType, fixedAmount,
      addAll, selectedPhones: [...selectedPhones],
      isCampaign, votingThreshold,
      txVisibility, amendmentProposer, amendmentThreshold, latePolicy, lateGraceDays,
    };
    AsyncStorage.setItem(DRAFT_KEY, JSON.stringify(draft)).catch(() => {});
  }, [step, title, description, communityId, visibility, tenureType, endDate,
      periodMonths, target, frequency, amountType, fixedAmount, addAll,
      selectedPhones, isCampaign, votingThreshold,
      txVisibility, amendmentProposer, amendmentThreshold, latePolicy, lateGraceDays]);

  useEffect(() => {
    if (communityId && step === 4) {
      setLoadingMembers(true);
      getCommunityMembers(communityId)
        .then(setMembers)
        .catch(() => {})
        .finally(() => setLoadingMembers(false));
    }
  }, [communityId, step]);

  const togglePhone = (phone: string) => {
    setSelectedPhones((prev) => {
      const next = new Set(prev);
      next.has(phone) ? next.delete(phone) : next.add(phone);
      return next;
    });
  };

  const canNext = () => {
    if (step === 1) return !!title.trim();
    if (step === 2) {
      if (tenureType === 'date') {
        if (!isValidFutureDate(endDate.trim())) return false;
      }
      if (tenureType === 'period' && !periodMonths) return false;
      return true;
    }
    if (step === 3) return amountType === 'open' || !!fixedAmount.trim();
    return true;
  };

  const goNext = () => {
    if (!canNext()) {
      if (step === 2 && tenureType === 'date') {
        Alert.alert("Invalid date", "Enter a valid future date in YYYY-MM-DD format (e.g. 2027-06-30).");
      } else {
        Alert.alert("Required", "Please complete all required fields before continuing.");
      }
      return;
    }
    setStep((s) => s + 1);
  };

  const handleCreate = async () => {
    setSaving(true);
    try {
      // community and visibility must always be consistent.
      // communityId is the source of truth — derive visibility from it.
      const effectiveCommunity   = communityId ?? null;
      const effectiveVisibility: 'closed' | 'open' = effectiveCommunity ? 'closed' : 'open';

      // Guard: custom % must be a valid 1-100 integer
      let effectiveThreshold = votingThreshold;
      if (useCustomPct) {
        const pct = Number(customPct);
        if (!customPct || isNaN(pct) || pct < 1 || pct > 100) {
          Alert.alert("Invalid threshold", "Enter a custom percentage between 1 and 100.");
          setSaving(false);
          return;
        }
        effectiveThreshold = String(Math.round(pct));
      }

      const payload = {
        title:          title.trim(),
        description:    description.trim() || undefined,
        visibility:     effectiveVisibility,
        community:      effectiveCommunity,
        target_amount:        target ? Number(target) : null,
        member_target_amount: memberTarget ? Number(memberTarget) : null,
        tenure_type:    tenureType,
        end_date:       tenureType === 'date' ? endDate : null,
        period_months:  tenureType === 'period' ? periodMonths : null,
        frequency,
        amount_type:    amountType,
        fixed_amount:   amountType === 'fixed' ? Number(fixedAmount) : null,
        voting_threshold:             effectiveThreshold,
        transaction_visibility:       txVisibility,
        amendment_proposer:           amendmentProposer,
        amendment_voting_threshold:   amendmentThreshold,
        late_contribution_policy:     latePolicy,
        late_contribution_grace_days: latePolicy === 'grace' ? Number(lateGraceDays) : 7,
        add_all_members:  addAll,
        member_phones:    addAll ? [] : [...selectedPhones],
        is_campaign:      effectiveVisibility === 'open' ? isCampaign : false,
      };
      const c = await createContribution(payload);
      await AsyncStorage.removeItem(DRAFT_KEY); // clear draft on success
      router.replace({ pathname: "/contribution/[id]", params: { id: String(c.id) } });
    } catch (e: any) {
      const err =
        e?.response?.data?.error ||
        e?.response?.data?.title?.[0] ||
        e?.response?.data?.community?.[0] ||
        e?.response?.data?.non_field_errors?.[0] ||
        "Failed to create contribution.";
      Alert.alert("Error", err);
    } finally {
      setSaving(false);
    }
  };

  const stepTitles = ["Basics", "Term & Target", "Schedule", "Members", "Governance"];

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader
        title="New Contribution"
        variant="light"
        leading="back"
      />

      {/* Progress bar */}
      <View style={styles.progressWrap}>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${(step / TOTAL_STEPS) * 100}%` as any }]} />
        </View>
        <Text style={styles.progressLabel}>Step {step} of {TOTAL_STEPS} · {stepTitles[step - 1]}</Text>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
      <ScrollView style={styles.body} contentContainerStyle={{ paddingBottom: 100 + bottomInset }} keyboardShouldPersistTaps="handled">

        {/* ── Step 1: Basics ──────────────────────────────────────────── */}
        {step === 1 && (
          <>
            <Text style={styles.label}>Name *</Text>
            <TextInput
              placeholder="e.g. Nairobi Young Savers"
              placeholderTextColor={COLORS.textMuted}
              value={title}
              onChangeText={setTitle}
              style={styles.input}
              autoFocus
            />

            <Text style={styles.label}>Description (optional)</Text>
            <TextInput
              placeholder="What is this contribution for?"
              placeholderTextColor={COLORS.textMuted}
              value={description}
              onChangeText={setDesc}
              style={[styles.input, { height: 80, textAlignVertical: "top" }]}
              multiline
            />
          </>
        )}

        {/* ── Step 2: Term & Target ───────────────────────────────────── */}
        {step === 2 && (
          <>
            <Text style={styles.sectionTitle}>How long will this run?</Text>
            <OptionCard
              label="Open-ended"
              desc="No expiry date. Runs until closed manually."
              active={tenureType === 'open'}
              onPress={() => setTenureType('open')}
            />
            <OptionCard
              label="Until a specific date"
              desc="Set an exact end date."
              active={tenureType === 'date'}
              onPress={() => setTenureType('date')}
            />
            <OptionCard
              label="Fixed period"
              desc="Runs for a set number of months."
              active={tenureType === 'period'}
              onPress={() => setTenureType('period')}
            />

            {tenureType === 'date' && (
              <>
                <Text style={styles.label}>End date *</Text>

                {/* Trigger row — same style as KYC date of birth */}
                <TouchableOpacity
                  style={styles.dateTrigger}
                  onPress={() => setShowDatePicker(true)}
                  activeOpacity={0.7}
                >
                  <Ionicons name="calendar-outline" size={18} color={COLORS.primary} />
                  <Text style={[styles.dateTriggerText, !endDate && { color: COLORS.textMuted }]}>
                    {endDate
                      ? new Date(endDate).toLocaleDateString('en-KE', { day: '2-digit', month: 'long', year: 'numeric' })
                      : "Select end date"}
                  </Text>
                  <Ionicons name="chevron-down" size={16} color={COLORS.textMuted} />
                </TouchableOpacity>

                {endDate && (
                  <Text style={{ color: COLORS.success, fontSize: FONTS.sm, marginTop: 6 }}>
                    Ends {new Date(endDate).toLocaleDateString('en-KE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })}
                  </Text>
                )}

                {/* iOS — bottom sheet modal with spinner */}
                {Platform.OS === 'ios' ? (
                  showDatePicker && (
                    <Modal visible transparent animationType="slide" onRequestClose={() => setShowDatePicker(false)}>
                      <View style={styles.dateModalBackdrop}>
                        <View style={styles.dateModalSheet}>
                          <View style={styles.dateModalHeader}>
                            <TouchableOpacity onPress={() => setShowDatePicker(false)}>
                              <Text style={styles.dateModalCancel}>Cancel</Text>
                            </TouchableOpacity>
                            <Text style={styles.dateModalTitle}>End Date</Text>
                            <TouchableOpacity onPress={() => setShowDatePicker(false)}>
                              <Text style={styles.dateModalDone}>Done</Text>
                            </TouchableOpacity>
                          </View>
                          <DateTimePicker
                            value={endDate ? new Date(endDate) : (() => { const d = new Date(); d.setMonth(d.getMonth() + 1); return d; })()}
                            mode="date"
                            display="spinner"
                            minimumDate={new Date(Date.now() + 86400000)}
                            onChange={(_, selected) => {
                              if (selected) {
                                const y = selected.getFullYear();
                                const m = String(selected.getMonth() + 1).padStart(2, "0");
                                const d = String(selected.getDate()).padStart(2, "0");
                                setEndDate(`${y}-${m}-${d}`);
                                setDateError("");
                              }
                            }}
                            textColor={COLORS.text}
                          />
                        </View>
                      </View>
                    </Modal>
                  )
                ) : (
                  showDatePicker && (
                    <DateTimePicker
                      value={endDate ? new Date(endDate) : (() => { const d = new Date(); d.setMonth(d.getMonth() + 1); return d; })()}
                      mode="date"
                      display="default"
                      minimumDate={new Date(Date.now() + 86400000)}
                      onChange={(_, selected) => {
                        setShowDatePicker(false);
                        if (selected) {
                          const y = selected.getFullYear();
                          const m = String(selected.getMonth() + 1).padStart(2, "0");
                          const d = String(selected.getDate()).padStart(2, "0");
                          setEndDate(`${y}-${m}-${d}`);
                          setDateError("");
                        }
                      }}
                    />
                  )
                )}
              </>
            )}

            {/* ── Per-member personal target (shown when end date is set) ── */}
            {tenureType === 'date' && (
              <>
                <View style={styles.memberTargetSeparator} />
                <Text style={styles.label}>Personal target per member (optional)</Text>
                <Text style={{ fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 8, lineHeight: 18 }}>
                  Set an individual savings goal each member should reach by the end date.
                  Members can track their own progress toward this amount.
                </Text>
                <View style={[styles.input, { flexDirection: "row", alignItems: "center" }]}>
                  <Text style={{ color: COLORS.textMuted, marginRight: 6, fontSize: FONTS.md }}>KES</Text>
                  <TextInput
                    style={{ flex: 1, fontSize: FONTS.md, color: COLORS.text }}
                    value={memberTarget}
                    onChangeText={setMemberTarget}
                    placeholder="e.g. 150,000"
                    placeholderTextColor={COLORS.textMuted}
                    keyboardType="numeric"
                  />
                </View>
                {memberTarget && endDate ? (
                  <Text style={{ color: COLORS.primary, fontSize: FONTS.sm, marginTop: 4 }}>
                    Each member should reach KES {Number(memberTarget).toLocaleString()} by{" "}
                    {new Date(endDate).toLocaleDateString('en-KE', { day: '2-digit', month: 'long', year: 'numeric' })}
                  </Text>
                ) : null}
              </>
            )}

            {tenureType === 'period' && (
              <>
                <Text style={styles.label}>Duration *</Text>
                <View style={styles.chipRow}>
                  {[1, 3, 6, 12, 24].map((m) => (
                    <Chip
                      key={m}
                      label={m === 1 ? "1 month" : m === 12 ? "1 year" : m === 24 ? "2 years" : `${m} months`}
                      active={periodMonths === m}
                      onPress={() => setPeriodMonths(m)}
                    />
                  ))}
                </View>
              </>
            )}

            <Text style={styles.label}>Target amount (KES, optional)</Text>
            <TextInput
              placeholder="e.g. 500,000"
              placeholderTextColor={COLORS.textMuted}
              value={target}
              onChangeText={setTarget}
              style={styles.input}
              keyboardType="numeric"
            />
            <Text style={styles.hint}>Leave blank if there is no specific target.</Text>
          </>
        )}

        {/* ── Step 3: Schedule ────────────────────────────────────────── */}
        {step === 3 && (
          <>
            <Text style={styles.sectionTitle}>How often do members contribute?</Text>
            {([
              ['anytime', 'Anytime', 'Members contribute whenever they want'],
              ['daily',   'Daily',   'Members contribute once per day'],
              ['weekly',  'Weekly',  'Members contribute once per week'],
              ['monthly', 'Monthly', 'Members contribute once per month'],
            ] as [Frequency, string, string][]).map(([val, label, desc]) => (
              <OptionCard key={val} label={label} desc={desc} active={frequency === val} onPress={() => setFrequency(val)} />
            ))}

            <Text style={[styles.sectionTitle, { marginTop: 24 }]}>Contribution amount per member</Text>
            <OptionCard
              label="Open amount"
              desc="Each member decides how much to contribute."
              active={amountType === 'open'}
              onPress={() => setAmountType('open')}
            />
            <OptionCard
              label="Fixed amount"
              desc="Every member contributes the same set amount."
              active={amountType === 'fixed'}
              onPress={() => setAmountType('fixed')}
            />

            {amountType === 'fixed' && (
              <>
                <Text style={styles.label}>Fixed amount (KES) *</Text>
                <TextInput
                  placeholder="e.g. 1000"
                  placeholderTextColor={COLORS.textMuted}
                  value={fixedAmount}
                  onChangeText={setFixedAmount}
                  style={styles.input}
                  keyboardType="numeric"
                  autoFocus
                />
              </>
            )}
          </>
        )}

        {/* ── Step 4: Members ─────────────────────────────────────────── */}
        {step === 4 && (
          <>
            <Text style={styles.sectionTitle}>Who joins this contribution?</Text>
            <OptionCard
              label="All community members"
              desc="Everyone in the community is automatically added."
              active={addAll}
              onPress={() => setAddAll(true)}
            />
            <OptionCard
              label="Select specific members"
              desc="Hand-pick who participates."
              active={!addAll}
              onPress={() => setAddAll(false)}
            />

            {!addAll && (
              <>
                <Text style={styles.label}>Select members</Text>
                {loadingMembers ? (
                  <ActivityIndicator color={COLORS.primary} style={{ marginTop: 16 }} />
                ) : members.length === 0 ? (
                  <Text style={styles.muted}>No community members found.</Text>
                ) : (
                  members.map((m) => {
                    const phone = m.phone_number;
                    if (!phone) return null;
                    const selected = selectedPhones.has(phone);
                    return (
                      <TouchableOpacity
                        key={m.id}
                        style={[styles.memberRow, selected && styles.memberRowActive]}
                        onPress={() => togglePhone(phone)}
                      >
                        <Avatar name={m.name || phone} size={36} />
                        <View style={{ flex: 1, marginLeft: 12 }}>
                          <Text style={styles.memberName}>{m.name || m.phone_number}</Text>
                          <Text style={styles.memberPhone}>{m.phone_number}</Text>
                        </View>
                        <View style={[styles.checkCircle, selected && styles.checkCircleActive]}>
                          {selected && <Ionicons name="checkmark" size={14} color={COLORS.white} />}
                        </View>
                      </TouchableOpacity>
                    );
                  })
                )}
              </>
            )}
          </>
        )}

        {/* ── Step 5: Governance ──────────────────────────────────────── */}
        {step === 5 && (
          <>
            <Text style={styles.sectionTitle}>Who can approve withdrawals?</Text>
            <OptionCard
              label="Admins only"
              desc="Only community admins & treasurers can approve disbursements."
              active={!useCustomPct && votingThreshold === 'admins'}
              onPress={() => { setUseCustomPct(false); setVotingThreshold('admins'); }}
            />
            <OptionCard
              label="50%+1 majority"
              desc="More than half of members must vote to approve — democratic control."
              active={!useCustomPct && votingThreshold === '50'}
              onPress={() => { setUseCustomPct(false); setVotingThreshold('50'); }}
            />
            <OptionCard
              label="All members"
              desc="Every member must agree before funds move."
              active={!useCustomPct && votingThreshold === '100'}
              onPress={() => { setUseCustomPct(false); setVotingThreshold('100'); }}
            />

            {/* Custom percentage */}
            <TouchableOpacity
              style={[styles.optCard, useCustomPct && styles.optCardActive]}
              onPress={() => setUseCustomPct(true)}
            >
              <View style={[styles.radio, useCustomPct && styles.radioActive]}>
                {useCustomPct && <View style={styles.radioDot} />}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[styles.optLabel, useCustomPct && styles.optLabelActive]}>Custom percentage</Text>
                <Text style={styles.optDesc}>Set a specific approval threshold that fits your group.</Text>
              </View>
            </TouchableOpacity>

            {useCustomPct && (
              <>
                <Text style={styles.label}>Required approval % *</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                  <TextInput
                    placeholder="e.g. 75"
                    placeholderTextColor={COLORS.textMuted}
                    value={customPct}
                    onChangeText={(v) => {
                      const n = v.replace(/[^0-9]/g, "");
                      if (Number(n) <= 100) setCustomPct(n);
                    }}
                    style={[styles.input, { flex: 1 }]}
                    keyboardType="numeric"
                    maxLength={3}
                    autoFocus
                  />
                  <Text style={{ fontSize: FONTS.xl, color: COLORS.textSecondary, fontWeight: "700" }}>%</Text>
                </View>
              </>
            )}

            {/* ── Section C: Contribution Governance ─────────────────── */}
            <View style={styles.sectionDivider} />
            <Text style={styles.sectionTitle}>Transaction Visibility</Text>
            <Text style={styles.sectionDesc}>Who can see each other's payment records?</Text>
            {([
              { v: 'all',        label: 'All members see all transactions',        desc: 'Full transparency — everyone sees who paid what.' },
              { v: 'own',        label: 'Members see only their own',              desc: 'Private — each person sees only their own payments.' },
              { v: 'admins_all', label: 'Admins see all; members see own',         desc: 'Admins have full visibility; members see their own.' },
            ] as { v: typeof txVisibility; label: string; desc: string }[]).map(o => (
              <OptionCard key={o.v} label={o.label} desc={o.desc}
                active={txVisibility === o.v} onPress={() => setTxVisibility(o.v)} />
            ))}

            <View style={styles.sectionDivider} />
            <Text style={styles.sectionTitle}>Who Can Propose Amendments?</Text>
            <Text style={styles.sectionDesc}>Control who can propose changes to contribution settings.</Text>
            {([
              { v: 'creator', label: 'Creator only',           desc: 'Only you can propose changes.' },
              { v: 'admins',  label: 'Admins & Treasurers',    desc: 'Privileged roles can propose changes.' },
              { v: 'members', label: 'Any active participant', desc: 'Any member can propose changes.' },
            ] as { v: typeof amendmentProposer; label: string; desc: string }[]).map(o => (
              <OptionCard key={o.v} label={o.label} desc={o.desc}
                active={amendmentProposer === o.v} onPress={() => setAmendmentProposer(o.v)} />
            ))}

            <View style={styles.sectionDivider} />
            <Text style={styles.sectionTitle}>Amendment Approval Threshold</Text>
            <Text style={styles.sectionDesc}>How many votes are needed to approve a settings change? (Separate from disbursement threshold.)</Text>
            {([
              { v: 'admins', label: 'Admins only',    desc: 'Only admins vote on setting changes.' },
              { v: '50',     label: '50%+ majority',  desc: 'More than half of members must agree.' },
              { v: '67',     label: '2/3 majority',   desc: 'Two-thirds of members must agree.' },
              { v: '100',    label: 'All members',    desc: 'Full consensus required.' },
            ] as { v: VotingThreshold; label: string; desc: string }[]).map(o => (
              <OptionCard key={o.v} label={o.label} desc={o.desc}
                active={amendmentThreshold === o.v} onPress={() => setAmendmentThreshold(o.v)} />
            ))}

            <View style={styles.sectionDivider} />
            <Text style={styles.sectionTitle}>Late Contributions</Text>
            <Text style={styles.sectionDesc}>What happens after the end date?</Text>
            {([
              { v: 'open',   label: 'Always allowed',        desc: 'Contributions accepted at any time, even after end date.' },
              { v: 'strict', label: 'Blocked after end date', desc: 'No contributions accepted once the end date passes.' },
              { v: 'grace',  label: 'Grace period',          desc: 'Allow contributions for a set number of days after end date.' },
            ] as { v: typeof latePolicy; label: string; desc: string }[]).map(o => (
              <OptionCard key={o.v} label={o.label} desc={o.desc}
                active={latePolicy === o.v} onPress={() => setLatePolicy(o.v)} />
            ))}
            {latePolicy === 'grace' && (
              <>
                <Text style={styles.label}>Grace period (days after end date)</Text>
                <TextInput
                  style={styles.input}
                  value={lateGraceDays}
                  onChangeText={setLateGraceDays}
                  placeholder="7"
                  placeholderTextColor={COLORS.textMuted}
                  keyboardType="numeric"
                />
              </>
            )}
          </>
        )}
      </ScrollView>
      </KeyboardAvoidingView>

      {/* Bottom nav */}
      <View style={[styles.footer, { paddingBottom: 16 + bottomInset }]}>
        {step > 1 && (
          <TouchableOpacity style={styles.backBtn} onPress={() => setStep((s) => s - 1)}>
            <Ionicons name="arrow-back" size={18} color={COLORS.primary} />
            <Text style={styles.backText}>Back</Text>
          </TouchableOpacity>
        )}
        <View style={{ flex: 1 }} />
        {step < TOTAL_STEPS ? (
          <TouchableOpacity
            style={[styles.nextBtn, !canNext() && styles.nextBtnDisabled]}
            onPress={goNext}
          >
            <Text style={styles.nextText}>Next</Text>
            <Ionicons name="arrow-forward" size={18} color={COLORS.white} />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={[styles.nextBtn, saving && styles.nextBtnDisabled]}
            onPress={handleCreate}
            disabled={saving}
          >
            {saving
              ? <ActivityIndicator color={COLORS.white} />
              : <>
                  <Text style={styles.nextText}>Create</Text>
                  <Ionicons name="checkmark" size={18} color={COLORS.white} />
                </>
            }
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  body: { paddingHorizontal: 20, paddingTop: 4 },

  progressWrap: { paddingHorizontal: 20, paddingVertical: 12, backgroundColor: COLORS.white, borderBottomWidth: 1, borderBottomColor: COLORS.divider },
  progressTrack: { height: 4, backgroundColor: COLORS.divider, borderRadius: RADIUS.full, overflow: "hidden", marginBottom: 6 },
  progressFill:  { height: "100%", backgroundColor: COLORS.primary },
  progressLabel: { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },

  sectionTitle: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginTop: 16, marginBottom: 10 },
  label: { fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary, marginTop: 16, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 },
  hint:  { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 4, lineHeight: 18 },
  muted: { fontSize: FONTS.sm, color: COLORS.textMuted },

  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 14, fontSize: FONTS.md, color: COLORS.text, backgroundColor: COLORS.white,
  },

  memberTargetSeparator: {
    height: 1, backgroundColor: COLORS.divider, marginVertical: 16,
  },
  sectionDivider: { height: 1, backgroundColor: COLORS.divider, marginVertical: 20 },
  sectionDesc:    { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 10, lineHeight: 18 },

  // Date picker trigger — matches KYC date of birth style
  dateTrigger: {
    flexDirection: "row", alignItems: "center", gap: 10,
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 14, backgroundColor: COLORS.white,
  },
  dateTriggerText: { flex: 1, fontSize: FONTS.md, color: COLORS.text },
  dateModalBackdrop: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end",
  },
  dateModalSheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingBottom: 32,
  },
  dateModalHeader: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: 20, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  dateModalTitle:  { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  dateModalCancel: { fontSize: FONTS.md, color: COLORS.textSecondary },
  dateModalDone:   { fontSize: FONTS.md, fontWeight: "700", color: COLORS.primary },

  optCard:       { flexDirection: "row", alignItems: "flex-start", gap: 12, borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md, padding: 14, backgroundColor: COLORS.white, marginBottom: 8 },
  optCardActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primaryPale },
  radio:       { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: COLORS.border, justifyContent: "center", alignItems: "center", marginTop: 2, flexShrink: 0 },
  radioActive: { borderColor: COLORS.primary },
  radioDot:    { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },
  optLabel:       { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  optLabelActive: { color: COLORS.primary },
  optDesc: { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 4 },
  chip:         { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.white },
  chipActive:   { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipDisabled: { opacity: 0.5 },
  chipText:       { fontSize: FONTS.sm, color: COLORS.textSecondary, fontWeight: "600" },
  chipTextActive: { color: COLORS.white },

  memberRow:       { flexDirection: "row", alignItems: "center", padding: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.white, borderWidth: 1, borderColor: COLORS.border, marginBottom: 8 },
  memberRowActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primaryPale },
  memberName:  { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  memberPhone: { fontSize: FONTS.sm, color: COLORS.textMuted },
  checkCircle:       { width: 24, height: 24, borderRadius: 12, borderWidth: 2, borderColor: COLORS.border, justifyContent: "center", alignItems: "center" },
  checkCircleActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },

  toggleRow: {
    flexDirection:   "row",
    alignItems:      "center",
    gap:             12,
    borderWidth:     1.5,
    borderColor:     COLORS.border,
    borderRadius:    RADIUS.md,
    padding:         14,
    backgroundColor: COLORS.white,
    marginBottom:    8,
  },
  toggleIcon: {
    width: 36, height: 36,
    borderRadius:    RADIUS.full,
    backgroundColor: COLORS.background,
    justifyContent:  "center",
    alignItems:      "center",
    flexShrink:      0,
  },
  toggleLabel: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  toggleDesc:  { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  footer: {
    position: "absolute", bottom: 0, left: 0, right: 0,
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 20, paddingVertical: 16,
    backgroundColor: COLORS.white, borderTopWidth: 1, borderTopColor: COLORS.divider,
  },
  backBtn:  { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 12, paddingHorizontal: 4 },
  backText: { fontSize: FONTS.md, color: COLORS.primary, fontWeight: "600" },
  nextBtn:         { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: COLORS.primary, paddingVertical: 13, paddingHorizontal: 24, borderRadius: RADIUS.full },
  nextBtnDisabled: { opacity: 0.5 },
  nextText: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.white },
});
