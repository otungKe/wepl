import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  Switch,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Modal,
  Pressable,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { createCommunity, type JoinPolicy, type InvitePermission, type ContributionPermission, type MemberListVisibility } from "../../api/communities";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import FAB from "../../components/app/FAB";

const CATEGORIES = [
  { key: "general",    label: "General"              },
  { key: "savings",    label: "Savings"              },
  { key: "chama",      label: "Chama / Investment Club" },
  { key: "investment", label: "Investment"           },
  { key: "welfare",    label: "Welfare"              },
  { key: "emergency",  label: "Emergency Fund"       },
  { key: "business",   label: "Business"             },
];

export default function CreateCommunityScreen() {
  const [name, setName]               = useState("");
  const [description, setDescription] = useState("");
  const [hasWelfare, setHasWelfare]   = useState(false);
  const [hasShares, setHasShares]     = useState(false);
  const [sharePrice, setSharePrice]   = useState("100");
  // Single access-level selector — replaces the old isPublic + joinPolicy pair.
  // 'private'        → is_private=true,  join_policy='invite_only'
  // 'public_request' → is_private=false, join_policy='request'
  // 'public_open'    → is_private=false, join_policy='open'
  type AccessLevel = 'private' | 'public_request' | 'public_open';
  const [accessLevel,  setAccessLevel]  = useState<AccessLevel>("private");

  const [category, setCategory]       = useState("general");
  const [location, setLocation]       = useState("");
  const [showCatPicker, setShowCatPicker] = useState(false);
  const [saving, setSaving]           = useState(false);

  // Section A governance settings (other 4 — access is handled by accessLevel)
  const [invitePermission,       setInvitePermission]       = useState<InvitePermission>("admins");
  const [contributionPermission, setContributionPermission] = useState<ContributionPermission>("admins");
  const [memberListVisibility,   setMemberListVisibility]   = useState<MemberListVisibility>("all");
  const [maxMembers,             setMaxMembers]             = useState("");

  const isPublic = accessLevel !== 'private';

  const categoryLabel = CATEGORIES.find((c) => c.key === category)?.label ?? "General";

  const handleSave = async () => {
    if (!name.trim()) {
      Alert.alert("Name required", "Please choose a name for your community.");
      return;
    }
    setSaving(true);
    try {
      const c = await createCommunity({
        name:                    name.trim(),
        description:             description.trim() || undefined,
        has_welfare_fund:        hasWelfare,
        has_shares_fund:         hasShares,
        share_price:             hasShares ? Number(sharePrice) : undefined,
        is_private:  accessLevel === 'private',
        join_policy: accessLevel === 'private'        ? 'invite_only'
                   : accessLevel === 'public_request' ? 'request'
                   : 'open',
        category,
        location: location.trim() || undefined,
        invite_permission:       invitePermission,
        contribution_permission: contributionPermission,
        member_list_visibility:  memberListVisibility,
        max_members:             maxMembers ? Number(maxMembers) : undefined,
      } as any);
      router.replace({ pathname: `/community/${c.id}`, params: { name: c.name } });
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.name?.[0] || "Failed to create community.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader title="Create a Community" variant="light" leading="back" />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        {/* Photo picker placeholder */}
        <TouchableOpacity style={styles.photoBox} activeOpacity={0.7}>
          <Ionicons name="camera-outline" size={40} color={COLORS.textMuted} />
        </TouchableOpacity>

        <TextInput
          placeholder="Choose the name of your Community"
          placeholderTextColor={COLORS.textMuted}
          value={name}
          onChangeText={setName}
          style={styles.input}
          autoFocus
        />

        <TextInput
          placeholder="Description (optional)"
          placeholderTextColor={COLORS.textMuted}
          value={description}
          onChangeText={setDescription}
          style={[styles.input, styles.textarea]}
          multiline
        />

        {/* ── Community Access (single selector) ──────────────────── */}
        <Text style={styles.sectionTitle}>Community Access</Text>

        {([
          {
            value:   'private' as AccessLevel,
            icon:    'lock-closed-outline',
            label:   'Private',
            desc:    'Not discoverable. Members join via invite link only.',
          },
          {
            value:   'public_request' as AccessLevel,
            icon:    'people-outline',
            label:   'Public — approval required',
            desc:    'Appears in Discover. Anyone can request to join; an admin must approve.',
          },
          {
            value:   'public_open' as AccessLevel,
            icon:    'earth-outline',
            label:   'Public — open',
            desc:    'Appears in Discover. Any WEPL user can join immediately.',
          },
        ]).map(opt => (
          <TouchableOpacity
            key={opt.value}
            style={[styles.optRow, accessLevel === opt.value && styles.optRowActive]}
            onPress={() => setAccessLevel(opt.value)}
            activeOpacity={0.7}
          >
            <View style={[styles.radio, accessLevel === opt.value && styles.radioActive]}>
              {accessLevel === opt.value && <View style={styles.radioDot} />}
            </View>
            <View style={[styles.toggleIcon, { backgroundColor: COLORS.primary + "18" }]}>
              <Ionicons name={opt.icon as any} size={18} color={COLORS.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.optLabel, accessLevel === opt.value && { color: COLORS.primary }]}>
                {opt.label}
              </Text>
              <Text style={styles.optDesc}>{opt.desc}</Text>
            </View>
          </TouchableOpacity>
        ))}

        {/* Category & Location — only relevant when public (helps Discover filtering) */}
        {isPublic && (
          <>
            <Text style={styles.label}>Category</Text>
            <TouchableOpacity style={styles.picker} onPress={() => setShowCatPicker(true)}>
              <Text style={styles.pickerText}>{categoryLabel}</Text>
              <Ionicons name="chevron-down" size={16} color={COLORS.textMuted} />
            </TouchableOpacity>

            <Text style={styles.label}>Location (optional)</Text>
            <TextInput
              placeholder="e.g. Nairobi, Westlands"
              placeholderTextColor={COLORS.textMuted}
              value={location}
              onChangeText={setLocation}
              style={styles.input}
            />
            <Text style={styles.hint}>Helps members nearby find your community.</Text>
          </>
        )}

        {/* Community funds */}
        <Text style={styles.sectionTitle}>Community Funds</Text>

        <View style={styles.toggleRow}>
          <View style={styles.toggleIcon}>
            <Ionicons name="heart-outline" size={20} color="#c0392b" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleLabel}>Welfare Fund</Text>
            <Text style={styles.toggleDesc}>A shared emergency pool — members submit claims, others vote to release funds.</Text>
          </View>
          <Switch
            value={hasWelfare}
            onValueChange={setHasWelfare}
            trackColor={{ true: COLORS.primary }}
            thumbColor={COLORS.white}
          />
        </View>

        <View style={styles.toggleRow}>
          <View style={styles.toggleIcon}>
            <Ionicons name="stats-chart-outline" size={20} color={COLORS.accent} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleLabel}>Shares Fund</Text>
            <Text style={styles.toggleDesc}>Members earn shares and track their ownership stake in community funds.</Text>
          </View>
          <Switch
            value={hasShares}
            onValueChange={setHasShares}
            trackColor={{ true: COLORS.primary }}
            thumbColor={COLORS.white}
          />
        </View>

        {hasShares && (
          <>
            <Text style={styles.label}>Share price (KES per share)</Text>
            <TextInput
              placeholder="100"
              placeholderTextColor={COLORS.textMuted}
              value={sharePrice}
              onChangeText={setSharePrice}
              style={styles.input}
              keyboardType="numeric"
            />
            <Text style={styles.hint}>e.g. KES 100 per share — KES 1,000 contribution = 10 shares.</Text>
          </>
        )}

        {/* ── Section A: Governance Settings ──────────────────────── */}
        <Text style={styles.sectionTitle}>Access & Governance</Text>

        {/* 1. Who can invite members */}
        <Text style={[styles.label, { marginTop: 16 }]}>Who can invite members?</Text>
        {([
          { value: 'admins',  label: 'Admins & Treasurers', desc: 'Only privileged roles can share the invite link.' },
          { value: 'members', label: 'Any member',          desc: 'Every member can share the invite link.' },
          { value: 'creator', label: 'Creator only',        desc: 'Only the group creator can invite.' },
        ] as { value: InvitePermission; label: string; desc: string }[]).map(opt => (
          <TouchableOpacity
            key={opt.value}
            style={[styles.optRow, invitePermission === opt.value && styles.optRowActive]}
            onPress={() => setInvitePermission(opt.value)}
            activeOpacity={0.7}
          >
            <View style={[styles.radio, invitePermission === opt.value && styles.radioActive]}>
              {invitePermission === opt.value && <View style={styles.radioDot} />}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.optLabel, invitePermission === opt.value && { color: COLORS.primary }]}>{opt.label}</Text>
              <Text style={styles.optDesc}>{opt.desc}</Text>
            </View>
          </TouchableOpacity>
        ))}

        {/* 3. Who can create contributions */}
        <Text style={[styles.label, { marginTop: 16 }]}>Who can create contributions?</Text>
        {([
          { value: 'admins',  label: 'Admins & Treasurers', desc: 'Keeps tight control over what pools are created.' },
          { value: 'members', label: 'Any member',          desc: 'Any member can propose a contribution.' },
        ] as { value: ContributionPermission; label: string; desc: string }[]).map(opt => (
          <TouchableOpacity
            key={opt.value}
            style={[styles.optRow, contributionPermission === opt.value && styles.optRowActive]}
            onPress={() => setContributionPermission(opt.value)}
            activeOpacity={0.7}
          >
            <View style={[styles.radio, contributionPermission === opt.value && styles.radioActive]}>
              {contributionPermission === opt.value && <View style={styles.radioDot} />}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.optLabel, contributionPermission === opt.value && { color: COLORS.primary }]}>{opt.label}</Text>
              <Text style={styles.optDesc}>{opt.desc}</Text>
            </View>
          </TouchableOpacity>
        ))}

        {/* 4. Member list visibility */}
        <Text style={[styles.label, { marginTop: 16 }]}>Who can see the member list?</Text>
        {([
          { value: 'all',    label: 'All members', desc: 'Every member can see who else is in the group.' },
          { value: 'admins', label: 'Admins only', desc: 'Only admins see the full list; others see only themselves.' },
        ] as { value: MemberListVisibility; label: string; desc: string }[]).map(opt => (
          <TouchableOpacity
            key={opt.value}
            style={[styles.optRow, memberListVisibility === opt.value && styles.optRowActive]}
            onPress={() => setMemberListVisibility(opt.value)}
            activeOpacity={0.7}
          >
            <View style={[styles.radio, memberListVisibility === opt.value && styles.radioActive]}>
              {memberListVisibility === opt.value && <View style={styles.radioDot} />}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.optLabel, memberListVisibility === opt.value && { color: COLORS.primary }]}>{opt.label}</Text>
              <Text style={styles.optDesc}>{opt.desc}</Text>
            </View>
          </TouchableOpacity>
        ))}

        {/* 5. Maximum members cap */}
        <Text style={[styles.label, { marginTop: 16 }]}>Maximum members (optional)</Text>
        <TextInput
          placeholder="No limit"
          placeholderTextColor={COLORS.textMuted}
          value={maxMembers}
          onChangeText={setMaxMembers}
          style={styles.input}
          keyboardType="numeric"
        />
        <Text style={styles.hint}>Leave blank for unlimited. You can adjust this later.</Text>

        <View style={{ height: 100 }} />
      </ScrollView>
      </KeyboardAvoidingView>

      <FAB icon="check" onPress={handleSave} disabled={saving} loading={saving} />

      {/* Category picker modal */}
      <Modal
        visible={showCatPicker}
        transparent
        animationType="slide"
        onRequestClose={() => setShowCatPicker(false)}
      >
        <Pressable style={styles.modalBackdrop} onPress={() => setShowCatPicker(false)}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>Community Category</Text>
            {CATEGORIES.map((c) => (
              <TouchableOpacity
                key={c.key}
                style={[styles.modalOption, category === c.key && styles.modalOptionActive]}
                onPress={() => { setCategory(c.key); setShowCatPicker(false); }}
              >
                <Text style={[styles.modalOptionText, category === c.key && styles.modalOptionTextActive]}>
                  {c.label}
                </Text>
                {category === c.key && (
                  <Ionicons name="checkmark" size={18} color={COLORS.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  body: { paddingHorizontal: 24, paddingTop: 16, alignItems: "center" },

  photoBox: {
    width: 140, height: 140,
    borderRadius: RADIUS.full,
    backgroundColor: COLORS.divider,
    justifyContent: "center", alignItems: "center",
    marginBottom: 22,
  },

  input: {
    width: "100%",
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 14,
    fontSize: FONTS.md,
    color: COLORS.text,
    backgroundColor: COLORS.white,
    marginBottom: 12,
  },
  textarea: { height: 90, textAlignVertical: "top" },

  sectionTitle: {
    alignSelf: "flex-start",
    fontSize: FONTS.md,
    fontWeight: "700",
    color: COLORS.text,
    marginTop: 8,
    marginBottom: 4,
  },

  // Governance option rows
  optRow: {
    flexDirection: "row", alignItems: "flex-start", gap: 12,
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: RADIUS.md, padding: 12,
    backgroundColor: COLORS.white, marginBottom: 8,
  },
  optRowActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primaryPale },
  optLabel:     { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  optDesc:      { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },
  radio:        { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: COLORS.border, justifyContent: "center", alignItems: "center", marginTop: 2, flexShrink: 0 },
  radioActive:  { borderColor: COLORS.primary },
  radioDot:     { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },

  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    width: "100%",
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
    backgroundColor: COLORS.white,
  },
  toggleIcon: {
    width: 36, height: 36,
    borderRadius: RADIUS.full,
    backgroundColor: COLORS.background,
    justifyContent: "center", alignItems: "center",
  },
  toggleLabel: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  toggleDesc:  { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  label: {
    alignSelf: "flex-start",
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginTop: 16, marginBottom: 8,
    textTransform: "uppercase", letterSpacing: 0.4,
  },
  hint: { alignSelf: "flex-start", fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 4, lineHeight: 18 },


  // Picker
  picker: {
    flexDirection:   "row",
    alignItems:      "center",
    justifyContent:  "space-between",
    width:           "100%",
    borderWidth:     1.5,
    borderColor:     COLORS.border,
    borderRadius:    RADIUS.md,
    padding:         14,
    backgroundColor: COLORS.white,
    marginBottom:    12,
  },
  pickerText: {
    fontSize: FONTS.md,
    color:    COLORS.text,
  },

  // Modal
  modalBackdrop: {
    flex:            1,
    backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent:  "flex-end",
  },
  modalSheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius:  RADIUS.lg,
    borderTopRightRadius: RADIUS.lg,
    paddingTop:      12,
    paddingBottom:   36,
    paddingHorizontal: 20,
  },
  modalHandle: {
    width:           40,
    height:          4,
    borderRadius:    RADIUS.full,
    backgroundColor: COLORS.border,
    alignSelf:       "center",
    marginBottom:    16,
  },
  modalTitle: {
    fontSize:     FONTS.lg,
    fontWeight:   "700",
    color:        COLORS.text,
    marginBottom: 12,
  },
  modalOption: {
    flexDirection:   "row",
    alignItems:      "center",
    justifyContent:  "space-between",
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },
  modalOptionActive: {
    // no bg change — just show checkmark
  },
  modalOptionText: {
    fontSize:   FONTS.md,
    color:      COLORS.text,
  },
  modalOptionTextActive: {
    fontWeight: "700",
    color:      COLORS.primary,
  },
});
