import { useState, useCallback, useEffect } from "react";
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl, TextInput, Modal,
  KeyboardAvoidingView, Platform, Pressable,
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
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
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

  const filtered = search.trim()
    ? communities.filter((c) => c.name.toLowerCase().includes(search.toLowerCase()))
    : communities;

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

  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Communities</Text>
        {pendingRequests.length > 0 && (
          <TouchableOpacity
            style={styles.pendingChip}
            onPress={() => router.push("/join-requests")}
            activeOpacity={0.8}
          >
            <Ionicons name="time-outline" size={13} color={COLORS.accent} />
            <Text style={styles.pendingChipText}>
              {pendingRequests.length} Pending
            </Text>
          </TouchableOpacity>
        )}
      </View>

      {/* KYC verification banner — hidden once approved */}
      <KYCBanner status={kycStatus} />

      {/* Search bar */}
      <View style={styles.searchRow}>
        <Ionicons name="search-outline" size={16} color={COLORS.textMuted} style={styles.searchIcon} />
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

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : filtered.length === 0 && communities.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="people-outline" size={52} color={COLORS.textMuted} />
          <Text style={styles.emptyTitle}>No communities yet</Text>
          <Text style={styles.emptySub}>Create or join a community to start saving together.</Text>
        </View>
      ) : filtered.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="search-outline" size={40} color={COLORS.textMuted} />
          <Text style={styles.emptyTitle}>No results for "{search}"</Text>
        </View>
      ) : (
        <FlatList
          style={{ flex: 1 }}
          data={filtered}
          keyExtractor={(i) => String(i.id)}
          renderItem={({ item }: { item: Community }) => {
            const hasUnread = (unreadSummary.by_community[String(item.id)] ?? 0) > 0;
            return (
              <TouchableOpacity
                style={styles.row}
                onPress={() => router.push({ pathname: `/community/${item.id}`, params: { name: item.name } })}
                activeOpacity={0.7}
              >
                <Avatar name={item.name} uri={item.community_photo} size={50} />
                <View style={styles.rowText}>
                  <Text style={[styles.name, hasUnread && { fontWeight: "800" }]}>{item.name}</Text>
                  <Text style={styles.meta}>
                    {item.member_count} {item.member_count === 1 ? "member" : "members"}
                  </Text>
                </View>
                {hasUnread && (
                  <View style={styles.unreadDot} />
                )}
                <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
              </TouchableOpacity>
            );
          }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
          ItemSeparatorComponent={() => <View style={styles.divider} />}
          contentContainerStyle={{ paddingBottom: 96 }}
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
  safe: { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  // Pending requests chip
  pendingChip: {
    flexDirection: "row", alignItems: "center", gap: 5,
    backgroundColor: "#fef7e0",
    paddingHorizontal: 12, paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: "#f6d860",
  },
  pendingChipText: { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.accent },

  header: {
    flexDirection:    "row",
    alignItems:       "center",
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12,
    backgroundColor:  COLORS.white,
  },
  headerTitle: { flex: 1, fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text },
  discoverBtn: {
    flexDirection:   "row",
    alignItems:      "center",
    gap:             4,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius:    RADIUS.full,
    borderWidth:     1,
    borderColor:     COLORS.primary,
  },
  discoverBtnText: {
    fontSize:   FONTS.sm,
    fontWeight: "600",
    color:      COLORS.primary,
  },

  searchRow: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: COLORS.white,
    paddingHorizontal: 16, paddingBottom: 12,
    gap: 8,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  searchIcon: { marginLeft: 4 },
  searchInput: {
    flex: 1,
    height: 38,
    backgroundColor: COLORS.background,
    borderRadius: RADIUS.full,
    paddingHorizontal: 14,
    fontSize: FONTS.sm,
    color: COLORS.text,
    borderWidth: 1,
    borderColor: COLORS.border,
  },

  empty: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 40, gap: 10 },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub: { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  row: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 13, paddingHorizontal: 16,
    backgroundColor: COLORS.white, gap: 12,
  },
  rowText: { flex: 1 },
  name: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  meta: { fontSize: FONTS.sm, color: COLORS.textMuted },
  divider: { height: 1, backgroundColor: COLORS.divider, marginLeft: 78 },
  unreadDot: {
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: COLORS.success,
    marginRight: 4,
  },

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
