import { useState, useCallback } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, Pressable,
  ActivityIndicator, Alert, TextInput, Modal, ScrollView,
  KeyboardAvoidingView, Platform, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as storage from "../../utils/secureStorage";
import { getProfile, updateProfile } from "../../api/auth";
import { getFinancialSummary } from "../../api/activity";
import { getUpcomingReminders, Reminder } from "../../api/reminders";
import { COLORS, FONTS, RADIUS, avatarColorFor, initialsFor } from "../../constants/theme";

type Profile = { phone_number: string; name: string; bio: string | null };

const REMINDER_TYPE_ICON: Record<string, string> = {
  contribution_due:  "alarm",
  welfare_contrib:   "heart",
  advance_repayment: "cash",
  standing_order:    "repeat",
  custom:            "notifications",
};

const KYC_STATUS = {
  approved:      { label: "KYC Verified",     color: COLORS.success,  bg: COLORS.primaryPale, icon: "shield-checkmark" },
  pending:       { label: "KYC Pending",       color: COLORS.warning,  bg: "#FFF8E7",          icon: "time" },
  rejected:      { label: "KYC Rejected",      color: COLORS.error,    bg: "#FEF2F2",          icon: "close-circle" },
  not_submitted: { label: "Complete KYC",      color: COLORS.textMuted, bg: COLORS.background, icon: "document-text" },
};

