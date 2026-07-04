import { useState, useCallback } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, Pressable,
  ActivityIndicator, Alert, TextInput, Modal, ScrollView,
  KeyboardAvoidingView, Platform, RefreshControl, Linking, Image,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { suppressNextLock } from "../../utils/lockSuppress";
import { getProfile, updateProfile } from "../../api/auth";
import { getFinancialSummary } from "../../api/activity";
import { discoverCommunities, type Community } from "../../api/communities";
import { getCampaigns, type Campaign } from "../../api/discover";
import { getUpcomingReminders, type Reminder } from "../../api/reminders";
import { COLORS, FONTS, RADIUS, avatarColorFor, initialsFor } from "../../constants/theme";
import API from "../../api/client";

type KYCStatus = "approved" | "pending" | "rejected" | "not_submitted";

const KYC_CONFIG: Record<KYCStatus, {
  label: string; color: string; bg: string; icon: string; cta: string;
}> = {
  approved:      { label: "Verified",        color: COLORS.success,  bg: COLORS.primaryPale, icon: "shield-checkmark", cta: "" },
  pending:       { label: "Pending Review",   color: "#B45309",       bg: "#FEF3C7",          icon: "time",             cta: "View Status" },
  rejected:      { label: "Action Required",  color: COLORS.error,    bg: "#FEF2F2",          icon: "alert-circle",     cta: "Re-submit" },
  not_submitted: { label: "Not Verified",     color: COLORS.textMuted, bg: COLORS.background, icon: "shield-outline",   cta: "Verify Now" },
};

