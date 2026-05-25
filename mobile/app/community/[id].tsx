import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  FlatList,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Modal,
  Alert,
  Share,
  Linking,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams, useFocusEffect } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage"; // used for non-sensitive conv timestamps
import * as storage from "../../utils/secureStorage";
import { getCommunity, getCommunityMembers, deleteCommunity, leaveCommunity, assignMemberRole, removeMember, updateCommunity, Community, CommunityMember } from "../../api/communities";
import { getCommunityConversations, Conversation } from "../../api/conversations";
import { on } from "../../utils/eventBus";
import { getCommunityContributions, Contribution } from "../../api/contributions";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import Avatar from "../../components/app/Avatar";

type Tab = "members" | "conversations" | "contributions" | "meet";

const MEET_PLATFORMS = [
  {
    name: "Google Meet",
    icon: "videocam" as const,
    color: "#1A73E8",
    url: "https://meet.google.com",
    description: "Free video meetings by Google",
  },
  {
    name: "Microsoft Teams",
    icon: "people" as const,
    color: "#6264A7",
    url: "https://teams.microsoft.com",
    description: "Chat, meet and collaborate",
  },
  {
    name: "Zoom",
    icon: "camera" as const,
    color: "#2D8CFF",
    url: "https://zoom.us/join",
    description: "HD video and audio conferencing",
  },
];

function MeetPlaceholder() {
  return (
    <View style={meetStyles.container}>
      <Ionicons name="videocam-outline" size={48} color={COLORS.primary} style={{ marginBottom: 12 }} />
      <Text style={meetStyles.heading}>Virtual Meetings</Text>
      <Text style={meetStyles.sub}>
        Schedule or join community meetings using your preferred platform.
        Share the link in Discussions so everyone can join.
      </Text>

      {MEET_PLATFORMS.map((p) => (
        <TouchableOpacity
          key={p.name}
          style={meetStyles.card}
          onPress={() => Linking.openURL(p.url).catch(() => Alert.alert("Error", "Could not open link."))}
          activeOpacity={0.75}
        >
          <View style={[meetStyles.iconBox, { backgroundColor: p.color + "18" }]}>
            <Ionicons name={p.icon} size={26} color={p.color} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={meetStyles.cardName}>{p.name}</Text>
            <Text style={meetStyles.cardDesc}>{p.description}</Text>
          </View>
          <View style={meetStyles.openBtn}>
            <Text style={meetStyles.openBtnText}>Open</Text>
          </View>
        </TouchableOpacity>
      ))}

      <View style={meetStyles.hint}>
        <Ionicons name="information-circle-outline" size={16} color={COLORS.textMuted} />
        <Text style={meetStyles.hintText}>
          Full in-app meeting scheduling coming soon.
        </Text>
      </View>
    </View>
  );
}

const meetStyles = StyleSheet.create({
  container: {
    alignItems: "center",
    paddingHorizontal: 20,
    paddingTop: 24,
    paddingBottom: 40,
  },
  heading: {
    fontSize: 20,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 8,
  },
  sub: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: "center",
    lineHeight: 20,
    marginBottom: 28,
  },
  card: {
    flexDirection: "row",
    alignItems: "center",
    width: "100%",
    backgroundColor: COLORS.white,
    borderRadius: 14,
    padding: 14,
    marginBottom: 12,
    gap: 14,
    borderWidth: 1,
    borderColor: COLORS.border,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  iconBox: {
    width: 48,
    height: 48,
    borderRadius: 12,
    justifyContent: "center",
    alignItems: "center",
  },
  cardName: {
    fontSize: 15,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 2,
  },
  cardDesc: {
    fontSize: 12,
    color: COLORS.textMuted,
  },
  openBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  openBtnText: {
    color: COLORS.white,
    fontSize: 13,
    fontWeight: "700",
  },
  hint: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 16,
    paddingHorizontal: 8,
  },
  hintText: {
    fontSize: 12,
    color: COLORS.textMuted,
    fontStyle: "italic",
    flex: 1,
  },
});

