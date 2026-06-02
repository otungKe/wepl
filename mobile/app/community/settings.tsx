/**
 * Community Settings screen
 *
 * Accessible via: Community detail → ••• → Community Settings (admins only)
 *
 * Sections:
 *   1. Basic Info     — name, description
 *   2. Community Access — single three-way selector (private/public-request/public-open)
 *   3. Governance     — invite permission, contribution permission,
 *                       member list visibility, max members
 */
import { useState, useEffect } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, ActivityIndicator, Alert, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  getCommunity, updateCommunity,
  type JoinPolicy, type InvitePermission,
  type ContributionPermission, type MemberListVisibility,
} from "../../api/communities";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";

type AccessLevel = "private" | "public_request" | "public_open";

function toAccessLevel(isPrivate: boolean, joinPolicy: JoinPolicy): AccessLevel {
  if (isPrivate) return "private";
  return joinPolicy === "open" ? "public_open" : "public_request";
}

function fromAccessLevel(level: AccessLevel): { is_private: boolean; join_policy: JoinPolicy } {
  if (level === "private")        return { is_private: true,  join_policy: "invite_only" };
  if (level === "public_request") return { is_private: false, join_policy: "request" };
  return                                 { is_private: false, join_policy: "open" };
}

// ── Reusable radio option ────────────────────────────────────────────────────

function RadioOption<T extends string>({
  value, current, label, desc, onPress,
}: { value: T; current: T; label: string; desc: string; onPress: () => void }) {
  const active = value === current;
  return (
    <TouchableOpacity
      style={[s.optRow, active && s.optRowActive]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={[s.radio, active && s.radioActive]}>
        {active && <View style={s.radioDot} />}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[s.optLabel, active && { color: COLORS.primary }]}>{label}</Text>
        <Text style={s.optDesc}>{desc}</Text>
      </View>
    </TouchableOpacity>
  );
}

// ── Screen ───────────────────────────────────────────────────────────────────