function fmtKES(n: number) {
  if (n >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `KES ${(n / 1_000).toFixed(1)}K`;
  return `KES ${n.toLocaleString()}`;
}

export default function ProfileScreen() {
  const [profile,      setProfile]      = useState<any>(null);
  const [summary,      setSummary]      = useState<any>(null);
  const [communities,  setCommunities]  = useState<Community[]>([]);
  const [campaigns,    setCampaigns]    = useState<Campaign[]>([]);
  const [reminders,    setReminders]    = useState<Reminder[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [refreshing,   setRefreshing]   = useState(false);
  const [showEdit,     setShowEdit]     = useState(false);
  const [editName,     setEditName]     = useState("");
  const [editBio,      setEditBio]      = useState("");
  const [saving,       setSaving]       = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        getProfile(),
        getFinancialSummary().catch(() => null),
      ]);
      setProfile(p);
      setSummary(s);
      // Load public communities for the locked discover section
      // (shown to unverified users so they can see what's available)
      discoverCommunities({ limit: 10 })
        .then(res => setCommunities(res.results))
        .catch(() => {});

      // Public campaigns for the discover section (matches web Tier-0 profile).
      getCampaigns({ limit: 3 })
        .then(res => setCampaigns(res.results))
        .catch(() => {});

      getUpcomingReminders(3)
        .then(setReminders)
        .catch(() => {});
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
      // Keep SecureStore in sync so the welcome-back screen shows the latest name.
      if (editName.trim()) {
        const storage = await import("../../utils/secureStorage");
        await storage.setItem("name", editName.trim());
      }
      setShowEdit(false);
    } catch {
      Alert.alert("Error", "Could not save profile.");
    } finally {
      setSaving(false);
    }
  };

  const pickPhoto = async () => {
    // Ask for permission first
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "Allow access to your photos to update your profile picture.");
      return;
    }

    // Suppress the session lock for this background trip — the image picker
    // opens the system photo library as a separate activity on Android, which
    // triggers AppState 'background' → 'active'. Without this, the lock screen
    // appears on return and the user cannot complete the photo selection.
    suppressNextLock();

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsEditing: true,
      aspect:        [1, 1],   // square crop
      quality:       0.75,
    });

    if (result.canceled) return;

    const asset = result.assets[0];
    const uri   = asset.uri;
    const name  = uri.split("/").pop() ?? "photo.jpg";
    const type  = asset.mimeType ?? "image/jpeg";

    setUploadingPhoto(true);
    try {
      const form = new FormData();
      form.append("profile_photo", { uri, name, type } as any);
      const { data } = await API.patch("users/profile/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      console.log("[profile photo] server returned:", JSON.stringify(data.profile_photo));
      if (data.profile_photo) {
        setProfile((p: any) => ({ ...p, profile_photo: data.profile_photo }));
      } else {
        // Photo was not saved — re-fetch full profile to get current state
        const fresh = await API.get("users/profile/");
        console.log("[profile photo] re-fetched:", JSON.stringify(fresh.data.profile_photo));
        setProfile(fresh.data);
      }
    } catch (e: any) {
      console.error("[profile photo] upload error:", e?.response?.status, e?.response?.data);
      Alert.alert("Error", "Could not upload photo. Please try again.");
    } finally {
      setUploadingPhoto(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  const phone       = profile?.phone_number ?? "";
  const name        = profile?.name ?? "";
  const displayName = name || phone;
  const palette     = avatarColorFor(phone || "u");
  const kycStatus   = (summary?.kyc_status ?? "not_submitted") as KYCStatus;
  const kyc         = KYC_CONFIG[kycStatus] ?? KYC_CONFIG.not_submitted;
  const isVerified  = kycStatus === "approved";

  return (
    <SafeAreaView style={s.safe} edges={["top", "left", "right"]}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        contentContainerStyle={{ paddingBottom: 56 }}
        showsVerticalScrollIndicator={false}
      >

        {/* ── Hero ────────────────────────────────────────────────────── */}
        <View style={s.hero}>
          {/* Avatar — tap to change photo */}
          <TouchableOpacity onPress={pickPhoto} activeOpacity={0.85} disabled={uploadingPhoto}>
            <View style={[s.avatar, { backgroundColor: palette.bg }]}>
              {uploadingPhoto ? (
                <ActivityIndicator color={palette.text} />
              ) : profile?.profile_photo ? (
                <Image
                  source={{ uri: profile.profile_photo }}
                  style={s.avatarImage}
                  resizeMode="cover"
                />
              ) : (
                <Text style={[s.avatarInitials, { color: palette.text }]}>
                  {initialsFor(displayName)}
                </Text>
              )}
            </View>
            <View style={s.avatarEditBadge}>
              <Ionicons name={uploadingPhoto ? "hourglass" : "camera"} size={11} color={COLORS.white} />
            </View>
          </TouchableOpacity>

          <Text style={s.heroName}>{name || "Set your name"}</Text>
          <Text style={s.heroPhone}>{phone}</Text>

          {/* KYC status badge */}
          <TouchableOpacity
            style={[s.kycBadge, { backgroundColor: kyc.bg }]}
            onPress={() => router.push("/verification")}
          >
            <Ionicons name={kyc.icon as any} size={13} color={kyc.color} />
            <Text style={[s.kycBadgeText, { color: kyc.color }]}>{kyc.label}</Text>
          </TouchableOpacity>

          {summary?.member_since ? (
            <Text style={s.memberSince}>
              Member since {new Date(summary.member_since).toLocaleDateString("en-KE", { month: "long", year: "numeric" })}
            </Text>
          ) : null}
        </View>

        {/* ── KYC CTA — shown for ALL non-verified users ───────────────── */}
        {!isVerified && (
          <View style={s.ctaCard}>
            <View style={s.ctaIconWrap}>
              <Ionicons name="shield-outline" size={28} color={COLORS.primary} />
            </View>
            <Text style={s.ctaTitle}>Verify your identity</Text>
            <Text style={s.ctaBody}>
              {kycStatus === "pending"
                ? "Your documents are under review. Most verifications are approved within 24 hours."
                : kycStatus === "rejected"
                ? "Your last submission was not approved. Please re-submit your documents to unlock all features."
                : "Complete a quick identity check to unlock payments, contributions, advances, and group savings."}
            </Text>
            <TouchableOpacity
              style={s.ctaBtn}
              onPress={() => router.push("/verification")}
            >
              <Ionicons name="arrow-forward-circle-outline" size={18} color={COLORS.white} />
              <Text style={s.ctaBtnText}>Open Verification Center</Text>
            </TouchableOpacity>

            {/* What gets unlocked */}
            {kycStatus === "not_submitted" && (
              <View style={s.unlockRow}>
                {["Payments", "Contributions", "Advances", "Communities"].map(f => (
                  <View key={f} style={s.unlockChip}>
                    <Ionicons name="lock-closed-outline" size={10} color={COLORS.textMuted} />
                    <Text style={s.unlockChipText}>{f}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* ── Financial Snapshot ──────────────────────────────────────── */}
        <View style={s.section}>
          <View style={s.sectionHead}>
            <Text style={s.sectionTitle}>Financial Snapshot</Text>
            {isVerified && (
              <TouchableOpacity onPress={() => router.push("/reports")}>
                <Text style={s.sectionAction}>Full Report</Text>
              </TouchableOpacity>
            )}
          </View>

          {isVerified && summary ? (
            /* Verified: show real data */
            <>
              <View style={s.statsGrid}>
                <StatCard
                  icon="arrow-up-circle" iconColor={COLORS.primary}
                  label="Total Saved"    value={fmtKES(summary.total_contributed)}
                  sub={summary.this_month > 0 ? `+${fmtKES(summary.this_month)} this month` : undefined}
                />
                <StatCard
                  icon="wallet"          iconColor={COLORS.accent}
                  label="Active Pools"   value={String(summary.active_contributions)}
                  sub={`${summary.total_contributions} total joined`}
                />
              </View>
              <View style={[s.statsGrid, { marginTop: 10 }]}>
                <StatCard
                  icon="receipt"         iconColor="#0891B2"
                  label="Transactions"   value={String(summary.tx_count)}
                  sub={summary.total_received > 0 ? `${fmtKES(summary.total_received)} received` : undefined}
                />
                {summary.pending_advances > 0 ? (
                  <StatCard
                    icon="flash"           iconColor={COLORS.warning}
                    label="Advance Due"    value={fmtKES(summary.advance_balance_due)}
                    sub={`${summary.pending_advances} active`}
                    highlight
                  />
                ) : (
                  <StatCard
                    icon="checkmark-circle" iconColor={COLORS.success}
                    label="No Outstanding"  value="All clear"
                    sub="No advances due"
                  />
                )}
              </View>
            </>
          ) : (
            /* Unverified: locked placeholders */
            <View style={s.lockedGrid}>
              {["Total Saved", "Active Pools", "Transactions", "Advances"].map(label => (
                <View key={label} style={s.lockedCard}>
                  <View style={s.lockedIconWrap}>
                    <Ionicons name="lock-closed" size={18} color={COLORS.textMuted} />
                  </View>
                  <Text style={s.lockedValue}>—</Text>
                  <Text style={s.lockedLabel}>{label}</Text>
                </View>
              ))}
              <Text style={s.lockedHint}>Complete KYC to view your financial summary</Text>
            </View>
          )}
        </View>

        {/* ── Activity Feed banner (verified only) ───────────────────── */}
        {isVerified && (
          <TouchableOpacity
            style={s.activityBanner}
            onPress={() => router.push("/activity")}
            activeOpacity={0.82}
          >
            <View style={s.activityBannerIcon}>
              <Ionicons name="pulse" size={20} color={COLORS.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.activityBannerTitle}>Activity Feed</Text>
              <Text style={s.activityBannerSub}>View your full transaction & event history</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
          </TouchableOpacity>
        )}

        {/* ── Reminders (verified only) ───────────────────────────────── */}
        {isVerified && (
          <View style={s.section}>
            <View style={s.sectionHead}>
              <Text style={s.sectionTitle}>Reminders</Text>
              <TouchableOpacity onPress={() => router.push("/reminders")}>
                <Text style={s.sectionAction}>Manage</Text>
              </TouchableOpacity>
            </View>

            {reminders.length === 0 ? (
              <TouchableOpacity style={s.addReminderRow} onPress={() => router.push("/reminders")}>
                <View style={[s.reminderIcon, { backgroundColor: COLORS.primaryPale }]}>
                  <Ionicons name="add" size={16} color={COLORS.primary} />
                </View>
                <Text style={s.addReminderText}>Set a contribution reminder</Text>
              </TouchableOpacity>
            ) : (
              reminders.map((r, idx) => (
                <TouchableOpacity
                  key={r.id}
                  style={[s.reminderRow, idx === reminders.length - 1 && { borderBottomWidth: 0 }]}
                  onPress={() => router.push("/reminders")}
                >
                  <View style={[s.reminderIcon, { backgroundColor: COLORS.primaryPale }]}>
                    <Ionicons name="alarm-outline" size={16} color={COLORS.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={s.reminderTitle} numberOfLines={1}>{r.title}</Text>
                    <Text style={s.reminderTime}>
                      {r.recurrence !== "none"
                        ? `${r.recurrence.charAt(0).toUpperCase() + r.recurrence.slice(1)} · `
                        : ""}
                      {new Date(r.next_fire_at).toLocaleDateString("en-KE", {
                        weekday: "short", month: "short", day: "numeric",
                      })}
                    </Text>
                  </View>
                  {r.is_overdue && (
                    <View style={s.overdueChip}>
                      <Text style={s.overdueText}>Due</Text>
                    </View>
                  )}
                </TouchableOpacity>
              ))
            )}
          </View>
        )}

        {/* ── Discover communities & campaigns (unverified only) ───────── */}
        {!isVerified && (communities.length > 0 || campaigns.length > 0) && (
          <View style={s.section}>
            <View style={s.sectionHead}>
              <Text style={s.sectionTitle}>Discover Communities & Campaigns</Text>
              <View style={s.lockedPill}>
                <Ionicons name="lock-closed" size={10} color={COLORS.textMuted} />
                <Text style={s.lockedPillText}>Verify to join</Text>
              </View>
            </View>
            <Text style={s.discoverHint}>
              A peek at what&apos;s active near you. Explore everything in Discover —
              verify your identity to join or support.
            </Text>

            {/* Sneak peek — a couple of items only; the full list lives in Discover. */}
            {communities.slice(0, 2).map((c) => (
              <View key={c.id} style={s.discoverRow}>
                {c.community_photo ? (
                  <Image source={{ uri: c.community_photo }} style={s.discoverAvatarImg} resizeMode="cover" />
                ) : (
                  <View style={[s.discoverAvatar, { backgroundColor: avatarColorFor(c.name).bg }]}>
                    <Text style={[s.discoverAvatarText, { color: avatarColorFor(c.name).text }]}>
                      {initialsFor(c.name)}
                    </Text>
                  </View>
                )}
                <View style={s.discoverInfo}>
                  <Text style={s.discoverName} numberOfLines={1}>{c.name}</Text>
                  <Text style={s.discoverMeta}>
                    {c.member_count} {c.member_count === 1 ? "member" : "members"}
                    {c.category ? ` · ${c.category}` : ""}
                  </Text>
                </View>
                <View style={s.peekTag}><Ionicons name="people-outline" size={13} color={COLORS.textMuted} /></View>
              </View>
            ))}

            {campaigns.slice(0, 1).map((c) => (
              <View key={`camp-${c.id}`} style={s.discoverRow}>
                <View style={[s.discoverAvatar, { backgroundColor: COLORS.accentPale }]}>
                  <Ionicons name="megaphone-outline" size={18} color={COLORS.accent} />
                </View>
                <View style={s.discoverInfo}>
                  <Text style={s.discoverName} numberOfLines={1}>{c.title}</Text>
                  <Text style={s.discoverMeta}>
                    {fmtKES(c.current_amount)}
                    {c.target_amount ? ` of ${fmtKES(c.target_amount)}` : " raised"}
                  </Text>
                </View>
                <View style={s.peekTag}><Ionicons name="megaphone-outline" size={13} color={COLORS.textMuted} /></View>
              </View>
            ))}

            {/* Direct to the full Discover page */}
            <TouchableOpacity style={s.exploreBtn} onPress={() => router.push("/discover")}>
              <Text style={s.exploreText}>Explore all in Discover</Text>
              <Ionicons name="arrow-forward" size={16} color={COLORS.primary} />
            </TouchableOpacity>
          </View>
        )}

        {/* ── Menu ────────────────────────────────────────────────────── */}
        <View style={s.menuSection}>
          <MenuItem
            icon="shield-checkmark-outline"
            label="Verification Center"
            onPress={() => router.push("/verification")}
          />
          <MenuItem
            icon="settings-outline"
            label="Settings"
            onPress={() => router.push("/settings")}
          />
          <MenuItem
            icon="people-outline"
            label="Invite a Friend"
            onPress={() => router.push("/invite")}
          />
          <MenuItem
            icon="help-circle-outline"
            label="Help & Support"
            onPress={() => Linking.openURL("mailto:support@wepl.app")}
            last={!isVerified}
          />
          {isVerified && (
            <MenuItem
              icon="document-text-outline"
              label="Reports & Statements"
              onPress={() => router.push("/reports")}
              last
            />
          )}
        </View>

      </ScrollView>

      {/* ── Edit Profile sheet ───────────────────────────────────────── */}
      <Modal visible={showEdit} transparent animationType="slide" onRequestClose={() => setShowEdit(false)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <Pressable style={StyleSheet.absoluteFillObject} onPress={() => setShowEdit(false)} />
          <View style={s.sheet} onStartShouldSetResponder={() => true}>
            <View style={s.sheetHandle} />
            <Text style={s.sheetTitle}>Edit Profile</Text>

            <Text style={s.fieldLabel}>Display Name</Text>
            <TextInput
              value={editName}
              onChangeText={setEditName}
              placeholder="Your name"
              placeholderTextColor={COLORS.textMuted}
              style={s.input}
              autoFocus
            />

            <Text style={s.fieldLabel}>Bio</Text>
            <TextInput
              value={editBio}
              onChangeText={setEditBio}
              placeholder="A short bio (optional)"
              placeholderTextColor={COLORS.textMuted}
              style={[s.input, { height: 80, textAlignVertical: "top" }]}
              multiline
            />

            <View style={s.sheetActions}>
              <TouchableOpacity style={s.cancelBtn} onPress={() => setShowEdit(false)}>
                <Text style={s.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.saveBtn} onPress={handleSave} disabled={saving}>
                {saving
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={s.saveText}>Save</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────

function StatCard({ icon, iconColor, label, value, sub, highlight }: {
  icon: string; iconColor: string; label: string; value: string; sub?: string; highlight?: boolean;
}) {
  return (
    <View style={[s.statCard, highlight && s.statHighlight]}>
      <View style={[s.statIcon, { backgroundColor: iconColor + "18" }]}>
        <Ionicons name={icon as any} size={18} color={iconColor} />
      </View>
      <Text style={s.statValue}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
      {sub ? <Text style={s.statSub}>{sub}</Text> : null}
    </View>
  );
}

function MenuItem({ icon, label, onPress, last }: {
  icon: string; label: string; onPress: () => void; last?: boolean;
}) {
  return (
    <TouchableOpacity
      style={[s.menuRow, last && { borderBottomWidth: 0 }]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={s.menuIconBg}>
        <Ionicons name={icon as any} size={18} color={COLORS.primary} />
      </View>
      <Text style={s.menuLabel}>{label}</Text>
      <Ionicons name="chevron-forward" size={15} color={COLORS.textMuted} />
    </TouchableOpacity>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  // Hero
  hero: {
    alignItems: "center",
    paddingTop: 24, paddingBottom: 20,
    backgroundColor: COLORS.white,
    marginBottom: 8,
  },
  avatar: {
    width: 80, height: 80, borderRadius: 40,
    justifyContent: "center", alignItems: "center",
    marginBottom: 12,
  },
  avatarInitials: { fontSize: 30, fontWeight: "700" },
  avatarImage:    { width: 80, height: 80, borderRadius: 40 },
  avatarEditBadge: {
    position: "absolute", bottom: 12, right: -2,
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
    borderWidth: 2, borderColor: COLORS.white,
  },
  heroName:    { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginBottom: 3 },
  heroPhone:   { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 8 },
  kycBadge:    {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 12, paddingVertical: 5,
    borderRadius: RADIUS.full, marginBottom: 8,
  },
  kycBadgeText: { fontSize: FONTS.xs, fontWeight: "700" },
  memberSince:  { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 4 },

  // KYC CTA card
  ctaCard: {
    backgroundColor: COLORS.white,
    marginBottom: 10,
    padding: 20,
    alignItems: "center",
    borderTopWidth: 3,
    borderTopColor: COLORS.primary,
  },
  ctaIconWrap: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center", alignItems: "center",
    marginBottom: 12,
  },
  ctaTitle: {
    fontSize: FONTS.lg,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 8,
    textAlign: "center",
  },
  ctaBody: {
    fontSize: FONTS.sm,
    color: COLORS.textSecondary,
    textAlign: "center",
    lineHeight: 20,
    marginBottom: 16,
    paddingHorizontal: 8,
  },
  ctaBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: COLORS.primary,
    paddingHorizontal: 28,
    paddingVertical: 13,
    borderRadius: RADIUS.md,
    marginBottom: 16,
  },
  ctaBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
  unlockRow: {
    flexDirection: "row", flexWrap: "wrap", gap: 6, justifyContent: "center",
  },
  unlockChip: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: COLORS.background,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.border,
  },
  unlockChipText: { fontSize: FONTS.xs, color: COLORS.textMuted, fontWeight: "500" },

  // Section
  section: {
    backgroundColor: COLORS.white,
    marginBottom: 8,
    paddingHorizontal: 16, paddingVertical: 16,
  },
  sectionHead: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginBottom: 14,
  },
  sectionTitle:  { fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary },
  sectionAction: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },

  // Stats
  statsGrid: { flexDirection: "row", gap: 10 },
  statCard: {
    flex: 1, backgroundColor: COLORS.background,
    borderRadius: RADIUS.md, padding: 14,
  },
  statHighlight: { backgroundColor: "#FFFBF0" },
  statIcon:  { width: 30, height: 30, borderRadius: RADIUS.sm, justifyContent: "center", alignItems: "center", marginBottom: 8 },
  statValue: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginBottom: 2 },
  statLabel: { fontSize: FONTS.xs, color: COLORS.textMuted, letterSpacing: 0.2 },
  statSub:   { fontSize: FONTS.xs, color: COLORS.textSecondary, marginTop: 3 },

  // Locked placeholders
  lockedGrid: {
    flexDirection: "row", flexWrap: "wrap", gap: 10,
  },
  lockedCard: {
    width: "48%", backgroundColor: COLORS.background,
    borderRadius: RADIUS.md, padding: 14,
    borderWidth: 1, borderColor: COLORS.divider,
    borderStyle: "dashed",
    alignItems: "center",
  },
  lockedIconWrap: {
    width: 32, height: 32, borderRadius: RADIUS.md,
    backgroundColor: COLORS.divider,
    justifyContent: "center", alignItems: "center",
    marginBottom: 8,
  },
  lockedValue: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.border, marginBottom: 2 },
  lockedLabel: { fontSize: FONTS.xs, color: COLORS.textMuted },
  lockedHint:  {
    width: "100%", textAlign: "center", marginTop: 8,
    fontSize: FONTS.xs, color: COLORS.textMuted, fontStyle: "italic",
  },

  // Menu
  menuSection: { backgroundColor: COLORS.white, marginBottom: 10 },
  menuRow: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 16, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
    gap: 14,
  },
  menuIconBg: {
    width: 34, height: 34, borderRadius: RADIUS.md,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center", alignItems: "center",
  },
  menuLabel: { flex: 1, fontSize: FONTS.md, color: COLORS.text, fontWeight: "500" },

  // Activity banner
  activityBanner: {
    flexDirection: "row", alignItems: "center", gap: 14,
    backgroundColor: COLORS.white,
    paddingHorizontal: 16, paddingVertical: 14,
    marginBottom: 10,
    borderTopWidth: 1, borderBottomWidth: 1, borderColor: COLORS.divider,
  },
  activityBannerIcon: {
    width: 38, height: 38, borderRadius: RADIUS.md,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center", alignItems: "center",
  },
  activityBannerTitle: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  activityBannerSub:   { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 1 },

  // Reminders
  addReminderRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingVertical: 10,
  },
  addReminderText: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },
  reminderRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  reminderIcon: {
    width: 32, height: 32, borderRadius: RADIUS.md,
    justifyContent: "center", alignItems: "center",
  },
  reminderTitle: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  reminderTime:  { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 2 },
  overdueChip: {
    backgroundColor: "#FEF2F2", paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: RADIUS.full,
  },
  overdueText: { fontSize: 11, color: COLORS.error, fontWeight: "700" },

  // Locked pill badge next to section title
  lockedPill: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: COLORS.background,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.border,
  },
  lockedPillText: { fontSize: 10, color: COLORS.textMuted, fontWeight: "600" },

  // Discover section
  discoverHint: {
    fontSize: FONTS.xs, color: COLORS.textSecondary, marginBottom: 12, lineHeight: 17,
  },
  discoverSubhead: {
    fontSize: 11, fontWeight: "700", color: COLORS.textMuted,
    letterSpacing: 0.4, textTransform: "uppercase",
    marginTop: 14, marginBottom: 2,
  },
  peekTag: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: COLORS.background,
    justifyContent: "center", alignItems: "center",
  },
  exploreBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    marginTop: 12, paddingVertical: 12,
    borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.primary,
    backgroundColor: COLORS.primaryPale,
  },
  exploreText: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.primary },
  discoverRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  discoverAvatar: {
    width: 40, height: 40, borderRadius: 20,
    justifyContent: "center", alignItems: "center",
  },
  discoverAvatarImg: { width: 40, height: 40, borderRadius: 20 },
  discoverAvatarText: { fontSize: 16, fontWeight: "700" },
  discoverInfo:       { flex: 1 },
  discoverName:       { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  discoverMeta:       { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 2 },

  // Edit sheet
  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 20, paddingBottom: Platform.OS === "ios" ? 36 : 20,
  },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: COLORS.border, alignSelf: "center", marginBottom: 16,
  },
  sheetTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginBottom: 16 },
  fieldLabel: { fontSize: FONTS.sm, color: COLORS.textSecondary, fontWeight: "600", marginBottom: 6, marginTop: 4 },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: RADIUS.md, padding: 13,
    fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background, marginBottom: 8,
  },
  sheetActions: { flexDirection: "row", gap: 10, marginTop: 8 },
  cancelBtn: {
    flex: 1, padding: 14, borderRadius: RADIUS.md,
    borderWidth: 1.5, borderColor: COLORS.border,
    alignItems: "center",
  },
  cancelText: { color: COLORS.text, fontWeight: "600" },
  saveBtn: {
    flex: 1, padding: 14, borderRadius: RADIUS.md,
    backgroundColor: COLORS.primary, alignItems: "center",
  },
  saveText: { color: COLORS.white, fontWeight: "700" },
});