function timeShort(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function CommunityDetailScreen() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const communityId = Number(id);

  const [community, setCommunity] = useState<Community | null>(null);
  const [tab, setTab] = useState<Tab>("members");
  const [members, setMembers] = useState<CommunityMember[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [contributions, setContributions] = useState<Contribution[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const firstLoad = useRef(true);
  const [menuVisible, setMenuVisible] = useState(false);
  const [myPhone, setMyPhone] = useState("");
  const [copied, setCopied] = useState(false);
  const [selectedMember, setSelectedMember] = useState<CommunityMember | null>(null);
  const [memberActionLoading, setMemberActionLoading] = useState(false);
  const [clearedConvs, setClearedConvs] = useState<Record<number, string>>({});

  // Edit community modal
  const [showEdit, setShowEdit]       = useState(false);
  const [editName, setEditName]       = useState("");
  const [editDesc, setEditDesc]       = useState("");
  const [editPrivate, setEditPrivate] = useState(false);
  const [editSaving, setEditSaving]   = useState(false);

  useEffect(() => {
    storage.getItem("phone").then((p) => p && setMyPhone(p));
  }, []);

  const load = useCallback(async () => {
    try {
      const phone = await storage.getItem("phone");
      if (phone && !myPhone) setMyPhone(phone);

      const [c, m, conv, contrib] = await Promise.all([
        getCommunity(communityId),
        getCommunityMembers(communityId),
        getCommunityConversations(communityId),
        getCommunityContributions(communityId),
      ]);
      setCommunity(c);
      setMembers(m);
      setConversations(conv);
      setContributions(contrib);

      // Load which conversations this user has cleared
      if (phone && conv.length > 0) {
        const cleared: Record<number, string> = {};
        await Promise.all(conv.map(async (cv) => {
          const ts = await AsyncStorage.getItem(`conv_cleared_${phone}_${cv.id}`);
          if (ts) cleared[cv.id] = ts;
        }));
        setClearedConvs(cleared);
      }
    } catch (e: any) {
      if (e?.response?.status === 404) setNotFound(true);
    }
  }, [communityId]);

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  useFocusEffect(useCallback(() => {
    if (firstLoad.current) {
      firstLoad.current = false;
    } else {
      setRefreshing(true);
      load().finally(() => setRefreshing(false));
    }
    // Poll unread counts while this screen is visible
    const interval = setInterval(() => {
      getCommunityConversations(communityId).then(setConversations).catch(() => {});
    }, 8000);
    return () => clearInterval(interval);
  }, [load, communityId]));

  useEffect(() => {
    return on('newMessage', () => {
      getCommunityConversations(communityId).then(setConversations).catch(() => {});
    });
  }, [communityId]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const isCreator = community?.created_by === myPhone;
  const isAdmin   = isCreator || members.some((m) => m.phone_number === myPhone && m.role === 'admin');

  const handleShare = async () => {
    setMenuVisible(false);
    if (!community?.invite_code) return;
    await Share.share({
      message: `Join "${community.name}" on WEPL!\n\nUse invite code: ${community.invite_code}`,
      title: `Join ${community.name} on WEPL`,
    });
  };

  const handleCopyCode = async () => {
    if (!community?.invite_code) return;
    await Clipboard.setStringAsync(community.invite_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleAssignRole = async (role: 'admin' | 'member') => {
    if (!selectedMember || !community) return;
    setMemberActionLoading(true);
    try {
      const updated = await assignMemberRole(communityId, selectedMember.id, role);
      setMembers((prev) => prev.map((m) => m.id === updated.id ? updated : m));
      setSelectedMember((prev) => prev ? { ...prev, role: updated.role } : null);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error ?? "Failed to update role.");
    } finally {
      setMemberActionLoading(false);
    }
  };

  const handleRemoveMember = () => {
    if (!selectedMember || !community) return;
    Alert.alert(
      "Remove Member",
      `Remove ${selectedMember.name} from ${community.name}?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: async () => {
            setMemberActionLoading(true);
            try {
              await removeMember(communityId, selectedMember.id);
              setMembers((prev) => prev.filter((m) => m.id !== selectedMember.id));
              setSelectedMember(null);
            } catch (e: any) {
              Alert.alert("Error", e?.response?.data?.error ?? "Failed to remove member.");
            } finally {
              setMemberActionLoading(false);
            }
          },
        },
      ]
    );
  };

  const handleLeave = () => {
    setMenuVisible(false);
    Alert.alert(
      "Leave Community",
      `Leave "${community?.name}"? You can rejoin using an invite code.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Leave",
          style: "destructive",
          onPress: async () => {
            try {
              await leaveCommunity(communityId);
              router.replace("/(drawer)");
            } catch (e: any) {
              Alert.alert("Error", e?.response?.data?.error || "Could not leave community.");
            }
          },
        },
      ]
    );
  };

  const handleEditOpen = () => {
    setMenuVisible(false);
    setEditName(community?.name ?? "");
    setEditDesc(community?.description ?? "");
    setEditPrivate(community?.is_private ?? false);
    setShowEdit(true);
  };

  const handleSaveEdit = async () => {
    if (!editName.trim()) { Alert.alert("Required", "Community name cannot be empty."); return; }
    setEditSaving(true);
    try {
      const updated = await updateCommunity(communityId, {
        name: editName.trim(),
        description: editDesc.trim() || undefined,
        is_private: editPrivate,
      });
      setCommunity(updated);
      setShowEdit(false);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to update community.");
    } finally {
      setEditSaving(false);
    }
  };

  const handleDelete = () => {
    setMenuVisible(false);
    Alert.alert(
      "Delete Community",
      `Are you sure you want to delete "${community?.name}"? This cannot be undone.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              await deleteCommunity(communityId);
              router.replace("/(drawer)");
            } catch (e: any) {
              Alert.alert("Error", e?.response?.data?.error || "Failed to delete community.");
            }
          },
        },
      ]
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title={String(name ?? "Community")} variant="light" leading="back" />
        <View style={styles.center}>
          <ActivityIndicator size="large" color={COLORS.primary} />
        </View>
      </SafeAreaView>
    );
  }

  if (notFound) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title="Community" variant="light" leading="back" />
        <View style={styles.center}>
          <Ionicons name="people-outline" size={56} color={COLORS.textMuted} />
          <Text style={styles.notFoundTitle}>Community not found</Text>
          <Text style={styles.notFoundSub}>
            This community may have been deleted or is no longer available.
          </Text>
          <TouchableOpacity style={styles.notFoundBtn} onPress={() => router.back()}>
            <Text style={styles.notFoundBtnText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const stat = `${community?.member_count ?? members.length} ${
    (community?.member_count ?? members.length) === 1 ? "Member" : "Members"
  }`;
  const contribStat = `${contributions.length} ${
    contributions.length === 1 ? "Contribution" : "Contributions"
  }`;

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader
        title={community?.name ?? String(name ?? "")}
        variant="light"
        leading="back"
        rightIcon="more"
        onRightPress={() => setMenuVisible(true)}
      />

      {/* 3-dots menu */}
      <Modal visible={menuVisible} transparent animationType="fade" onRequestClose={() => setMenuVisible(false)}>
        <TouchableOpacity style={styles.menuOverlay} activeOpacity={1} onPress={() => setMenuVisible(false)}>
          <View style={styles.menuCard}>
            <MenuItem
              icon="share-outline"
              label="Share Invite Link"
              onPress={handleShare}
            />
            {isAdmin && (
              <MenuItem
                icon="create-outline"
                label="Edit Community"
                onPress={handleEditOpen}
              />
            )}
            {!isCreator && (
              <MenuItem
                icon="exit-outline"
                label="Leave Community"
                color={COLORS.error}
                onPress={handleLeave}
              />
            )}
            {isCreator && (
              <MenuItem
                icon="trash-outline"
                label="Delete Community"
                color={COLORS.error}
                onPress={handleDelete}
              />
            )}
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Edit community modal */}
      <Modal visible={showEdit} transparent animationType="slide" onRequestClose={() => setShowEdit(false)}>
        <KeyboardAvoidingView style={{ flex: 1, justifyContent: "flex-end" }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setShowEdit(false)} />
          <View style={styles.memberSheet}>
            <View style={styles.sheetHandle} />
            <Text style={[styles.memberPhone, { marginBottom: 4 }]}>Edit Community</Text>
            <Text style={[styles.memberPhoneSub, { marginBottom: 20 }]}>Changes are visible to all members.</Text>

            <Text style={editSheetStyles.fieldLabel}>Name</Text>
            <TextInput
              style={editSheetStyles.input}
              value={editName}
              onChangeText={setEditName}
              placeholder="Community name"
              placeholderTextColor={COLORS.textMuted}
              maxLength={120}
            />

            <Text style={editSheetStyles.fieldLabel}>Description</Text>
            <TextInput
              style={[editSheetStyles.input, { height: 90, textAlignVertical: "top" }]}
              value={editDesc}
              onChangeText={setEditDesc}
              placeholder="What is this community about?"
              placeholderTextColor={COLORS.textMuted}
              multiline
              maxLength={500}
            />

            <TouchableOpacity
              style={editSheetStyles.toggleRow}
              onPress={() => setEditPrivate((p) => !p)}
              activeOpacity={0.7}
            >
              <View style={{ flex: 1 }}>
                <Text style={editSheetStyles.toggleLabel}>Private community</Text>
                <Text style={editSheetStyles.toggleSub}>
                  {editPrivate ? "Invitation only — not listed in Discover" : "Anyone can find and request to join"}
                </Text>
              </View>
              <View style={[editSheetStyles.toggle, editPrivate && editSheetStyles.toggleOn]}>
                <View style={[editSheetStyles.toggleThumb, editPrivate && editSheetStyles.toggleThumbOn]} />
              </View>
            </TouchableOpacity>

            <View style={styles.memberActions}>
              <TouchableOpacity
                style={[styles.memberActionBtn, { backgroundColor: COLORS.primary, borderRadius: RADIUS.md, justifyContent: "center" }]}
                onPress={handleSaveEdit}
                disabled={editSaving}
              >
                {editSaving
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={{ color: COLORS.white, fontWeight: "700", fontSize: FONTS.md, textAlign: "center" }}>Save Changes</Text>}
              </TouchableOpacity>
            </View>

            <TouchableOpacity style={styles.memberCloseBtn} onPress={() => setShowEdit(false)}>
              <Text style={styles.memberCloseBtnText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Member profile sheet */}
      <Modal
        visible={selectedMember !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setSelectedMember(null)}
      >
        <View style={{ flex: 1, justifyContent: "flex-end" }}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setSelectedMember(null)} />
          <View style={styles.memberSheet}>
            <View style={styles.sheetHandle} />

            {/* Profile info */}
            <View style={styles.memberProfile}>
              <Avatar name={selectedMember?.name ?? ""} uri={selectedMember?.profile_photo} size={72} />
              <Text style={styles.memberPhone}>{selectedMember?.name}</Text>
              <Text style={styles.memberPhoneSub}>{selectedMember?.phone_number}</Text>
              <View style={[
                styles.memberRolePill,
                selectedMember?.phone_number === community?.created_by
                  ? styles.memberRolePillOwner
                  : styles.memberRolePillDefault,
              ]}>
                <Text style={[
                  styles.memberRolePillText,
                  selectedMember?.phone_number === community?.created_by && { color: COLORS.accent },
                ]}>
                  {selectedMember?.phone_number === community?.created_by ? "Owner" : selectedMember?.role}
                </Text>
              </View>
              <Text style={styles.memberJoined}>
                Joined {selectedMember?.joined_at ? new Date(selectedMember.joined_at).toLocaleDateString([], { month: "long", year: "numeric" }) : ""}
              </Text>
            </View>

            {/* Admin actions — only visible to creator, not on themselves */}
            {isCreator && selectedMember?.phone_number !== community?.created_by && (
              memberActionLoading ? (
                <ActivityIndicator size="large" color={COLORS.primary} style={{ marginVertical: 24 }} />
              ) : (
                <View style={styles.memberActions}>
                  {selectedMember?.role !== 'admin' ? (
                    <TouchableOpacity style={styles.memberActionBtn} onPress={() => handleAssignRole('admin')}>
                      <View style={[styles.memberActionIcon, { backgroundColor: COLORS.primary + "18" }]}>
                        <Ionicons name="shield-checkmark-outline" size={20} color={COLORS.primary} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.memberActionTitle}>Make Admin</Text>
                        <Text style={styles.memberActionSub}>Grant admin rights to this member</Text>
                      </View>
                      <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                    </TouchableOpacity>
                  ) : (
                    <TouchableOpacity style={styles.memberActionBtn} onPress={() => handleAssignRole('member')}>
                      <View style={[styles.memberActionIcon, { backgroundColor: COLORS.textMuted + "22" }]}>
                        <Ionicons name="shield-outline" size={20} color={COLORS.textMuted} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.memberActionTitle}>Remove Admin</Text>
                        <Text style={styles.memberActionSub}>Revert to regular member</Text>
                      </View>
                      <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                    </TouchableOpacity>
                  )}
                  <View style={styles.memberActionDivider} />
                  <TouchableOpacity style={styles.memberActionBtn} onPress={handleRemoveMember}>
                    <View style={[styles.memberActionIcon, { backgroundColor: COLORS.error + "18" }]}>
                      <Ionicons name="person-remove-outline" size={20} color={COLORS.error} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.memberActionTitle, { color: COLORS.error }]}>Remove from Community</Text>
                      <Text style={styles.memberActionSub}>This member will lose access</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                  </TouchableOpacity>
                </View>
              )
            )}

            <TouchableOpacity style={styles.memberCloseBtn} onPress={() => setSelectedMember(null)}>
              <Text style={styles.memberCloseBtnText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      <FlatList
        data={
          tab === "members"       ? members       :
          tab === "conversations" ? conversations :
          tab === "contributions" ? contributions :
          []
        }
        keyExtractor={(item: any) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />
        }
        ListHeaderComponent={
          <>
            {/* Profile section */}
            <View style={styles.profile}>
              <Avatar name={community?.name ?? ""} uri={community?.community_photo} size={140} />
              <Text style={styles.cName}>{community?.name}</Text>
              <Text style={styles.cStat}>{stat}</Text>
              <Text style={styles.cStat}>{contribStat}</Text>

              {/* Invite code card */}
              {community?.invite_code && (
                <View style={styles.inviteCard}>
                  <View style={styles.inviteLeft}>
                    <Text style={styles.inviteLabel}>Invite Code</Text>
                    <Text style={styles.inviteCode}>{community.invite_code}</Text>
                  </View>
                  <View style={styles.inviteActions}>
                    <TouchableOpacity style={styles.inviteBtn} onPress={handleCopyCode}>
                      <Ionicons
                        name={copied ? "checkmark" : "copy-outline"}
                        size={16}
                        color={copied ? COLORS.success : COLORS.primary}
                      />
                      <Text style={[styles.inviteBtnText, copied && { color: COLORS.success }]}>
                        {copied ? "Copied!" : "Copy"}
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.inviteBtn} onPress={handleShare}>
                      <Ionicons name="share-outline" size={16} color={COLORS.primary} />
                      <Text style={styles.inviteBtnText}>Share</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>

            {/* Segmented control */}
            {(() => {
              const totalUnread = conversations.reduce((sum, c) => sum + (c.unread_count ?? 0), 0);
              const tabDefs: { key: Tab; label: string }[] = [
                { key: "members",       label: "Members" },
                { key: "conversations", label: "Discussions" },
                { key: "contributions", label: "Contributions" },
                { key: "meet",          label: "Meet" },
              ];
              return (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabScroll} contentContainerStyle={{ paddingHorizontal: 12, gap: 8, paddingVertical: 10 }}>
                  {tabDefs.map(({ key: t, label }) => (
                    <TouchableOpacity
                      key={t}
                      style={[styles.tab, tab === t && styles.tabActive]}
                      onPress={() => setTab(t)}
                    >
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
                        <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>{label}</Text>
                        {t === "conversations" && totalUnread > 0 && (
                          <View style={styles.tabBadge}>
                            <Text style={styles.tabBadgeText}>{totalUnread > 99 ? "99+" : totalUnread}</Text>
                          </View>
                        )}
                      </View>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              );
            })()}

            {/* Action rows */}
            <View style={styles.actionsBlock}>
              <ActionRow
                icon="person-add-outline"
                label="Add Members"
                onPress={() => router.push({ pathname: `/community/${communityId}/add-members` })}
              />
              <View style={styles.actionDivider} />
              <ActionRow
                icon="chatbubble-outline"
                label="New Conversation"
                onPress={() => router.push({
                  pathname: `/conversation/create`,
                  params: { communityId: String(communityId) },
                })}
              />
              {isAdmin && (
                <>
                  <View style={styles.actionDivider} />
                  <ActionRow
                    icon="wallet-outline"
                    label="New Contribution"
                    onPress={() => router.push({
                      pathname: `/contribution/create`,
                      params: { communityId: String(communityId) },
                    })}
                  />
                </>
              )}
              {community?.has_welfare_fund && (
                <>
                  <View style={styles.actionDivider} />
                  <ActionRow
                    icon="heart-outline"
                    label="Welfare Fund"
                    onPress={() => router.push({
                      pathname: `/welfare/${communityId}`,
                      params: { name: community?.name, isAdmin: isAdmin ? "1" : "0" },
                    })}
                  />
                </>
              )}
              {community?.has_shares_fund && (
                <>
                  <View style={styles.actionDivider} />
                  <ActionRow
                    icon="bar-chart-outline"
                    label="Shares Fund"
                    onPress={() => router.push({
                      pathname: `/shares/${communityId}`,
                      params: { name: community?.name },
                    })}
                  />
                </>
              )}
            </View>

          </>
        }
        renderItem={({ item }) => {
          if (tab === "members") {
            const m = item as CommunityMember;
            const isOwnerRow = m.phone_number === community?.created_by;
            return (
              <TouchableOpacity
                style={styles.row}
                onPress={() => setSelectedMember(m)}
                activeOpacity={0.7}
              >
                <Avatar name={m.name} uri={m.profile_photo} size={40} />
                <View style={styles.rowText}>
                  <Text style={styles.rowName}>{m.name}</Text>
                  <Text style={styles.rowSub}>{m.phone_number}</Text>
                </View>
                {isOwnerRow ? (
                  <View style={[styles.roleBadge, { backgroundColor: COLORS.accent + "22" }]}>
                    <Text style={[styles.roleBadgeText, { color: COLORS.accent }]}>owner</Text>
                  </View>
                ) : m.role !== "member" ? (
                  <View style={styles.roleBadge}>
                    <Text style={styles.roleBadgeText}>{m.role}</Text>
                  </View>
                ) : null}
                <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
              </TouchableOpacity>
            );
          }
          if (tab === "conversations") {
            const c = item as Conversation;
            const hasUnread = c.unread_count > 0;
            const myMember = members.find((m) => m.phone_number === myPhone);
            const myRole = isCreator ? 'admin' : (myMember?.role ?? 'member');

            // If user cleared this chat and the last message predates the clear, hide it
            const clearedAt = clearedConvs[c.id];
            const lastMsgHidden = !!(
              clearedAt &&
              (!c.last_message || new Date(c.last_message.created_at) <= new Date(clearedAt))
            );

            return (
              <TouchableOpacity
                style={styles.row}
                onPress={() =>
                  router.push({
                    pathname: `/conversation/${c.id}`,
                    params: { topic: c.topic, communityId: String(communityId), createdBy: c.created_by, myRole },
                  })
                }
              >
                <Avatar name={c.topic} uri={c.photo} size={48} />
                <View style={{ flex: 1 }}>
                  <Text style={[styles.rowName, hasUnread && { fontWeight: "800" }]}>{c.topic}</Text>
                  <Text style={[styles.rowSub, hasUnread && { color: COLORS.text, fontWeight: "500" }]} numberOfLines={1}>
                    {lastMsgHidden ? "No messages yet" : (c.last_message?.content ?? "No messages yet")}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end", gap: 4 }}>
                  {c.last_message && !lastMsgHidden && (
                    <Text style={styles.rowTime}>{timeShort(c.last_message.created_at)}</Text>
                  )}
                  {hasUnread && (
                    <View style={styles.unreadBadge}>
                      <Text style={styles.unreadBadgeText}>
                        {c.unread_count > 99 ? "99+" : c.unread_count}
                      </Text>
                    </View>
                  )}
                </View>
              </TouchableOpacity>
            );
          }
          const x = item as Contribution;
          const cur = Number(x.current_amount);
          const tgt = x.target_amount ? Number(x.target_amount) : 0;
          const pct = tgt > 0 ? Math.min((cur / tgt) * 100, 100) : 0;
          return (
            <TouchableOpacity
              style={styles.contribCard}
              onPress={() => router.push({ pathname: `/contribution/${x.id}` })}
            >
              <Text style={styles.contribTitle}>{x.title}</Text>
              <Text style={styles.contribAmount}>
                KES {cur.toLocaleString()} {tgt > 0 ? `/ ${tgt.toLocaleString()}` : ""}
              </Text>
              {tgt > 0 && (
                <View style={styles.progressBg}>
                  <View style={[styles.progressFill, { width: `${pct}%` }]} />
                </View>
              )}
            </TouchableOpacity>
          );
        }}
        ListEmptyComponent={
          tab === "meet" ? null :
          <Text style={styles.emptyText}>
            {tab === "members" ? "No members yet" :
             tab === "conversations" ? "No discussions yet" :
             "No contributions yet"}
          </Text>
        }
        ItemSeparatorComponent={() =>
          tab === "contributions" ? <View style={{ height: 10 }} /> : <View style={styles.divider} />
        }
      />

    </SafeAreaView>
  );
}

function ActionRow({
  icon,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.actionRow} onPress={onPress}>
      <View style={styles.actionIcon}>
        <Ionicons name={icon} size={20} color={COLORS.white} />
      </View>
      <Text style={styles.actionLabel}>{label}</Text>
      <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
    </TouchableOpacity>
  );
}

function MenuItem({
  icon,
  label,
  color,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  color?: string;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.menuItem} onPress={onPress}>
      <Ionicons name={icon} size={20} color={color ?? COLORS.text} />
      <Text style={[styles.menuItemText, color ? { color } : {}]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 32, gap: 12 },
  notFoundTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginTop: 8 },
  notFoundSub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },
  notFoundBtn:   { marginTop: 8, paddingHorizontal: 28, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.primary },
  notFoundBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },

  profile: { alignItems: "center", paddingVertical: 20 },
  cName:   { marginTop: 14, fontSize: FONTS.xl, fontWeight: "bold", color: COLORS.text },
  cStat:   { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 4 },

  inviteCard: {
    marginTop: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: COLORS.primaryBg,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: RADIUS.lg,
    paddingHorizontal: 16,
    paddingVertical: 12,
    width: "90%",
  },
  inviteLeft: { gap: 2 },
  inviteLabel: { fontSize: 11, color: COLORS.textMuted, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.5 },
  inviteCode: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, letterSpacing: 3 },
  inviteActions: { flexDirection: "row", gap: 8 },
  inviteBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 7,
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.border,
  },
  inviteBtnText: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },

  tabScroll:     { flexGrow: 0 },
  tab:           { paddingHorizontal: 14, paddingVertical: 7, borderRadius: RADIUS.full, backgroundColor: COLORS.white, borderWidth: 1, borderColor: COLORS.border },
  tabActive:     { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  tabText:       { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },
  tabTextActive: { color: COLORS.white },
  tabBadge: {
    minWidth: 18, height: 18, borderRadius: 9,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
    paddingHorizontal: 4,
  },
  tabBadgeText: { fontSize: 10, fontWeight: "700", color: COLORS.white },

  actionsBlock: { backgroundColor: COLORS.white, marginBottom: 4 },
  actionRow: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 16, paddingHorizontal: 20, gap: 14,
  },
  actionIcon: {
    width: 40, height: 40, borderRadius: RADIUS.full,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
  },
  actionLabel: { flex: 1, fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  actionDivider: { height: 1, backgroundColor: COLORS.divider, marginLeft: 74 },

  row: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 12, paddingHorizontal: 20,
    backgroundColor: COLORS.white, gap: 14,
  },
  rowText: { flex: 1 },
  rowName: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  rowSub:  { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 1 },
  rowTime: { fontSize: 11, color: COLORS.textMuted },
  divider: { height: 1, backgroundColor: COLORS.divider, marginLeft: 74 },

  unreadBadge: {
    minWidth: 20, height: 20, borderRadius: 10,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
    paddingHorizontal: 5,
  },
  unreadBadgeText: { fontSize: 11, fontWeight: "700", color: COLORS.white },

  roleBadge: {
    paddingHorizontal: 8, paddingVertical: 3,
    backgroundColor: COLORS.primaryPale, borderRadius: RADIUS.full,
  },
  roleBadgeText: { fontSize: 10, color: COLORS.primary, fontWeight: "700", textTransform: "uppercase" },

  contribCard: {
    backgroundColor: COLORS.white,
    marginHorizontal: 16,
    borderRadius: RADIUS.lg,
    padding: 14,
  },
  contribTitle: { fontSize: FONTS.md, fontWeight: "bold", color: COLORS.text, marginBottom: 6 },
  contribAmount: { fontSize: FONTS.sm, color: COLORS.textSecondary, marginBottom: 8 },
  progressBg: { height: 6, backgroundColor: COLORS.divider, borderRadius: RADIUS.full, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: COLORS.primary },

  emptyText: {
    textAlign: "center",
    color: COLORS.textMuted,
    paddingVertical: 32,
    fontSize: FONTS.sm,
  },

  // Member profile sheet
  memberSheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    paddingHorizontal: 20, paddingBottom: 40, paddingTop: 12,
  },
  sheetHandle: {
    width: 36, height: 4, borderRadius: 2,
    backgroundColor: COLORS.divider, alignSelf: "center", marginBottom: 20,
  },
  memberProfile: { alignItems: "center", marginBottom: 24, gap: 4 },
  memberPhone: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginTop: 10 },
  memberPhoneSub: { fontSize: FONTS.sm, color: COLORS.textMuted },
  memberRolePill: {
    paddingHorizontal: 12, paddingVertical: 4,
    borderRadius: RADIUS.full,
  },
  memberRolePillDefault: { backgroundColor: COLORS.primaryBg },
  memberRolePillOwner: { backgroundColor: COLORS.accent + "22" },
  memberRolePillText: {
    fontSize: FONTS.sm, fontWeight: "700",
    color: COLORS.primary, textTransform: "capitalize",
  },
  memberJoined: { fontSize: FONTS.sm, color: COLORS.textMuted },

  memberActions: {
    backgroundColor: COLORS.background,
    borderRadius: RADIUS.lg, marginBottom: 16, overflow: "hidden",
  },
  memberActionBtn: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 14, paddingHorizontal: 14, gap: 12,
    backgroundColor: COLORS.white,
  },
  memberActionIcon: {
    width: 40, height: 40, borderRadius: RADIUS.full,
    justifyContent: "center", alignItems: "center",
  },
  memberActionTitle: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 1 },
  memberActionSub: { fontSize: FONTS.sm, color: COLORS.textMuted },
  memberActionDivider: { height: 1, backgroundColor: COLORS.divider, marginLeft: 66 },
  memberCloseBtn: {
    height: 46,
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: RADIUS.md, justifyContent: "center", alignItems: "center",
  },
  memberCloseBtnText: { fontSize: FONTS.md, color: COLORS.textSecondary, fontWeight: "600" },

  menuOverlay: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.3)",
    justifyContent: "flex-start", alignItems: "flex-end",
    paddingTop: 90, paddingRight: 16,
  },
  menuCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    paddingVertical: 8,
    minWidth: 200,
    shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  menuItem: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 16, paddingVertical: 14, gap: 12,
  },
  menuItemText: { fontSize: FONTS.md, fontWeight: "500", color: COLORS.text },

});

const editSheetStyles = StyleSheet.create({
  fieldLabel: {
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginBottom: 6, marginTop: 4, textTransform: "uppercase", letterSpacing: 0.4,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background, marginBottom: 12,
  },
  toggleRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingVertical: 14,
    borderTopWidth: 1, borderTopColor: COLORS.divider,
    marginTop: 4, marginBottom: 16,
  },
  toggleLabel: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  toggleSub:   { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 2 },
  toggle: {
    width: 44, height: 26, borderRadius: 13,
    backgroundColor: COLORS.border,
    justifyContent: "center", paddingHorizontal: 2,
  },
  toggleOn:    { backgroundColor: COLORS.primary },
  toggleThumb: {
    width: 20, height: 20, borderRadius: 10, backgroundColor: COLORS.white,
    shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 4, shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
  toggleThumbOn: { alignSelf: "flex-end" },
});