export default function CommunitySettingsScreen() {
  const { id, name: nameParam } = useLocalSearchParams<{ id: string; name: string }>();
  const communityId = Number(id);

  const [loading, setSaving]    = useState(false);
  const [fetching, setFetching] = useState(true);

  // Basic info
  const [name,        setName]        = useState(nameParam ?? "");
  const [description, setDescription] = useState("");

  // Access
  const [accessLevel, setAccessLevel] = useState<AccessLevel>("private");

  // Governance
  const [invitePermission,       setInvitePermission]       = useState<InvitePermission>("admins");
  const [contributionPermission, setContributionPermission] = useState<ContributionPermission>("admins");
  const [memberListVisibility,   setMemberListVisibility]   = useState<MemberListVisibility>("all");
  const [maxMembers,             setMaxMembers]             = useState("");
  const [coolingOffDays,         setCoolingOffDays]         = useState("30");

  useEffect(() => {
    getCommunity(communityId)
      .then(c => {
        setName(c.name);
        setDescription(c.description ?? "");
        setAccessLevel(toAccessLevel(c.is_private, c.join_policy));
        setInvitePermission(c.invite_permission ?? "admins");
        setContributionPermission(c.contribution_permission ?? "admins");
        setMemberListVisibility(c.member_list_visibility ?? "all");
        setMaxMembers(c.max_members ? String(c.max_members) : "");
        setCoolingOffDays(c.cooling_off_days != null ? String(c.cooling_off_days) : "30");
      })
      .catch(() => Alert.alert("Error", "Could not load community settings."))
      .finally(() => setFetching(false));
  }, [communityId]);

  const handleSave = async () => {
    if (!name.trim()) { Alert.alert("Required", "Community name cannot be empty."); return; }
    const { is_private, join_policy } = fromAccessLevel(accessLevel);
    setSaving(true);
    try {
      await updateCommunity(communityId, {
        name:                    name.trim(),
        description:             description.trim() || undefined,
        is_private,
        join_policy,
        invite_permission:       invitePermission,
        contribution_permission: contributionPermission,
        member_list_visibility:  memberListVisibility,
        max_members:      maxMembers ? Number(maxMembers) : null,
        cooling_off_days: coolingOffDays ? Number(coolingOffDays) : 0,
      } as any);
      router.back();
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  if (fetching) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Community Settings" variant="light" leading="back"
          onBack={() => router.back()} />
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  const isPublic = accessLevel !== "private";

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader
        title="Community Settings"
        variant="light"
        leading="back"
        onBack={() => router.back()}
      />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}>

          {/* ── Basic Info ───────────────────────────────────────── */}
          <Text style={s.section}>BASIC INFO</Text>
          <View style={s.card}>
            <Text style={s.fieldLabel}>Name</Text>
            <TextInput
              style={s.input}
              value={name}
              onChangeText={setName}
              placeholder="Community name"
              placeholderTextColor={COLORS.textMuted}
              maxLength={120}
            />
            <Text style={[s.fieldLabel, { marginTop: 12 }]}>Description</Text>
            <TextInput
              style={[s.input, { height: 80, textAlignVertical: "top" }]}
              value={description}
              onChangeText={setDescription}
              placeholder="What is this community about? (optional)"
              placeholderTextColor={COLORS.textMuted}
              multiline
              maxLength={500}
            />
          </View>

          {/* ── Community Access ─────────────────────────────────── */}
          <Text style={s.section}>COMMUNITY ACCESS</Text>
          <View style={s.card}>
            {([
              { value: "private"        as AccessLevel, icon: "lock-closed-outline", label: "Private",                    desc: "Not discoverable. Members join via invite link only." },
              { value: "public_request" as AccessLevel, icon: "people-outline",      label: "Public — approval required",  desc: "Appears in Discover. Anyone can request; an admin must approve." },
              { value: "public_open"    as AccessLevel, icon: "earth-outline",        label: "Public — open",              desc: "Appears in Discover. Any WEPL user can join immediately." },
            ]).map(opt => (
              <TouchableOpacity
                key={opt.value}
                style={[s.accessRow, accessLevel === opt.value && s.accessRowActive]}
                onPress={() => setAccessLevel(opt.value)}
                activeOpacity={0.7}
              >
                <View style={[s.radio, accessLevel === opt.value && s.radioActive]}>
                  {accessLevel === opt.value && <View style={s.radioDot} />}
                </View>
                <View style={[s.accessIcon, accessLevel === opt.value && { backgroundColor: COLORS.primary + "25" }]}>
                  <Ionicons name={opt.icon as any} size={18} color={accessLevel === opt.value ? COLORS.primary : COLORS.textMuted} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[s.accessLabel, accessLevel === opt.value && { color: COLORS.primary }]}>{opt.label}</Text>
                  <Text style={s.accessDesc}>{opt.desc}</Text>
                </View>
              </TouchableOpacity>
            ))}
          </View>

          {/* ── Governance ───────────────────────────────────────── */}
          <Text style={s.section}>GOVERNANCE</Text>
          <View style={s.card}>

            <Text style={s.govLabel}>Who can invite members?</Text>
            {([
              { value: "admins"  as InvitePermission, label: "Admins & Treasurers", desc: "Only privileged roles can share the invite link." },
              { value: "members" as InvitePermission, label: "Any member",          desc: "Every member can share the invite link." },
              { value: "creator" as InvitePermission, label: "Creator only",        desc: "Only the group creator can invite." },
            ]).map(opt => (
              <RadioOption key={opt.value} value={opt.value} current={invitePermission}
                label={opt.label} desc={opt.desc} onPress={() => setInvitePermission(opt.value)} />
            ))}

            <View style={s.govDivider} />

            <Text style={s.govLabel}>Who can create contributions?</Text>
            {([
              { value: "admins"  as ContributionPermission, label: "Admins & Treasurers", desc: "Keeps tight control over what pools are created." },
              { value: "members" as ContributionPermission, label: "Any member",          desc: "Any member can propose a contribution." },
            ]).map(opt => (
              <RadioOption key={opt.value} value={opt.value} current={contributionPermission}
                label={opt.label} desc={opt.desc} onPress={() => setContributionPermission(opt.value)} />
            ))}

            <View style={s.govDivider} />

            <Text style={s.govLabel}>Who can see the member list?</Text>
            {([
              { value: "all"    as MemberListVisibility, label: "All members", desc: "Every member can see who else is in the group." },
              { value: "admins" as MemberListVisibility, label: "Admins only",  desc: "Only admins see the full list; others see only themselves." },
            ]).map(opt => (
              <RadioOption key={opt.value} value={opt.value} current={memberListVisibility}
                label={opt.label} desc={opt.desc} onPress={() => setMemberListVisibility(opt.value)} />
            ))}

            <View style={s.govDivider} />

            <Text style={s.govLabel}>Maximum members</Text>
            <TextInput
              style={s.input}
              value={maxMembers}
              onChangeText={setMaxMembers}
              placeholder="No limit"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="numeric"
            />
            <Text style={s.hint}>Leave blank for unlimited.</Text>

            <View style={s.govDivider} />

            <Text style={s.govLabel}>New member cooling-off period (days)</Text>
            <Text style={[s.hint, { marginBottom: 8 }]}>
              New members must wait this many days before they can submit welfare
              claims, request advances, or vote on disbursements.
              Set to 0 for no waiting period.
            </Text>

            {/* Quick presets */}
            <View style={{ flexDirection: "row", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
              {["0", "7", "14", "30", "60", "90"].map(d => (
                <TouchableOpacity
                  key={d}
                  style={[
                    s.coolingChip,
                    coolingOffDays === d && s.coolingChipActive,
                  ]}
                  onPress={() => setCoolingOffDays(d)}
                >
                  <Text style={[s.coolingChipText, coolingOffDays === d && { color: COLORS.primary, fontWeight: "700" }]}>
                    {d === "0" ? "None" : `${d} days`}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TextInput
              style={s.input}
              value={coolingOffDays}
              onChangeText={setCoolingOffDays}
              placeholder="30"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="numeric"
            />
            {Number(coolingOffDays) > 0 && (
              <Text style={[s.hint, { color: COLORS.primary }]}>
                New members will have a {coolingOffDays}-day waiting period before accessing financial features.
              </Text>
            )}

          </View>

          {/* ── Save ─────────────────────────────────────────────── */}
          <TouchableOpacity
            style={[s.saveBtn, loading && { opacity: 0.6 }]}
            onPress={handleSave}
            disabled={loading}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={s.saveBtnText}>Save Settings</Text>
            }
          </TouchableOpacity>

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  body:   { padding: 16, gap: 4 },

  section: {
    fontSize: 11, fontWeight: "700", color: COLORS.textMuted,
    letterSpacing: 0.8, marginTop: 16, marginBottom: 8, paddingHorizontal: 4,
  },

  card: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.border,
    padding: 16,
    overflow: "hidden",
  },

  fieldLabel: { fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary, marginBottom: 6 },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background,
  },
  hint: { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 4 },

  // Access selector
  accessRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  accessRowActive: { backgroundColor: COLORS.primaryPale },
  accessIcon: {
    width: 34, height: 34, borderRadius: RADIUS.md,
    backgroundColor: COLORS.background,
    justifyContent: "center", alignItems: "center",
    flexShrink: 0,
  },
  accessLabel: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  accessDesc:  { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  // Governance
  govLabel:   { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.text, marginBottom: 8, marginTop: 4 },
  govDivider: { height: 1, backgroundColor: COLORS.divider, marginVertical: 14 },

  // Radio
  optRow:      { flexDirection: "row", alignItems: "flex-start", gap: 10, paddingVertical: 8 },
  optRowActive:{ backgroundColor: "transparent" },
  optLabel:    { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  optDesc:     { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },
  radio:       { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: COLORS.border, justifyContent: "center", alignItems: "center", marginTop: 2, flexShrink: 0 },
  radioActive: { borderColor: COLORS.primary },
  radioDot:    { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },

  // Cooling-off preset chips
  coolingChip: {
    paddingHorizontal: 12, paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1.5, borderColor: COLORS.border,
    backgroundColor: COLORS.white,
  },
  coolingChipActive: {
    borderColor: COLORS.primary, backgroundColor: COLORS.primaryPale,
  },
  coolingChipText: { fontSize: FONTS.sm, color: COLORS.textSecondary },

  // Save
  saveBtn: {
    backgroundColor: COLORS.primary, padding: 16,
    borderRadius: RADIUS.md, alignItems: "center", marginTop: 16,
  },
  saveBtnText: { color: "#fff", fontWeight: "700", fontSize: FONTS.md },
});
