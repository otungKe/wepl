import { useState, useCallback } from "react";
import {
  View, Text, ScrollView, StyleSheet,
  TouchableOpacity, Switch, Modal,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getPrivacyPrefs, updatePrivacyPrefs, type PrivacyPrefs, type Visibility } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

const DEFAULT: PrivacyPrefs = {
  phone_visibility:        "members",
  photo_visibility:        "everyone",
  contribution_visibility: "members",
  discoverable:            true,
  show_online_status:      true,
};

const VISIBILITY_LABELS: Record<Visibility, string> = {
  everyone: "Everyone",
  members:  "My communities only",
  nobody:   "Only me",
};

const VISIBILITY_OPTIONS: Visibility[] = ["everyone", "members", "nobody"];

// ─── Picker row — opens a bottom-sheet with radio options ────────────────────

function PickerRow({
  icon, label, desc, value, onChange,
}: {
  icon: string;
  label: string;
  desc: string;
  value: Visibility;
  onChange: (v: Visibility) => void;
}) {
  const [open, setOpen] = useState(false);

  const color =
    value === "everyone" ? COLORS.success :
    value === "members"  ? COLORS.primary :
    COLORS.textMuted;

  return (
    <>
      <TouchableOpacity style={s.row} onPress={() => setOpen(true)} activeOpacity={0.7}>
        <View style={[s.iconWrap, { backgroundColor: COLORS.primary + "18" }]}>
          <Ionicons name={icon as any} size={20} color={COLORS.primary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.rowLabel}>{label}</Text>
          <Text style={s.rowDesc}>{desc}</Text>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <View style={[s.badge, { backgroundColor: color + "18" }]}>
            <Text style={[s.badgeText, { color }]}>{VISIBILITY_LABELS[value]}</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
        </View>
      </TouchableOpacity>

      {/* Bottom-sheet picker */}
      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={{ flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.45)" }}>
          <TouchableOpacity style={{ ...StyleSheet.absoluteFillObject } as any} activeOpacity={1} onPress={() => setOpen(false)} />
          <View style={s.sheet}>
            <View style={s.sheetHandle} />
            <Text style={s.sheetTitle}>{label}</Text>
            <Text style={s.sheetSub}>{desc}</Text>

            {VISIBILITY_OPTIONS.map((opt) => {
              const selected = opt === value;
              const optColor =
                opt === "everyone" ? COLORS.success :
                opt === "members"  ? COLORS.primary :
                COLORS.textMuted;
              return (
                <TouchableOpacity
                  key={opt}
                  style={[s.option, selected && { borderColor: COLORS.primary, backgroundColor: COLORS.primaryPale }]}
                  onPress={() => { onChange(opt); setOpen(false); }}
                  activeOpacity={0.7}
                >
                  <View style={[s.optionIcon, { backgroundColor: optColor + "18" }]}>
                    <Ionicons
                      name={
                        opt === "everyone" ? "earth-outline" :
                        opt === "members"  ? "people-outline" :
                        "lock-closed-outline"
                      }
                      size={18}
                      color={optColor}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[s.optionLabel, selected && { color: COLORS.primary }]}>
                      {VISIBILITY_LABELS[opt]}
                    </Text>
                    <Text style={s.optionDesc}>
                      {opt === "everyone" ? "Visible to all WEPL users" :
                       opt === "members"  ? "Visible only to people in your communities" :
                       "Only visible to you"}
                    </Text>
                  </View>
                  <View style={[s.radio, selected && s.radioActive]}>
                    {selected && <View style={s.radioDot} />}
                  </View>
                </TouchableOpacity>
              );
            })}

            <TouchableOpacity style={s.cancelBtn} onPress={() => setOpen(false)}>
              <Text style={s.cancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </>
  );
}

// ─── Toggle row ──────────────────────────────────────────────────────────────

function ToggleRow({
  icon, label, desc, value, onChange,
}: {
  icon: string;
  label: string;
  desc: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <View style={s.row}>
      <View style={[s.iconWrap, { backgroundColor: COLORS.primary + "18" }]}>
        <Ionicons name={icon as any} size={20} color={COLORS.primary} />
      </View>
      <View style={{ flex: 1, marginRight: 8 }}>
        <Text style={s.rowLabel}>{label}</Text>
        <Text style={s.rowDesc}>{desc}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ true: COLORS.primary }}
        thumbColor={COLORS.white}
      />
    </View>
  );
}

// ─── Screen ──────────────────────────────────────────────────────────────────

