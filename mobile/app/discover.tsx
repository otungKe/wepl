import { useCallback, useRef, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  TextInput,
  Alert,
  Image,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  discoverCommunities,
  requestToJoinById,
  type Community,
} from "../api/communities";
import { joinContribution } from "../api/contributions";
import { getCampaigns, type Campaign } from "../api/discover";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

// ─── Constants ────────────────────────────────────────────────────────────────

const CATEGORIES = [
  { key: "",           label: "All"        },
  { key: "savings",    label: "Savings"    },
  { key: "chama",      label: "Chama"      },
  { key: "investment", label: "Investment" },
  { key: "welfare",    label: "Welfare"    },
  { key: "emergency",  label: "Emergency"  },
  { key: "business",   label: "Business"   },
  { key: "general",    label: "General"    },
];

const LIMIT = 20;

// ─── Community card ───────────────────────────────────────────────────────────

function CommunityCard({ item }: { item: Community }) {
  const [joining, setJoining] = useState(false);
  const [localStatus, setLocalStatus] = useState<"none" | "PENDING" | "joined">(
    item.is_member                              ? "joined"  :
    item.join_request_status === "PENDING"      ? "PENDING" :
    "none"
  );

  const categoryLabel =
    CATEGORIES.find((c) => c.key === item.category)?.label ?? item.category;

  const handleJoin = async () => {
    setJoining(true);
    try {
      await requestToJoinById(item.id);
      setLocalStatus("PENDING");
    } catch (e: any) {
      const msg =
        e?.response?.data?.error ||
        e?.response?.data?.detail ||
        "Could not send join request.";
      Alert.alert("Error", msg);
    } finally {
      setJoining(false);
    }
  };

  return (
    <TouchableOpacity
      style={styles.card}
      activeOpacity={0.82}
      onPress={() => router.push(`/community/${item.id}`)}
    >
      {/* Avatar / photo */}
      <View style={styles.cardAvatarWrap}>
        {item.community_photo ? (
          <Image source={{ uri: item.community_photo }} style={styles.cardAvatar} />
        ) : (
          <View style={[styles.cardAvatar, styles.cardAvatarPlaceholder]}>
            <Ionicons name="people" size={22} color={COLORS.primary} />
          </View>
        )}
      </View>

      {/* Body */}
      <View style={styles.cardBody}>
        <View style={styles.cardTitleRow}>
          <Text style={styles.cardTitle} numberOfLines={1}>{item.name}</Text>
          <View style={styles.categoryChip}>
            <Text style={styles.categoryChipText}>{categoryLabel}</Text>
          </View>
        </View>

        {!!item.description && (
          <Text style={styles.cardDesc} numberOfLines={2}>{item.description}</Text>
        )}

        <View style={styles.cardMeta}>
          <Ionicons name="people-outline" size={13} color={COLORS.textMuted} />
          <Text style={styles.cardMetaText}>
            {item.member_count} member{item.member_count !== 1 ? "s" : ""}
          </Text>
          {!!item.location && (
            <>
              <Text style={styles.cardMetaDot}>·</Text>
              <Ionicons name="location-outline" size={13} color={COLORS.textMuted} />
              <Text style={styles.cardMetaText} numberOfLines={1}>{item.location}</Text>
            </>
          )}
        </View>
      </View>

      {/* Action */}
      <View style={styles.cardAction}>
        {localStatus === "joined" ? (
          <View style={styles.joinedBadge}>
            <Ionicons name="checkmark" size={12} color={COLORS.primary} />
            <Text style={styles.joinedBadgeText}>Joined</Text>
          </View>
        ) : localStatus === "PENDING" ? (
          <View style={[styles.joinedBadge, { borderColor: COLORS.warning }]}>
            <Text style={[styles.joinedBadgeText, { color: COLORS.warning }]}>Pending</Text>
          </View>
        ) : (
          <TouchableOpacity style={styles.joinBtn} onPress={handleJoin} disabled={joining}>
            {joining
              ? <ActivityIndicator size={12} color={COLORS.white} />
              : <Text style={styles.joinBtnText}>Join</Text>
            }
          </TouchableOpacity>
        )}
      </View>
    </TouchableOpacity>
  );
}

// ─── Campaign card ────────────────────────────────────────────────────────────

