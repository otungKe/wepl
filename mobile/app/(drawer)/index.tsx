import { useState, useCallback, useEffect } from "react";
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl, TextInput, Modal,
  KeyboardAvoidingView, Platform, Pressable, Image, ScrollView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  getMyCommunities, getCommunityByInviteCode, requestToJoinCommunity,
  getMyJoinRequests, PendingRequest,
  Community,
} from "../../api/communities";
import { getUnreadSummary, UnreadSummary } from "../../api/conversations";
import { on } from "../../utils/eventBus";
import { COLORS, FONTS, RADIUS, avatarColorFor, initialsFor } from "../../constants/theme";
import Avatar from "../../components/app/Avatar";
import FAB from "../../components/app/FAB";
import KYCBanner from "../../components/app/KYCBanner";
import { useKYCGate } from "../../hooks/useKYCGate";

type Sheet = null | "menu" | "join";
type JoinStep = "input" | "loading" | "preview" | "requesting" | "success";

export default function CommunitiesScreen() {
  const [communities, setCommunities]     = useState<Community[]>([]);
  const [pendingRequests, setPendingRequests] = useState<PendingRequest[]>([]);
  const [unreadSummary, setUnreadSummary] = useState<UnreadSummary>({ total: 0, by_community: {} });
  const [loading, setLoading]   = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch]     = useState("");
  const [cat, setCat]           = useState<string | null>(null);

  // FAB action sheet
  const [sheet, setSheet] = useState<Sheet>(null);
  const [code, setCode] = useState("");
  const [joinStep, setJoinStep] = useState<JoinStep>("input");
  const [preview, setPreview] = useState<Community | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);

  const { kycStatus, isVerified, requireKYC } = useKYCGate();

  const load = useCallback(async () => {
    try {
      const [comms, summary, requests] = await Promise.all([
        getMyCommunities(),
        getUnreadSummary(),
        getMyJoinRequests(),
      ]);
      setCommunities(comms);
      setUnreadSummary(summary);
      setPendingRequests(requests);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => {
    load().finally(() => setLoading(false));
  }, [load]));

  useEffect(() => {
    return on('newMessage', () => {
      getUnreadSummary().then(setUnreadSummary).catch(() => {});
    });
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  // Distinct categories present across the user's communities, for the filter row.
  const categories = Array.from(
    new Set(communities.map((c) => c.category).filter(Boolean) as string[])
  ).sort();

  const filtered = communities.filter((c) => {
    const matchesSearch = !search.trim() || c.name.toLowerCase().includes(search.toLowerCase());
    const matchesCat    = !cat || c.category === cat;
    return matchesSearch && matchesCat;
  });

  const closeSheet = () => {
    setSheet(null);
    setCode("");
    setJoinStep("input");
    setPreview(null);
    setJoinError(null);
  };

  const lookupCode = async () => {
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) return;
    setJoinStep("loading");
    setJoinError(null);
    try {
      const community = await getCommunityByInviteCode(trimmed);
      setPreview(community);
      setJoinStep("preview");
    } catch {
      setJoinError("Invalid invite code. Please check and try again.");
      setJoinStep("input");
    }
  };

  const submitRequest = async () => {
    if (!preview) return;
    setJoinStep("requesting");
    try {
      await requestToJoinCommunity(code.trim().toUpperCase());
      setJoinStep("success");
      await load();
    } catch (e: any) {
      const msg = e?.response?.data?.error ?? "Could not submit request.";
      setJoinError(msg);
      setJoinStep("preview");
    }
  };

  // Unverified users must only see the Profile tab. They can still land on this
  // screen (the post-login redirect targets the drawer root) — bounce them to
  // Profile and don't render community content meanwhile.
  useEffect(() => {
    if (kycStatus !== "loading" && !isVerified) {
      router.replace("/(drawer)/profile");
    }
  }, [kycStatus, isVerified]);

  if (kycStatus === "loading" || !isVerified) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  const totalUnread  = unreadSummary.total;
  const totalPending = pendingRequests.length;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Communities</Text>
          {!loading && communities.length > 0 && (
            <View style={styles.summaryRow}>
              <Text style={styles.summaryText}>
                {communities.length} {communities.length === 1 ? "group" : "groups"}
              </Text>
              {totalUnread > 0 && (
                <View style={styles.summaryChip}>
                  <View style={[styles.summaryDot, { backgroundColor: COLORS.primary }]} />
                  <Text style={styles.summaryChipText}>{totalUnread} unread</Text>
                </View>
              )}
              {totalPending > 0 && (
                <TouchableOpacity
                  style={[styles.summaryChip, styles.summaryChipPending]}
                  onPress={() => router.push("/join-requests")}
                  activeOpacity={0.7}
                >
                  <Ionicons name="time-outline" size={12} color={COLORS.accent} />
                  <Text style={[styles.summaryChipText, { color: COLORS.accent }]}>
                    {totalPending} pending
                  </Text>
                </TouchableOpacity>
              )}
            </View>
          )}
        </View>
      </View>

      {/* KYC verification banner — hidden once approved */}
      <KYCBanner status={kycStatus} />

      {/* Search bar */}
      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search-outline" size={16} color={COLORS.textMuted} />
          <TextInput
            placeholder="Search communities..."
            placeholderTextColor={COLORS.textMuted}
            value={search}
            onChangeText={setSearch}
            style={styles.searchInput}
            returnKeyType="search"
            clearButtonMode="while-editing"
          />
        </View>
      </View>

      {/* Category filter chips */}
      {!loading && categories.length > 1 && (
        <View style={styles.filterWrap}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.filterRow}
          >
            {[null, ...categories].map((c) => {
              const active = cat === c;
              return (
                <TouchableOpacity
                  key={c ?? "__all"}
                  onPress={() => setCat(c)}
                  activeOpacity={0.7}
                  style={[styles.filterChip, active && styles.filterChipActive]}
                >
                  <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>
                    {c ?? "All"}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      )}

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : filtered.length === 0 && communities.length === 0 ? (
        <View style={styles.empty}>
          <View style={styles.emptyIcon}>
            <Ionicons name="people-outline" size={34} color={COLORS.primary} />
          </View>
          <Text style={styles.emptyTitle}>No communities yet</Text>
          <Text style={styles.emptySub}>Create or join a community to start saving together.</Text>
          <TouchableOpacity style={styles.emptyCta} onPress={() => setSheet("menu")} activeOpacity={0.85}>
            <Ionicons name="add" size={18} color={COLORS.white} />
            <Text style={styles.emptyCtaText}>Create or join</Text>
          </TouchableOpacity>
        </View>
      ) : filtered.length === 0 ? (
        <View style={styles.empty}>
          <View style={styles.emptyIcon}>
            <Ionicons name="search-outline" size={30} color={COLORS.primary} />
          </View>
          <Text style={styles.emptyTitle}>No matches</Text>
          <Text style={styles.emptySub}>
            {search.trim() ? `No communities match "${search}".` : "No communities in this category."}
          </Text>
        </View>
      ) : (
        <FlatList
          style={{ flex: 1 }}
          data={filtered}
          keyExtractor={(i) => String(i.id)}
          renderItem={({ item }: { item: Community }) => {
            const unreadCount = unreadSummary.by_community[String(item.id)] ?? 0;
            const hasUnread   = unreadCount > 0;
            const palette     = avatarColorFor(item.name);

            return (
              <TouchableOpacity
                style={styles.card}
                onPress={() => router.push({ pathname: "/community/[id]", params: { id: String(item.id), name: item.name } })}
                activeOpacity={0.75}
              >
                {/* Category-colored identity stripe */}
                <View style={[styles.cardAccent, { backgroundColor: palette.text }]} />

                <View style={styles.cardInner}>
                  {/* Photo */}
                  <View style={styles.cardPhotoWrap}>
                    {item.community_photo ? (
                      <Image source={{ uri: item.community_photo }} style={styles.cardPhoto} resizeMode="cover" />
                    ) : (
                      <View style={[styles.cardPhoto, styles.cardPhotoPlaceholder, { backgroundColor: palette.bg }]}>
                        <Text style={[styles.cardPhotoInitials, { color: palette.text }]}>
                          {initialsFor(item.name)}
                        </Text>
                      </View>
                    )}
                    {item.is_private && (
                      <View style={styles.privateBadge}>
                        <Ionicons name="lock-closed" size={9} color={COLORS.white} />
                      </View>
                    )}
                  </View>

                  {/* Content */}
                  <View style={styles.cardContent}>
                    <View style={styles.cardTitleRow}>
                      <Text style={[styles.cardName, hasUnread && styles.cardNameUnread]} numberOfLines={1}>
                        {item.name}
                      </Text>
                    </View>

                    {/* Meta: members + location */}
                    <View style={styles.metaRow}>
                      <Ionicons name="people-outline" size={13} color={COLORS.textMuted} />
                      <Text style={styles.metaText}>
                        {item.member_count} {item.member_count === 1 ? "member" : "members"}
                      </Text>
                      {item.location ? (
                        <>
                          <View style={styles.metaSep} />
                          <Ionicons name="location-outline" size={13} color={COLORS.textMuted} />
                          <Text style={styles.metaText} numberOfLines={1}>{item.location}</Text>
                        </>
                      ) : null}
                    </View>

                    {/* Feature chips */}
                    <View style={styles.chipRow}>
                      {item.category ? (
                        <View style={[styles.chip, { backgroundColor: palette.bg }]}>
                          <Text style={[styles.chipText, { color: palette.text }]}>{item.category}</Text>
                        </View>
                      ) : null}
                      {item.has_welfare_fund ? (
                        <View style={[styles.chip, styles.chipWelfare]}>
                          <Ionicons name="heart-outline" size={11} color={COLORS.primary} />
                          <Text style={[styles.chipText, { color: COLORS.primary }]}>Welfare</Text>
                        </View>
                      ) : null}
                      {item.has_shares_fund ? (
                        <View style={[styles.chip, styles.chipShares]}>
                          <Ionicons name="trending-up-outline" size={11} color={COLORS.accent} />
                          <Text style={[styles.chipText, { color: COLORS.accent }]}>Shares</Text>
                        </View>
                      ) : null}
                    </View>
                  </View>

                  {/* Right: unread + chevron */}
                  <View style={styles.cardRight}>
                    {hasUnread ? (
                      <View style={styles.unreadBadge}>
                        <Text style={styles.unreadBadgeText}>{unreadCount > 9 ? "9+" : unreadCount}</Text>
                      </View>
                    ) : (
                      <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                    )}
                  </View>
                </View>
              </TouchableOpacity>
            );
          }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
          contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 6, paddingBottom: 96 }}
          showsVerticalScrollIndicator={false}
        />
      )}

      <FAB icon="add" onPress={() => setSheet("menu")} />

      {/* ── FAB action sheet ── */}
      <Modal visible={sheet !== null} transparent animationType="slide" onRequestClose={closeSheet}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          style={styles.sheetWrap}
        >
          <Pressable style={StyleSheet.absoluteFillObject} onPress={closeSheet} />
          <View style={styles.sheet} onStartShouldSetResponder={() => true}>
            <View style={styles.sheetHandle} />

            {/* ── Menu: choose action ── */}
            {sheet === "menu" && (
              <>
                <Text style={styles.sheetTitle}>Join or Create</Text>
                <TouchableOpacity
                  style={styles.sheetOption}
                  activeOpacity={0.7}
                  onPress={() => { closeSheet(); if (requireKYC()) router.push("/community/create"); }}
                >
                  <View style={[styles.sheetOptionIcon, { backgroundColor: COLORS.primary + "18" }]}>
                    <Ionicons name="add-circle-outline" size={22} color={COLORS.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.sheetOptionTitle}>Create Community</Text>
                    <Text style={styles.sheetOptionSub}>Start a new savings group</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.sheetOption}
                  activeOpacity={0.7}
                  onPress={() => setSheet("join")}
                >
                  <View style={[styles.sheetOptionIcon, { backgroundColor: COLORS.success + "18" }]}>
                    <Ionicons name="link-outline" size={22} color={COLORS.success} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.sheetOptionTitle}>Join with Invite Code</Text>
                    <Text style={styles.sheetOptionSub}>Enter a code shared by a group admin</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                </TouchableOpacity>
              </>
            )}

            {/* ── Join flow ── */}
            {sheet === "join" && (
              <>
                {/* Header row with back */}
                <View style={styles.joinHeader}>
                  <TouchableOpacity onPress={() => { setSheet("menu"); setCode(""); setJoinStep("input"); setPreview(null); setJoinError(null); }}>
                    <Ionicons name="arrow-back" size={22} color={COLORS.text} />
                  </TouchableOpacity>
                  <Text style={styles.sheetTitle}>Join with Invite Code</Text>
                  <View style={{ width: 22 }} />
                </View>

                {joinStep === "success" ? (
                  <View style={styles.successBox}>
                    <Ionicons name="checkmark-circle" size={56} color={COLORS.success} />
                    <Text style={styles.successTitle}>Request Sent!</Text>
                    <Text style={styles.successSub}>
                      The group admin will review your request and you'll be notified once approved.
                    </Text>
                    <TouchableOpacity style={styles.doneBtn} onPress={closeSheet}>
                      <Text style={styles.doneBtnText}>Done</Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <>
                    {/* Code input */}
                    {(joinStep === "input" || joinStep === "loading") && (
                      <>
                        <Text style={styles.joinLabel}>Enter the invite code</Text>
                        <View style={styles.codeRow}>
                          <TextInput
                            style={styles.codeInput}
                            placeholder="e.g. A3F9K2B1C0"
                            placeholderTextColor={COLORS.textMuted}
                            value={code}
                            onChangeText={(t) => setCode(t.toUpperCase())}
                            autoCapitalize="characters"
                            autoCorrect={false}
                            returnKeyType="go"
                            onSubmitEditing={lookupCode}
                          />
                          <TouchableOpacity
                            style={[styles.lookupBtn, (!code.trim() || joinStep === "loading") && styles.lookupBtnDisabled]}
                            onPress={lookupCode}
                            disabled={!code.trim() || joinStep === "loading"}
                          >
                            {joinStep === "loading"
                              ? <ActivityIndicator size="small" color={COLORS.white} />
                              : <Text style={styles.lookupBtnText}>Look up</Text>
                            }
                          </TouchableOpacity>
                        </View>
                        {joinError && <Text style={styles.errorText}>{joinError}</Text>}
                      </>
                    )}

                    {/* Community preview */}
                    {(joinStep === "preview" || joinStep === "requesting") && preview && (
                      <View style={styles.previewBox}>
                        <Avatar name={preview.name} uri={preview.community_photo} size={64} />
                        <Text style={styles.previewName}>{preview.name}</Text>
                        {preview.description ? (
                          <Text style={styles.previewDesc}>{preview.description}</Text>
                        ) : null}
                        <Text style={styles.previewMeta}>
                          {preview.member_count} {preview.member_count === 1 ? "member" : "members"}
                          {preview.is_private ? "  ·  Private" : "  ·  Public"}
                        </Text>
                        {joinError && <Text style={[styles.errorText, { marginTop: 8 }]}>{joinError}</Text>}
                        <TouchableOpacity
                          style={[styles.requestBtn, joinStep === "requesting" && styles.requestBtnDisabled]}
                          onPress={submitRequest}
                          disabled={joinStep === "requesting"}
                        >
                          {joinStep === "requesting"
                            ? <ActivityIndicator size="small" color={COLORS.white} />
                            : <Text style={styles.requestBtnText}>Request to Join</Text>
                          }
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => { setJoinStep("input"); setPreview(null); setJoinError(null); }}>
                          <Text style={styles.backLink}>Use a different code</Text>
                        </TouchableOpacity>
                      </View>
                    )}
                  </>
                )}
              </>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>

    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  header: {
    flexDirection: "row", alignItems: "flex-start",
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 10,
    backgroundColor: COLORS.white,
  },
  headerTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text },

  // Header summary chips
  summaryRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 5, flexWrap: "wrap" },
  summaryText: { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "500" },
  summaryChip: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: RADIUS.full, backgroundColor: COLORS.primaryPale,
  },
  summaryChipPending: { backgroundColor: COLORS.accentPale },
  summaryDot: { width: 6, height: 6, borderRadius: 3 },
  summaryChipText: { fontSize: 11, fontWeight: "700", color: COLORS.primary },

  // Search
  searchRow: {
    backgroundColor: COLORS.white,
    paddingHorizontal: 16, paddingBottom: 10, paddingTop: 2,
  },
  searchBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    height: 40, paddingHorizontal: 12,
    backgroundColor: COLORS.background,
    borderRadius: RADIUS.full,
  },
  searchInput: { flex: 1, height: 40, fontSize: FONTS.sm, color: COLORS.text, padding: 0 },

  // Category filter chips
  filterWrap: {
    backgroundColor: COLORS.white, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  filterRow: { paddingHorizontal: 16, gap: 8 },
  filterChip: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: RADIUS.full,
    backgroundColor: COLORS.background,
    borderWidth: 1, borderColor: COLORS.divider,
  },
  filterChipActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  filterChipText: { fontSize: FONTS.xs, fontWeight: "600", color: COLORS.textSecondary },
  filterChipTextActive: { color: COLORS.white },

  // Empty
  empty: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 40, gap: 8 },
  emptyIcon: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center", alignItems: "center", marginBottom: 6,
  },
  emptyTitle: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginTop: 4 },
  emptySub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },
  emptyCta: {
    flexDirection: "row", alignItems: "center", gap: 6,
    marginTop: 14, height: 44, paddingHorizontal: 20,
    backgroundColor: COLORS.primary, borderRadius: RADIUS.full,
  },
  emptyCtaText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },

  // Elevated community card
  card: {
    flexDirection: "row",
    backgroundColor: COLORS.surface,
    borderRadius: 16,
    marginBottom: 10,
    overflow: "hidden",
    borderWidth: 1, borderColor: COLORS.divider,
    shadowColor: "#0B231A",
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  cardAccent: { width: 4 },
  cardInner: {
    flex: 1, flexDirection: "row", alignItems: "center", gap: 12,
    paddingVertical: 12, paddingHorizontal: 14,
  },
  cardPhotoWrap: { position: "relative" },
  cardPhoto:     { width: 52, height: 52, borderRadius: RADIUS.md },
  cardPhotoPlaceholder: { justifyContent: "center", alignItems: "center" },
  cardPhotoInitials:    { fontSize: 20, fontWeight: "700" },
  privateBadge: {
    position: "absolute", bottom: -2, right: -2,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: COLORS.textMuted,
    justifyContent: "center", alignItems: "center",
    borderWidth: 1.5, borderColor: COLORS.white,
  },
  cardContent:  { flex: 1, gap: 5 },
  cardTitleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  cardName:     { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, flexShrink: 1 },
  cardNameUnread: { fontWeight: "800" },
  metaRow:  { flexDirection: "row", alignItems: "center", gap: 4 },
  metaText: { fontSize: FONTS.xs, color: COLORS.textMuted, flexShrink: 1 },
  metaSep:  { width: 3, height: 3, borderRadius: 1.5, backgroundColor: COLORS.border, marginHorizontal: 3 },
  chipRow:  { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 3,
    paddingHorizontal: 7, paddingVertical: 2,
    borderRadius: RADIUS.sm,
  },
  chipText:    { fontSize: 10, fontWeight: "700" },
  chipWelfare: { backgroundColor: COLORS.primaryPale },
  chipShares:  { backgroundColor: COLORS.accentPale },
  cardRight:   { minWidth: 24, alignItems: "center", justifyContent: "center" },

  unreadBadge: {
    minWidth: 20, height: 20, borderRadius: 10,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
    paddingHorizontal: 4,
  },
  unreadBadgeText: { fontSize: 11, fontWeight: "700", color: COLORS.white },

  // Bottom sheet
  sheetWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingHorizontal: 20,
    paddingBottom: 36,
    paddingTop: 12,
  },
  sheetHandle: {
    width: 36, height: 4, borderRadius: 2,
    backgroundColor: COLORS.divider,
    alignSelf: "center", marginBottom: 16,
  },
  sheetTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, textAlign: "center", marginBottom: 20 },

  sheetOption: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 14, gap: 14,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  sheetOptionIcon: {
    width: 44, height: 44, borderRadius: RADIUS.full,
    justifyContent: "center", alignItems: "center",
  },
  sheetOptionTitle: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  sheetOptionSub: { fontSize: FONTS.sm, color: COLORS.textMuted },

  // Join flow
  joinHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginBottom: 20,
  },
  joinLabel: { fontSize: FONTS.sm, color: COLORS.textSecondary, marginBottom: 10 },
  codeRow: { flexDirection: "row", gap: 10, marginBottom: 8 },
  codeInput: {
    flex: 1, height: 46,
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: RADIUS.md, paddingHorizontal: 14,
    fontSize: FONTS.md, color: COLORS.text,
    letterSpacing: 2,
  },
  lookupBtn: {
    height: 46, paddingHorizontal: 16,
    backgroundColor: COLORS.primary, borderRadius: RADIUS.md,
    justifyContent: "center", alignItems: "center",
  },
  lookupBtnDisabled: { opacity: 0.5 },
  lookupBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },
  errorText: { fontSize: FONTS.sm, color: COLORS.error, marginBottom: 4 },

  // Preview
  previewBox: { alignItems: "center", paddingVertical: 12, gap: 6 },
  previewName: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, marginTop: 8 },
  previewDesc: { fontSize: FONTS.sm, color: COLORS.textSecondary, textAlign: "center", lineHeight: 19 },
  previewMeta: { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 4 },
  requestBtn: {
    marginTop: 12, width: "100%",
    height: 48, backgroundColor: COLORS.primary,
    borderRadius: RADIUS.md, justifyContent: "center", alignItems: "center",
  },
  requestBtnDisabled: { opacity: 0.6 },
  requestBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
  backLink: { fontSize: FONTS.sm, color: COLORS.primary, marginTop: 10 },

  // Success
  successBox: { alignItems: "center", paddingVertical: 20, gap: 10 },
  successTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text },
  successSub: { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20, paddingHorizontal: 10 },
  doneBtn: {
    marginTop: 12, width: "100%",
    height: 48, backgroundColor: COLORS.primary,
    borderRadius: RADIUS.md, justifyContent: "center", alignItems: "center",
  },
  doneBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
});