function fmtKES(n: number) {
  if (n >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `KES ${(n / 1_000).toFixed(1)}K`;
  return `KES ${n.toLocaleString()}`;
}

export default function ProfileScreen() {
  const [profile,   setProfile]   = useState<Profile | null>(null);
  const [summary,   setSummary]   = useState<any>(null);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showEdit,   setShowEdit]   = useState(false);
  const [editName,   setEditName]   = useState("");
  const [editBio,    setEditBio]    = useState("");
  const [saving,     setSaving]     = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, s, rem] = await Promise.all([
        getProfile(),
        getFinancialSummary().catch(() => null),
        getUpcomingReminders(3).catch(() => []),
      ]);
      setProfile(p);
      setSummary(s);
      setReminders(rem);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => {
    load().finally(() => setLoading(false));
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const openEdit = () => {
    setEditName(profile?.name ?? "");
    setEditBio(profile?.bio ?? "");
    setShowEdit(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await updateProfile({ name: editName.trim(), bio: editBio.trim() });
      setProfile(updated);
      setShowEdit(false);
    } catch {
      Alert.alert("Error", "Could not save profile.");
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    Alert.alert("Log out", "You'll need your PIN to log back in.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Log out", style: "destructive",
        onPress: async () => {
          await storage.multiRemove(["access", "refresh", "phone", "name"]);
          router.replace("/login");
        },
      },
    ]);
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  const phone       = profile?.phone_number ?? "";
  const name        = profile?.name || "";
  const displayName = name || phone;
  const palette     = avatarColorFor(phone || "u");
  const kycInfo     = KYC_STATUS[summary?.kyc_status as keyof typeof KYC_STATUS ?? "not_submitted"]
                      ?? KYC_STATUS.not_submitted;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        contentContainerStyle={{ paddingBottom: 48 }}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <View style={styles.hero}>
          <View style={[styles.avatar, { backgroundColor: palette.bg }]}>
            <Text style={[styles.avatarText, { color: palette.text }]}>
              {initialsFor(displayName)}
            </Text>
          </View>
          <Text style={styles.heroName}>{name || "Set your name"}</Text>
          <Text style={styles.heroPhone}>{phone}</Text>
          {profile?.bio ? <Text style={styles.heroBio}>{profile.bio}</Text> : null}

          {/* KYC badge */}
          <TouchableOpacity
            style={[styles.kycBadge, { backgroundColor: kycInfo.bg }]}
            onPress={() => router.push("/kyc")}
          >
            <Ionicons name={kycInfo.icon as any} size={13} color={kycInfo.color} />
            <Text style={[styles.kycBadgeText, { color: kycInfo.color }]}>{kycInfo.label}</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.editBtn} onPress={openEdit}>
            <Ionicons name="pencil-outline" size={13} color={COLORS.primary} />
            <Text style={styles.editBtnText}>Edit Profile</Text>
          </TouchableOpacity>

          {summary?.member_since && (
            <Text style={styles.memberSince}>
              Member since {new Date(summary.member_since).toLocaleDateString("en-KE", { month: "long", year: "numeric" })}
            </Text>
          )}
        </View>

        {/* ── Financial Snapshot ───────────────────────────────────────── */}
        {summary && (
          <View style={styles.section}>
            <SectionHeader title="Financial Snapshot" onAction={() => router.push("/(drawer)/reports")} actionLabel="Full Report" />
            <View style={styles.statsGrid}>
              <StatCard
                icon="arrow-up-circle" iconColor={COLORS.primary}
                label="Total Saved"
                value={fmtKES(summary.total_contributed)}
                sub={summary.this_month > 0 ? `+${fmtKES(summary.this_month)} this month` : undefined}
              />
              <StatCard
                icon="wallet" iconColor={COLORS.accent}
                label="Active Pools"
                value={String(summary.active_contributions)}
                sub={`${summary.total_contributions} total joined`}
              />
            </View>
            <View style={[styles.statsGrid, { marginTop: 10 }]}>
              <StatCard
                icon="receipt" iconColor="#0891B2"
                label="Transactions"
                value={String(summary.tx_count)}
                sub={summary.total_received > 0 ? `${fmtKES(summary.total_received)} received` : undefined}
              />
              {summary.pending_advances > 0 ? (
                <StatCard
                  icon="flash" iconColor={COLORS.warning}
                  label="Advance Due"
                  value={fmtKES(summary.advance_balance_due)}
                  sub={`${summary.pending_advances} active advance`}
                  highlight
                />
              ) : (
                <StatCard
                  icon="checkmark-circle" iconColor={COLORS.success}
                  label="No Outstanding"
                  value="All clear"
                  sub="No advances due"
                />
              )}
            </View>

            {/* Monthly mini-bar chart */}
            {summary.monthly_trend && summary.monthly_trend.length > 1 && (
              <MiniBarChart data={summary.monthly_trend} />
            )}
          </View>
        )}

        {/* ── Activity ─────────────────────────────────────────────────── */}
        <TouchableOpacity
          style={styles.activityBanner}
          onPress={() => router.push("/activity")}
          activeOpacity={0.82}
        >
          <View style={styles.activityBannerIcon}>
            <Ionicons name="pulse" size={20} color={COLORS.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.activityBannerTitle}>Activity Feed</Text>
            <Text style={styles.activityBannerSub}>View your full transaction & event history</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
        </TouchableOpacity>

        {/* ── Upcoming Reminders ───────────────────────────────────────── */}
        <View style={styles.section}>
          <SectionHeader
            title="Reminders"
            onAction={() => router.push("/reminders")}
            actionLabel="Manage"
          />
          {reminders.length === 0 ? (
            <TouchableOpacity style={styles.addReminderRow} onPress={() => router.push("/reminders")}>
              <View style={[styles.activityIcon, { backgroundColor: COLORS.primaryPale }]}>
                <Ionicons name="add" size={16} color={COLORS.primary} />
              </View>
              <Text style={styles.addReminderText}>Set a contribution reminder</Text>
            </TouchableOpacity>
          ) : (
            reminders.map((r) => (
              <TouchableOpacity key={r.id} style={styles.reminderRow} onPress={() => router.push("/reminders")}>
                <View style={[styles.activityIcon, { backgroundColor: COLORS.primaryPale }]}>
                  <Ionicons name={REMINDER_TYPE_ICON[r.reminder_type] as any ?? "alarm"} size={16} color={COLORS.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.reminderTitle} numberOfLines={1}>{r.title}</Text>
                  <Text style={styles.reminderTime}>
                    {r.recurrence !== "none" ? `${r.recurrence.charAt(0).toUpperCase() + r.recurrence.slice(1)} · ` : ""}
                    {new Date(r.next_fire_at).toLocaleDateString("en-KE", { weekday: "short", month: "short", day: "numeric" })}
                  </Text>
                </View>
                {r.is_overdue && (
                  <View style={styles.overdueChip}>
                    <Text style={styles.overdueText}>Due</Text>
                  </View>
                )}
              </TouchableOpacity>
            ))
          )}
        </View>

        {/* ── Menu ─────────────────────────────────────────────────────── */}
        <View style={[styles.section, { paddingHorizontal: 0, paddingVertical: 0 }]}>
          <MenuItem icon="compass-outline"             label="Discover Groups & Campaigns" onPress={() => router.push("/discover")} />
          <MenuItem icon="document-text-outline"      label="Reports & Statements" onPress={() => router.push("/(drawer)/reports")} />
          <MenuItem icon="shield-checkmark-outline"   label="Security & PIN"       onPress={() => router.push("/pin")} />
          <MenuItem icon="people-outline"             label="Invite a friend"      onPress={() => router.push("/(drawer)/invite")} />
          <MenuItem icon="settings-outline"           label="Settings"             onPress={() => router.push("/(drawer)/settings")} />
          <MenuItem icon="help-circle-outline"        label="Help & Support"       onPress={() => {}} last />
        </View>

        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={18} color={COLORS.error} />
          <Text style={styles.logoutText}>Log out</Text>
        </TouchableOpacity>
      </ScrollView>

      {/* Edit Profile Modal */}
      <Modal visible={showEdit} transparent animationType="slide" onRequestClose={() => setShowEdit(false)}>
        <KeyboardAvoidingView style={{ flex: 1, justifyContent: "flex-end" }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <Pressable style={StyleSheet.absoluteFillObject} onPress={() => setShowEdit(false)} />
          <View style={styles.modal} onStartShouldSetResponder={() => true}>
            <View style={styles.sheetHandle} />
            <Text style={styles.modalTitle}>Edit Profile</Text>

            <Text style={styles.fieldLabel}>Full Name</Text>
            <TextInput
              value={editName}
              onChangeText={setEditName}
              placeholder="Your full name"
              placeholderTextColor={COLORS.textMuted}
              style={styles.input}
              autoFocus
            />

            <Text style={styles.fieldLabel}>Bio</Text>
            <TextInput
              value={editBio}
              onChangeText={setEditBio}
              placeholder="A short bio (optional)"
              placeholderTextColor={COLORS.textMuted}
              style={[styles.input, { height: 80, textAlignVertical: "top" }]}
              multiline
            />

            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowEdit(false)}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
                {saving
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={styles.saveText}>Save</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ title, onAction, actionLabel }: { title: string; onAction?: () => void; actionLabel?: string }) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {onAction && (
        <TouchableOpacity onPress={onAction} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Text style={styles.sectionAction}>{actionLabel ?? "See all"}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

function StatCard({
  icon, iconColor, label, value, sub, highlight,
}: {
  icon: string; iconColor: string; label: string; value: string; sub?: string; highlight?: boolean;
}) {
  return (
    <View style={[styles.statCard, highlight && styles.statCardHighlight]}>
      <View style={[styles.statIcon, { backgroundColor: iconColor + "18" }]}>
        <Ionicons name={icon as any} size={18} color={iconColor} />
      </View>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
      {sub && <Text style={styles.statSub}>{sub}</Text>}
    </View>
  );
}

function MiniBarChart({ data }: { data: { month: string; amount: number }[] }) {
  const max = Math.max(...data.map((d) => d.amount), 1);
  return (
    <View style={styles.chartWrap}>
      <Text style={styles.chartTitle}>Monthly Contributions</Text>
      <View style={styles.chartBars}>
        {data.map((d) => {
          const pct = (d.amount / max) * 100;
          return (
            <View key={d.month} style={styles.chartCol}>
              <View style={styles.chartBarBg}>
                <View style={[styles.chartBar, { height: `${Math.max(pct, 4)}%` }]} />
              </View>
              <Text style={styles.chartLabel}>{d.month.split(" ")[0]}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function MenuItem({ icon, label, onPress, last }: { icon: string; label: string; onPress: () => void; last?: boolean }) {
  return (
    <TouchableOpacity
      style={[styles.menuRow, last && { borderBottomWidth: 0 }]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={styles.menuIconWrap}>
        <Ionicons name={icon as any} size={19} color={COLORS.primary} />
      </View>
      <Text style={styles.menuLabel}>{label}</Text>
      <Ionicons name="chevron-forward" size={15} color={COLORS.textMuted} />
    </TouchableOpacity>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  // Hero
  hero: {
    alignItems: "center",
    paddingTop: 28, paddingBottom: 20,
    backgroundColor: COLORS.white,
    marginBottom: 10,
  },
  avatar: {
    width: 84, height: 84, borderRadius: RADIUS.full,
    justifyContent: "center", alignItems: "center",
    marginBottom: 12,
    shadowColor: "#000", shadowOpacity: 0.08, shadowRadius: 8, shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  avatarText:  { fontSize: 32, fontWeight: "700" },
  heroName:    { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, marginBottom: 2 },
  heroPhone:   { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 6 },
  heroBio:     { fontSize: FONTS.sm, color: COLORS.textSecondary, textAlign: "center", paddingHorizontal: 40, marginBottom: 10, lineHeight: 18 },
  memberSince: { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 8 },

  kycBadge: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 12, paddingVertical: 5,
    borderRadius: RADIUS.full, marginBottom: 8,
  },
  kycBadgeText: { fontSize: FONTS.xs, fontWeight: "700" },

  editBtn: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 14, paddingVertical: 7,
    borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.primary,
  },
  editBtnText: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },

  // Sections
  section: {
    backgroundColor: COLORS.white,
    marginHorizontal: 0, marginBottom: 10,
    paddingHorizontal: 16, paddingVertical: 14,
  },
  sectionHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginBottom: 12,
  },
  sectionTitle:  { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.text, textTransform: "uppercase", letterSpacing: 0.6 },
  sectionAction: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },
  emptyText:     { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", paddingVertical: 8 },

  // Stats grid
  statsGrid: { flexDirection: "row", gap: 10 },
  statCard: {
    flex: 1, backgroundColor: COLORS.background,
    borderRadius: RADIUS.md, padding: 14,
    borderWidth: 1, borderColor: COLORS.divider,
  },
  statCardHighlight: {
    borderColor: COLORS.warning + "60",
    backgroundColor: "#FFFBF0",
  },
  statIcon:  { width: 34, height: 34, borderRadius: RADIUS.md, justifyContent: "center", alignItems: "center", marginBottom: 8 },
  statValue: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginBottom: 2 },
  statLabel: { fontSize: FONTS.xs, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 0.4 },
  statSub:   { fontSize: FONTS.xs, color: COLORS.textSecondary, marginTop: 3 },

  // Bar chart
  chartWrap:  { marginTop: 16, paddingTop: 14, borderTopWidth: 1, borderTopColor: COLORS.divider },
  chartTitle: { fontSize: FONTS.xs, fontWeight: "700", color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 },
  chartBars:  { flexDirection: "row", alignItems: "flex-end", gap: 6, height: 80 },
  chartCol:   { flex: 1, alignItems: "center", height: "100%" },
  chartBarBg: { flex: 1, width: "100%", justifyContent: "flex-end", borderRadius: RADIUS.sm, overflow: "hidden", backgroundColor: COLORS.divider },
  chartBar:   { width: "100%", backgroundColor: COLORS.primary, borderRadius: RADIUS.sm },
  chartLabel: { fontSize: 9, color: COLORS.textMuted, marginTop: 4, fontWeight: "600" },

  // Activity banner
  activityBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: COLORS.white,
    marginBottom: 10,
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderLeftWidth: 3,
    borderLeftColor: COLORS.primary,
  },
  activityBannerIcon: {
    width: 40, height: 40,
    borderRadius: RADIUS.md,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center",
    alignItems: "center",
  },
  activityBannerTitle: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginBottom: 2 },
  activityBannerSub:   { fontSize: FONTS.sm, color: COLORS.textMuted },

  // Reminders
  reminderRow: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 9, gap: 12,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  reminderTitle: { fontSize: FONTS.sm, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  reminderTime:  { fontSize: FONTS.xs, color: COLORS.textSecondary },
  overdueChip:   { backgroundColor: COLORS.warning + "25", paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  overdueText:   { fontSize: FONTS.xs, color: COLORS.warning, fontWeight: "700" },
  addReminderRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingVertical: 9,
  },
  addReminderText: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },

  // Menu
  menuRow: {
    flexDirection: "row", alignItems: "center", gap: 14,
    paddingHorizontal: 16, paddingVertical: 15,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
    backgroundColor: COLORS.white,
  },
  menuIconWrap: {
    width: 36, height: 36, borderRadius: RADIUS.md,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center", alignItems: "center",
  },
  menuLabel: { flex: 1, fontSize: FONTS.md, color: COLORS.text, fontWeight: "500" },

  // Logout
  logoutBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    marginHorizontal: 16, marginTop: 6, marginBottom: 8,
    padding: 15, borderRadius: RADIUS.md,
    borderWidth: 1.5, borderColor: COLORS.error + "40",
    backgroundColor: COLORS.error + "08",
  },
  logoutText: { color: COLORS.error, fontSize: FONTS.md, fontWeight: "700" },

  // Modal
  sheetHandle: { width: 36, height: 4, borderRadius: 2, backgroundColor: COLORS.divider, alignSelf: "center", marginBottom: 18 },
  modal: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 22, borderTopRightRadius: 22,
    paddingHorizontal: 20, paddingBottom: 40, paddingTop: 14,
  },
  modalTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, marginBottom: 20 },
  fieldLabel: { fontSize: FONTS.xs, fontWeight: "700", color: COLORS.textSecondary, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background, marginBottom: 16,
  },
  modalActions: { flexDirection: "row", gap: 12, marginTop: 4 },
  cancelBtn: { flex: 1, padding: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, alignItems: "center" },
  cancelText: { color: COLORS.textSecondary, fontWeight: "600" },
  saveBtn:    { flex: 1, padding: 14, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: "center" },
  saveText:   { color: COLORS.white, fontWeight: "700" },
});