function CampaignCard({
  item,
  onJoined,
}: {
  item: Campaign;
  onJoined: (id: number) => void;
}) {
  const [joining, setJoining] = useState(false);
  const [isJoined, setIsJoined] = useState(item.is_joined);

  const pct = item.progress_pct ?? 0;
  const progressWidth = `${Math.min(pct, 100)}%` as any;

  const handleJoin = async () => {
    setJoining(true);
    try {
      await joinContribution(item.id);
      setIsJoined(true);
      onJoined(item.id);
    } catch (e: any) {
      const msg =
        e?.response?.data?.error ||
        e?.response?.data?.detail ||
        "Could not join campaign.";
      Alert.alert("Error", msg);
    } finally {
      setJoining(false);
    }
  };

  return (
    <TouchableOpacity
      style={styles.card}
      activeOpacity={0.82}
      onPress={() => router.push(`/contribution/${item.id}`)}
    >
      {/* Icon */}
      <View style={[styles.cardAvatarWrap, { alignSelf: "flex-start", marginTop: 2 }]}>
        <View style={[styles.cardAvatar, styles.campaignIconBg]}>
          <Ionicons name="megaphone" size={22} color={COLORS.accent} />
        </View>
      </View>

      {/* Body */}
      <View style={styles.cardBody}>
        <Text style={styles.cardTitle} numberOfLines={1}>
          {item.title}
        </Text>

        {!!item.description && (
          <Text style={styles.cardDesc} numberOfLines={2}>
            {item.description}
          </Text>
        )}

        {/* Progress bar */}
        {item.target_amount != null && (
          <View style={styles.progressWrap}>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: progressWidth }]} />
            </View>
            <Text style={styles.progressLabel}>
              KES {item.current_amount.toLocaleString()}
              {" / "}
              {item.target_amount.toLocaleString()}
              {"  "}
              <Text style={styles.progressPct}>{pct.toFixed(0)}%</Text>
            </Text>
          </View>
        )}

        {item.target_amount == null && item.current_amount > 0 && (
          <Text style={styles.progressLabel}>
            KES {item.current_amount.toLocaleString()} raised
          </Text>
        )}

        <View style={styles.cardMeta}>
          <Ionicons name="people-outline" size={13} color={COLORS.textMuted} />
          <Text style={styles.cardMetaText}>
            {item.contributor_count} contributor
            {item.contributor_count !== 1 ? "s" : ""}
          </Text>
          {item.days_left != null && (
            <>
              <Text style={styles.cardMetaDot}>·</Text>
              <Ionicons name="time-outline" size={13} color={COLORS.textMuted} />
              <Text
                style={[
                  styles.cardMetaText,
                  item.days_left === 0 && { color: COLORS.error },
                ]}
              >
                {item.days_left === 0
                  ? "Ends today"
                  : `${item.days_left}d left`}
              </Text>
            </>
          )}
          {!!item.community && (
            <>
              <Text style={styles.cardMetaDot}>·</Text>
              <Text style={styles.cardMetaText} numberOfLines={1}>
                {item.community}
              </Text>
            </>
          )}
        </View>
      </View>

      {/* Action */}
      <View style={styles.cardAction}>
        {isJoined ? (
          <View style={styles.joinedBadge}>
            <Ionicons name="checkmark" size={12} color={COLORS.primary} />
            <Text style={styles.joinedBadgeText}>Joined</Text>
          </View>
        ) : (
          <TouchableOpacity
            style={[styles.joinBtn, { backgroundColor: COLORS.accent }]}
            onPress={handleJoin}
            disabled={joining}
          >
            {joining ? (
              <ActivityIndicator size={12} color={COLORS.white} />
            ) : (
              <Text style={styles.joinBtnText}>Join</Text>
            )}
          </TouchableOpacity>
        )}
      </View>
    </TouchableOpacity>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <View style={styles.emptyWrap}>
      <Ionicons name="search-outline" size={48} color={COLORS.border} />
      <Text style={styles.emptyText}>{message}</Text>
    </View>
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────

