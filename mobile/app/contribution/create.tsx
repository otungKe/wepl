import { useState, useEffect } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert, ScrollView, KeyboardAvoidingView, Platform, Switch,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  createContribution, TenureType, Frequency, AmountType, VotingThreshold,
} from "../../api/contributions";
import { getMyCommunities, getCommunityMembers, Community, CommunityMember } from "../../api/communities";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import Avatar from "../../components/app/Avatar";

const TOTAL_STEPS = 5;

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

  const [step, setStep]       = useState(1);
  const [saving, setSaving]   = useState(false);
  const [communities, setCommunities]     = useState<Community[]>([]);
  const [members, setMembers]             = useState<CommunityMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Step 1: Basics
  const [title, setTitle]           = useState("");
  const [description, setDesc]      = useState("");
  const [communityId, setCommunityId] = useState<number | null>(forcedCommunityId);
  const [visibility, setVisibility] = useState<'closed' | 'open'>(forcedCommunityId ? 'closed' : 'open');

  // Step 2: Term & Target
  const [tenureType, setTenureType]     = useState<TenureType>('open');
  const [endDate, setEndDate]           = useState("");
  const [periodMonths, setPeriodMonths] = useState<number | null>(null);
  const [target, setTarget]             = useState("");

  // Step 3: Schedule
  const [frequency, setFrequency]     = useState<Frequency>('anytime');
  const [amountType, setAmountType]   = useState<AmountType>('open');
  const [fixedAmount, setFixedAmount] = useState("");

  // Step 4: Members
  const [addAll, setAddAll]               = useState(true);
  const [selectedPhones, setSelectedPhones] = useState<Set<string>>(new Set());

  // Campaign flag (open contributions only)
  const [isCampaign, setIsCampaign] = useState(false);

  // Step 5: Governance
  const [votingThreshold, setVotingThreshold] = useState<VotingThreshold>('admins');

  useEffect(() => {
    getMyCommunities().then(setCommunities).catch(() => {});
  }, []);

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
    if (step === 1) return !!title.trim() && (visibility === 'open' || !!communityId);
    if (step === 2) {
      if (tenureType === 'date' && !endDate.trim()) return false;
      if (tenureType === 'period' && !periodMonths) return false;
      return true;
    }
    if (step === 3) return amountType === 'open' || !!fixedAmount.trim();
    return true;
  };

  const goNext = () => {
    if (!canNext()) {
      Alert.alert("Required", "Please complete the required fields.");
      return;
    }
    setStep((s) => s + 1);
  };

  const handleCreate = async () => {
    setSaving(true);
    try {
      const payload = {
        title: title.trim(),
        description: description.trim() || undefined,
        visibility,
        community: visibility === 'closed' ? communityId : null,
        target_amount: target ? Number(target) : null,
        tenure_type: tenureType,
        end_date: tenureType === 'date' ? endDate : null,
        period_months: tenureType === 'period' ? periodMonths : null,
        frequency,
        amount_type: amountType,
        fixed_amount: amountType === 'fixed' ? Number(fixedAmount) : null,
        voting_threshold: votingThreshold,
        add_all_members: addAll,
        member_phones: addAll ? [] : [...selectedPhones],
        is_campaign: visibility === 'open' ? isCampaign : false,
      };
      const c = await createContribution(payload);
      router.replace({ pathname: `/contribution/${c.id}` });
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

            <Text style={styles.label}>Scope</Text>
            <View style={styles.chipRow}>
              <Chip label="Community (closed)" active={visibility === 'closed'} onPress={() => setVisibility('closed')} disabled={!!forcedCommunityId} />
              <Chip label="Open / Public" active={visibility === 'open'} onPress={() => { setVisibility('open'); setCommunityId(null); }} disabled={!!forcedCommunityId} />
            </View>

            {visibility === 'closed' && (
              <>
                <Text style={styles.label}>Community *</Text>
                <View style={styles.chipRow}>
                  {communities.map((c) => (
                    <Chip
                      key={c.id}
                      label={c.name}
                      active={communityId === c.id}
                      onPress={() => setCommunityId(c.id)}
                      disabled={!!forcedCommunityId}
                    />
                  ))}
                  {communities.length === 0 && <Text style={styles.muted}>No communities yet.</Text>}
                </View>
              </>
            )}

            {visibility === 'open' && (
              <>
                <Text style={styles.label}>Campaign</Text>
                <View style={styles.toggleRow}>
                  <View style={styles.toggleIcon}>
                    <Ionicons name="megaphone-outline" size={18} color={COLORS.accent} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.toggleLabel}>Mark as public campaign</Text>
                    <Text style={styles.toggleDesc}>
                      Appears in Discover so anyone can find and contribute to it.
                    </Text>
                  </View>
                  <Switch
                    value={isCampaign}
                    onValueChange={setIsCampaign}
                    trackColor={{ true: COLORS.accent }}
                    thumbColor={COLORS.white}
                  />
                </View>
              </>
            )}
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
                <Text style={styles.label}>End date (YYYY-MM-DD) *</Text>
                <TextInput
                  placeholder="e.g. 2026-12-31"
                  placeholderTextColor={COLORS.textMuted}
                  value={endDate}
                  onChangeText={setEndDate}
                  style={styles.input}
                />
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
                    const selected = selectedPhones.has(m.phone_number);
                    return (
                      <TouchableOpacity
                        key={m.id}
                        style={[styles.memberRow, selected && styles.memberRowActive]}
                        onPress={() => togglePhone(m.phone_number)}
                      >
                        <Avatar name={m.name || m.phone_number} size={36} />
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
            {([
              ['admins', 'Admins only',       'Only community admins & treasurers can approve disbursements.'],
              ['25',     '25% of members',    'A quarter of members must vote to approve.'],
              ['50',     '50% of members',    'A majority must approve — true democratic control.'],
              ['100',    'All members',        'Everyone must agree before funds move.'],
            ] as [VotingThreshold, string, string][]).map(([val, label, desc]) => (
              <OptionCard key={val} label={label} desc={desc} active={votingThreshold === val} onPress={() => setVotingThreshold(val)} />
            ))}

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