export default function AccountPrivacyScreen() {
  const [prefs,   setPrefs]   = useState<PrivacyPrefs>(DEFAULT);
  const [saving,  setSaving]  = useState(false);
  const [loading, setLoading] = useState(true);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      getPrivacyPrefs()
        .then(p => setPrefs(p))
        .catch(() => {})  // keep defaults on error
        .finally(() => setLoading(false));
    }, [])
  );

  const update = async (patch: Partial<PrivacyPrefs>) => {
    const prev = prefs;
    const next = { ...prefs, ...patch };
    setPrefs(next);          // optimistic update
    setSaving(true);
    try {
      const saved = await updatePrivacyPrefs(patch);
      setPrefs(saved);       // sync with server response
    } catch {
      setPrefs(prev);        // revert on error
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader
        title="Account & Privacy"
        variant="light"
        leading="back"
        onBack={() => router.replace("/(drawer)/profile")}
        rightExtra={
          saving
            ? <Text style={{ fontSize: FONTS.xs, color: COLORS.textMuted, marginRight: 8 }}>Saving…</Text>
            : null
        }
      />

      <ScrollView contentContainerStyle={{ paddingBottom: 48 }}>

        {/* Profile visibility */}
        <Text style={s.section}>PROFILE</Text>
        <View style={s.card}>
          <PickerRow
            icon="call-outline"
            label="Phone number"
            desc="Who can see your phone number"
            value={prefs.phone_visibility}
            onChange={(v) => update({ phone_visibility: v })}
          />
          <View style={s.divider} />
          <PickerRow
            icon="image-outline"
            label="Profile photo"
            desc="Who can see your profile photo"
            value={prefs.photo_visibility}
            onChange={(v) => update({ photo_visibility: v })}
          />
          <View style={s.divider} />
          <ToggleRow
            icon="search-outline"
            label="Discoverable"
            desc="Allow others to find you when adding members to communities"
            value={prefs.discoverable}
            onChange={(v) => update({ discoverable: v })}
          />
          <View style={s.divider} />
          <ToggleRow
            icon="ellipse-outline"
            label="Online status"
            desc="Show when you were last active in chats"
            value={prefs.show_online_status}
            onChange={(v) => update({ show_online_status: v })}
          />
        </View>

        {/* Financial visibility */}
        <Text style={s.section}>FINANCIAL ACTIVITY</Text>
        <View style={s.card}>
          <PickerRow
            icon="wallet-outline"
            label="Contribution history"
            desc="Who can see your payment records within shared pools"
            value={prefs.contribution_visibility}
            onChange={(v) => update({ contribution_visibility: v })}
          />
        </View>

        {/* Data note */}
        <View style={s.note}>
          <Ionicons name="information-circle-outline" size={16} color={COLORS.textMuted} />
          <Text style={s.noteText}>
            These preferences control how your information is displayed to others within WEPL.
            Your phone number is always shared with community admins when you join a group.
          </Text>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },

  section: {
    fontSize: 11, fontWeight: "700", color: COLORS.textMuted,
    letterSpacing: 0.8, marginTop: 24, marginBottom: 8,
    paddingHorizontal: 20,
  },

  card: {
    backgroundColor: COLORS.white,
    marginHorizontal: 16,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    overflow: "hidden",
  },

  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 12,
  },
  iconWrap: {
    width: 38, height: 38,
    borderRadius: 10,
    justifyContent: "center",
    alignItems: "center",
    flexShrink: 0,
  },
  rowLabel: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  rowDesc:  { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },
  divider:  { height: 1, backgroundColor: COLORS.divider, marginLeft: 66 },

  badge: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: RADIUS.full,
  },
  badgeText: { fontSize: 12, fontWeight: "700" },

  // Bottom-sheet
  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    padding: 24, paddingBottom: 40,
  },
  sheetHandle: { width: 40, height: 4, backgroundColor: COLORS.border, borderRadius: 2, alignSelf: "center", marginBottom: 20 },
  sheetTitle:  { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, marginBottom: 4 },
  sheetSub:    { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18, marginBottom: 20 },

  option: {
    flexDirection: "row", alignItems: "center", gap: 12,
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: RADIUS.md, padding: 14, marginBottom: 10,
    backgroundColor: COLORS.white,
  },
  optionIcon:  { width: 36, height: 36, borderRadius: 10, justifyContent: "center", alignItems: "center" },
  optionLabel: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  optionDesc:  { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  radio:      { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: COLORS.border, justifyContent: "center", alignItems: "center" },
  radioActive:{ borderColor: COLORS.primary },
  radioDot:   { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },

  cancelBtn:  { marginTop: 6, padding: 14, borderRadius: RADIUS.md, alignItems: "center", borderWidth: 1.5, borderColor: COLORS.border },
  cancelText: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.textSecondary },

  note: {
    flexDirection: "row", alignItems: "flex-start", gap: 10,
    marginHorizontal: 20, marginTop: 16,
  },
  noteText: { flex: 1, fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },
});