export default function DiscoverScreen() {
  const [segment, setSegment] = useState<"communities" | "campaigns">("communities");

  // ── Communities state ─────────────────────────────────────
  const [groups, setGroups]             = useState<Community[]>([]);
  const [groupTotal, setGroupTotal]     = useState(0);
  const [groupHasMore, setGroupHasMore] = useState(false);
  const [groupLoading, setGroupLoading] = useState(false);
  const [groupRefresh, setGroupRefresh] = useState(false);
  const groupOffsetRef                  = useRef(0);
  const [groupQuery, setGroupQuery]     = useState("");
  const [groupCategory, setGroupCategory] = useState("");

  // ── Campaigns state ───────────────────────────────────────
  const [campaigns, setCampaigns]             = useState<Campaign[]>([]);
  const [campaignTotal, setCampaignTotal]     = useState(0);
  const [campaignHasMore, setCampaignHasMore] = useState(false);
  const [campaignLoading, setCampaignLoading] = useState(false);
  const [campaignRefresh, setCampaignRefresh] = useState(false);
  const campaignOffsetRef                     = useRef(0);
  const [campaignQuery, setCampaignQuery]     = useState("");

  // ── Load groups ───────────────────────────────────────────

  const loadGroups = useCallback(
    async (reset = false) => {
      const offset = reset ? 0 : groupOffsetRef.current;
      if (!reset && groupLoading) return;
      if (!reset && !groupHasMore && groups.length > 0) return;

      setGroupLoading(true);
      try {
        const page = await discoverCommunities({
          q:        groupQuery || undefined,
          category: groupCategory || undefined,
          limit:    LIMIT,
          offset,
        });
        if (reset) {
          setGroups(page.results);
          groupOffsetRef.current = page.results.length;
        } else {
          setGroups((prev) => [...prev, ...page.results]);
          groupOffsetRef.current = offset + page.results.length;
        }
        setGroupTotal(page.count);
        setGroupHasMore(page.has_more);
      } catch (e) {
        // silently fail on network issues — show stale data
      } finally {
        setGroupLoading(false);
        setGroupRefresh(false);
      }
    },
    [groupQuery, groupCategory, groupLoading, groupHasMore, groups.length]
  );

  const loadMoreGroups = () => {
    if (groupHasMore && !groupLoading) loadGroups(false);
  };

  const refreshGroups = () => {
    setGroupRefresh(true);
    loadGroups(true);
  };

  // ── Load campaigns ────────────────────────────────────────

  const loadCampaigns = useCallback(
    async (reset = false) => {
      const offset = reset ? 0 : campaignOffsetRef.current;
      if (!reset && campaignLoading) return;
      if (!reset && !campaignHasMore && campaigns.length > 0) return;

      setCampaignLoading(true);
      try {
        const page = await getCampaigns({
          q:      campaignQuery || undefined,
          limit:  LIMIT,
          offset,
        });
        if (reset) {
          setCampaigns(page.results);
          campaignOffsetRef.current = page.results.length;
        } else {
          setCampaigns((prev) => [...prev, ...page.results]);
          campaignOffsetRef.current = offset + page.results.length;
        }
        setCampaignTotal(page.count);
        setCampaignHasMore(page.has_more);
      } catch (e) {
        // silently fail
      } finally {
        setCampaignLoading(false);
        setCampaignRefresh(false);
      }
    },
    [campaignQuery, campaignLoading, campaignHasMore, campaigns.length]
  );

  const loadMoreCampaigns = () => {
    if (campaignHasMore && !campaignLoading) loadCampaigns(false);
  };

  const refreshCampaigns = () => {
    setCampaignRefresh(true);
    loadCampaigns(true);
  };

  // ── Initial load on focus ────────────────────────────────────────────────

  useFocusEffect(
    useCallback(() => {
      groupOffsetRef.current    = 0;
      campaignOffsetRef.current = 0;
      loadGroups(true);
      loadCampaigns(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
  );

  // ── Re-search when query/category changes ────────────────────────────────

  const searchGroupsRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleGroupQueryChange = (v: string) => {
    setGroupQuery(v);
    if (searchGroupsRef.current) clearTimeout(searchGroupsRef.current);
    searchGroupsRef.current = setTimeout(() => {
      groupOffsetRef.current = 0;
      setGroups([]);
      loadGroups(true);
    }, 400);
  };

  const handleCategoryChange = (cat: string) => {
    setGroupCategory(cat);
    groupOffsetRef.current = 0;
    setGroups([]);
    // loadGroups will be triggered by useEffect below via state change
  };

  // Trigger group reload when category changes
  const categoryLoadedRef = useRef(groupCategory);
  if (categoryLoadedRef.current !== groupCategory) {
    categoryLoadedRef.current = groupCategory;
    // intentionally not calling here — handled in effect below
  }

  const searchCampaignsRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleCampaignQueryChange = (v: string) => {
    setCampaignQuery(v);
    if (searchCampaignsRef.current) clearTimeout(searchCampaignsRef.current);
    searchCampaignsRef.current = setTimeout(() => {
      campaignOffsetRef.current = 0;
      setCampaigns([]);
      loadCampaigns(true);
    }, 400);
  };

  // ── Category reload ──────────────────────────────────────────────────────
  // Since loadGroups reads groupCategory from closure, we need a proper effect.
  // But because we don't use useEffect (it's a function component), we defer
  // the reload to the next render using a callback ref pattern.
  const prevCategory = useRef(groupCategory);
  if (prevCategory.current !== groupCategory) {
    prevCategory.current   = groupCategory;
    groupOffsetRef.current = 0;
    // Schedule on next tick to avoid render-phase side effects
    setTimeout(() => loadGroups(true), 0);
  }

  // ─────────────────────────────────────────────────────────────────────────

  const renderGroupsContent = () => (
    <FlatList
      data={groups}
      keyExtractor={(i) => `g-${i.id}`}
      contentContainerStyle={styles.listContent}
      renderItem={({ item }) => (
        <CommunityCard item={item} />
      )}
      ListHeaderComponent={
        <View>
          {/* Search */}
          <View style={styles.searchWrap}>
            <Ionicons
              name="search-outline"
              size={16}
              color={COLORS.textMuted}
              style={styles.searchIcon}
            />
            <TextInput
              style={styles.searchInput}
              placeholder="Search communities…"
              placeholderTextColor={COLORS.textMuted}
              value={groupQuery}
              onChangeText={handleGroupQueryChange}
              returnKeyType="search"
              autoCorrect={false}
            />
            {!!groupQuery && (
              <TouchableOpacity
                onPress={() => handleGroupQueryChange("")}
                style={styles.searchClear}
              >
                <Ionicons name="close-circle" size={16} color={COLORS.textMuted} />
              </TouchableOpacity>
            )}
          </View>

          {/* Category chips */}
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chips}
          >
            {CATEGORIES.map((c) => (
              <TouchableOpacity
                key={c.key}
                style={[
                  styles.chip,
                  groupCategory === c.key && styles.chipActive,
                ]}
                onPress={() => handleCategoryChange(c.key)}
              >
                <Text
                  style={[
                    styles.chipText,
                    groupCategory === c.key && styles.chipTextActive,
                  ]}
                >
                  {c.label}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Result count */}
          {groups.length > 0 && (
            <Text style={styles.resultCount}>
              {groupTotal} {groupTotal !== 1 ? "communities" : "community"} found
            </Text>
          )}
        </View>
      }
      ListEmptyComponent={
        groupLoading ? null : (
          <EmptyState
            message={
              groupQuery || groupCategory
                ? "No communities match your search."
                : "No public communities available right now."
            }
          />
        )
      }
      ListFooterComponent={
        groupLoading ? (
          <ActivityIndicator
            color={COLORS.primary}
            style={{ marginVertical: 20 }}
          />
        ) : null
      }
      onEndReached={loadMoreGroups}
      onEndReachedThreshold={0.4}
      refreshControl={
        <RefreshControl
          refreshing={groupRefresh}
          onRefresh={refreshGroups}
          tintColor={COLORS.primary}
        />
      }
    />
  );

  const renderCampaignsContent = () => (
    <FlatList
      data={campaigns}
      keyExtractor={(i) => `c-${i.id}`}
      contentContainerStyle={styles.listContent}
      renderItem={({ item }) => (
        <CampaignCard
          item={item}
          onJoined={(id) => {
            setCampaigns((prev) =>
              prev.map((c) => (c.id === id ? { ...c, is_joined: true } : c))
            );
          }}
        />
      )}
      ListHeaderComponent={
        <View>
          {/* Search */}
          <View style={styles.searchWrap}>
            <Ionicons
              name="search-outline"
              size={16}
              color={COLORS.textMuted}
              style={styles.searchIcon}
            />
            <TextInput
              style={styles.searchInput}
              placeholder="Search campaigns…"
              placeholderTextColor={COLORS.textMuted}
              value={campaignQuery}
              onChangeText={handleCampaignQueryChange}
              returnKeyType="search"
              autoCorrect={false}
            />
            {!!campaignQuery && (
              <TouchableOpacity
                onPress={() => handleCampaignQueryChange("")}
                style={styles.searchClear}
              >
                <Ionicons name="close-circle" size={16} color={COLORS.textMuted} />
              </TouchableOpacity>
            )}
          </View>

          {campaigns.length > 0 && (
            <Text style={styles.resultCount}>
              {campaignTotal} campaign{campaignTotal !== 1 ? "s" : ""} found
            </Text>
          )}
        </View>
      }
      ListEmptyComponent={
        campaignLoading ? null : (
          <EmptyState
            message={
              campaignQuery
                ? "No campaigns match your search."
                : "No public campaigns available right now."
            }
          />
        )
      }
      ListFooterComponent={
        campaignLoading ? (
          <ActivityIndicator
            color={COLORS.primary}
            style={{ marginVertical: 20 }}
          />
        ) : null
      }
      onEndReached={loadMoreCampaigns}
      onEndReachedThreshold={0.4}
      refreshControl={
        <RefreshControl
          refreshing={campaignRefresh}
          onRefresh={refreshCampaigns}
          tintColor={COLORS.primary}
        />
      }
    />
  );

  return (
    <SafeAreaView style={styles.screen} edges={["top"]}>
      <AppHeader
        title="Discover"
        variant="green"
        leading="back"
        onBack={() => router.back()}
      />

      {/* Segment control */}
      <View style={styles.segmentBar}>
        <TouchableOpacity
          style={[styles.segBtn, segment === "communities" && styles.segBtnActive]}
          onPress={() => setSegment("communities")}
        >
          <Ionicons
            name="people"
            size={15}
            color={segment === "communities" ? COLORS.primary : COLORS.textMuted}
            style={{ marginRight: 5 }}
          />
          <Text
            style={[
              styles.segLabel,
              segment === "communities" && styles.segLabelActive,
            ]}
          >
            Communities
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.segBtn, segment === "campaigns" && styles.segBtnActive]}
          onPress={() => setSegment("campaigns")}
        >
          <Ionicons
            name="megaphone"
            size={15}
            color={segment === "campaigns" ? COLORS.primary : COLORS.textMuted}
            style={{ marginRight: 5 }}
          />
          <Text
            style={[
              styles.segLabel,
              segment === "campaigns" && styles.segLabelActive,
            ]}
          >
            Campaigns
          </Text>
        </TouchableOpacity>
      </View>

      <View style={{ flex: 1 }}>
        {segment === "communities" ? renderGroupsContent() : renderCampaignsContent()}
      </View>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: {
    flex:            1,
    backgroundColor: COLORS.background,
  },

  // ── Segment ──────────────────────────────────────────────
  segmentBar: {
    flexDirection:    "row",
    backgroundColor:  COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
    paddingHorizontal: 16,
    paddingTop:        8,
    paddingBottom:     0,
  },
  segBtn: {
    flexDirection:  "row",
    alignItems:     "center",
    paddingVertical: 10,
    paddingHorizontal: 16,
    marginRight:    4,
    borderBottomWidth: 2,
    borderBottomColor: "transparent",
  },
  segBtnActive: {
    borderBottomColor: COLORS.primary,
  },
  segLabel: {
    fontSize:   FONTS.sm,
    fontWeight: "600",
    color:      COLORS.textMuted,
  },
  segLabelActive: {
    color: COLORS.primary,
  },

  // ── List ─────────────────────────────────────────────────
  listContent: {
    paddingBottom: 40,
  },

  // ── Search ───────────────────────────────────────────────
  searchWrap: {
    flexDirection:   "row",
    alignItems:      "center",
    backgroundColor: COLORS.white,
    borderWidth:     1,
    borderColor:     COLORS.border,
    borderRadius:    RADIUS.lg,
    marginHorizontal: 16,
    marginTop:       12,
    marginBottom:    4,
    paddingHorizontal: 10,
    height:          42,
  },
  searchIcon: { marginRight: 6 },
  searchInput: {
    flex:     1,
    fontSize: FONTS.md,
    color:    COLORS.text,
    height:   42,
  },
  searchClear: { padding: 4 },

  // ── Category chips ────────────────────────────────────────
  chips: {
    paddingHorizontal: 12,
    paddingVertical:   8,
    gap:               6,
  },
  chip: {
    paddingVertical:   5,
    paddingHorizontal: 13,
    borderRadius:      RADIUS.full,
    backgroundColor:   COLORS.white,
    borderWidth:       1,
    borderColor:       COLORS.border,
  },
  chipActive: {
    backgroundColor: COLORS.primary,
    borderColor:     COLORS.primary,
  },
  chipText: {
    fontSize:   FONTS.sm,
    fontWeight: "600",
    color:      COLORS.textSecondary,
  },
  chipTextActive: {
    color: COLORS.white,
  },

  // ── Result count ─────────────────────────────────────────
  resultCount: {
    fontSize:        FONTS.xs,
    color:           COLORS.textMuted,
    marginHorizontal: 16,
    marginBottom:    6,
    marginTop:       2,
  },

  // ── Cards ────────────────────────────────────────────────
  card: {
    flexDirection:    "row",
    alignItems:       "center",
    backgroundColor:  COLORS.white,
    marginHorizontal: 16,
    marginVertical:   5,
    borderRadius:     RADIUS.md,
    padding:          12,
    borderWidth:      1,
    borderColor:      COLORS.divider,
    // subtle shadow
    shadowColor:   "#000",
    shadowOffset:  { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius:  2,
    elevation:     1,
  },
  cardAvatarWrap: {
    marginRight: 12,
  },
  cardAvatar: {
    width:        46,
    height:       46,
    borderRadius: RADIUS.md,
  },
  cardAvatarPlaceholder: {
    backgroundColor: COLORS.primaryPale,
    justifyContent:  "center",
    alignItems:      "center",
  },
  campaignIconBg: {
    backgroundColor: COLORS.accentPale,
    justifyContent:  "center",
    alignItems:      "center",
  },

  cardBody: { flex: 1, marginRight: 8 },
  cardTitleRow: {
    flexDirection: "row",
    alignItems:    "center",
    flexWrap:      "wrap",
    gap:           6,
    marginBottom:  2,
  },
  cardTitle: {
    fontSize:   FONTS.md,
    fontWeight: "700",
    color:      COLORS.text,
    flexShrink: 1,
  },
  categoryChip: {
    backgroundColor: COLORS.primaryPale,
    borderRadius:    RADIUS.full,
    paddingVertical: 2,
    paddingHorizontal: 7,
  },
  categoryChipText: {
    fontSize:   FONTS.xs,
    fontWeight: "600",
    color:      COLORS.primary,
  },
  cardDesc: {
    fontSize:    FONTS.sm,
    color:       COLORS.textSecondary,
    lineHeight:  18,
    marginBottom: 5,
  },
  cardMeta: {
    flexDirection: "row",
    alignItems:    "center",
    flexWrap:      "wrap",
    gap:           3,
    marginTop:     2,
  },
  cardMetaText: {
    fontSize: FONTS.xs,
    color:    COLORS.textMuted,
  },
  cardMetaDot: {
    fontSize: FONTS.xs,
    color:    COLORS.textMuted,
    marginHorizontal: 1,
  },

  // ── Progress bar ─────────────────────────────────────────
  progressWrap: { marginVertical: 5 },
  progressTrack: {
    height:          5,
    backgroundColor: COLORS.divider,
    borderRadius:    RADIUS.full,
    overflow:        "hidden",
    marginBottom:    3,
  },
  progressFill: {
    height:          5,
    backgroundColor: COLORS.accent,
    borderRadius:    RADIUS.full,
  },
  progressLabel: {
    fontSize: FONTS.xs,
    color:    COLORS.textMuted,
  },
  progressPct: {
    fontWeight: "700",
    color:      COLORS.accent,
  },

  // ── Card action ──────────────────────────────────────────
  cardAction: {
    alignItems:  "center",
    minWidth:    60,
  },
  joinBtn: {
    backgroundColor: COLORS.primary,
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius:    RADIUS.full,
    minWidth:        52,
    alignItems:      "center",
  },
  joinBtnText: {
    fontSize:   FONTS.sm,
    fontWeight: "700",
    color:      COLORS.white,
  },
  joinedBadge: {
    flexDirection:   "row",
    alignItems:      "center",
    borderWidth:     1,
    borderColor:     COLORS.primary,
    borderRadius:    RADIUS.full,
    paddingVertical: 4,
    paddingHorizontal: 9,
    gap:             3,
  },
  joinedBadgeText: {
    fontSize:   FONTS.xs,
    fontWeight: "600",
    color:      COLORS.primary,
  },

  // ── Empty ─────────────────────────────────────────────────
  emptyWrap: {
    alignItems:  "center",
    paddingTop:  60,
    paddingHorizontal: 32,
  },
  emptyText: {
    marginTop:   14,
    fontSize:    FONTS.md,
    color:       COLORS.textMuted,
    textAlign:   "center",
    lineHeight:  22,
  },
});

