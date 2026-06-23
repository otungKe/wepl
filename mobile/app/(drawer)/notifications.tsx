import { useState, useCallback } from "react";
import {
  View, Text, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, RefreshControl,
  Modal, Alert, Pressable,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  getNotifications, markRead, markAllRead,
  deleteNotification, deleteAllNotifications,
  Notification,
} from "../../api/notifications";
import {
  actionJoinRequest as actionCommunityJoinRequest,
} from "../../api/communities";
import {
  actionJoinRequest   as actionContribJoinRequest,
  respondToContributionInvite,
  voteDisbursement,
  voteWelfareClaim,
  actionAdvance,
} from "../../api/contributions";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";

// ── Icon + colour for every notification type ────────────────────────────────
const TYPE_META: Record<string, { icon: string; color: string }> = {
  // Community
  community_join:               { icon: "people",             color: COLORS.primary },
  join_request:                 { icon: "person-add",         color: COLORS.primary },
  join_approved:                { icon: "checkmark-circle",   color: COLORS.success },
  join_rejected:                { icon: "close-circle",       color: COLORS.error   },
  // Chat
  conversation_created:         { icon: "chatbubbles",        color: "#6D28D9" },
  new_message:                  { icon: "chatbubble",         color: COLORS.primary },
  // Contributions
  contribution_payment:         { icon: "arrow-up-circle",    color: COLORS.success },
  payment_recorded:             { icon: "receipt",            color: "#0891B2"       },
  contribution_milestone:       { icon: "trophy",             color: COLORS.accent   },
  contribution_joined:          { icon: "person-add",         color: COLORS.primary  },
  // Contribution join/invite
  contribution_join_request:    { icon: "person-add",         color: COLORS.primary  },
  contribution_invite:          { icon: "mail",               color: "#6D28D9"       },
  contribution_join_approved:   { icon: "checkmark-circle",   color: COLORS.success  },
  contribution_join_rejected:   { icon: "close-circle",       color: COLORS.error    },
  contribution_invite_accepted: { icon: "people",             color: COLORS.success  },
  // Amendments
  amendment_proposed:           { icon: "git-pull-request",  color: COLORS.accent   },
  amendment_approved:           { icon: "checkmark-done",    color: COLORS.success  },
  amendment_rejected:           { icon: "close-circle",      color: COLORS.error    },
  // ROSCA
  rosca_rotation_set:           { icon: "refresh-circle",    color: COLORS.primary  },
  rosca_payout:                 { icon: "cash",              color: COLORS.success  },
  rosca_payout_confirmed:       { icon: "checkmark-done-circle", color: COLORS.success },
  // Disbursements
  disbursement_requested:       { icon: "git-pull-request",  color: COLORS.accent   },
  disbursement_rejected:        { icon: "close-circle",      color: COLORS.error    },
  disbursement_executed:        { icon: "checkmark-circle",  color: COLORS.success  },
  disbursement_sent:            { icon: "send",              color: COLORS.success  },
  // Welfare
  welfare_claim:                { icon: "heart",             color: "#DC2626"       },
  welfare_rejected:             { icon: "close-circle",      color: COLORS.error    },
  welfare_disbursed:            { icon: "heart",             color: COLORS.success  },
  // Advances
  advance_requested:            { icon: "flash",             color: COLORS.accent   },
  advance_approved:             { icon: "flash",             color: COLORS.success  },
  advance_rejected:             { icon: "flash",             color: COLORS.error    },
  advance_sent:                 { icon: "send",              color: COLORS.success  },
  // Reminders
  reminder:                     { icon: "alarm",             color: COLORS.accent   },
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

type ActionState = "idle" | "loading" | "approved" | "rejected" | "accepted" | "declined";

export default function NotificationsScreen() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading,       setLoading]       = useState(true);
  const [refreshing,    setRefreshing]    = useState(false);
  const [actionStates,  setActionStates]  = useState<Record<number, ActionState>>({});
  const [menuVisible,   setMenuVisible]   = useState(false);

  const load = useCallback(async () => {
    try { setNotifications(await getNotifications()); } catch {}
  }, []);

  useFocusEffect(useCallback(() => {
    load().finally(() => setLoading(false));
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  // ── Generic action helper ────────────────────────────────────────────────

  async function runAction(
    notifId: number,
    fn: () => Promise<unknown>,
    successState: ActionState,
  ) {
    setActionStates(p => ({ ...p, [notifId]: "loading" }));
    try {
      await fn();
      await markRead(notifId);
      setNotifications(prev =>
        prev.map(n => n.id === notifId ? { ...n, is_read: true } : n)
      );
      setActionStates(p => ({ ...p, [notifId]: successState }));
    } catch (e: any) {
      const msg = e?.response?.data?.error ?? "";
      if (msg.toLowerCase().includes("already")) {
        // Another admin acted first — refresh to get latest state
        await load();
        setActionStates(p => ({ ...p, [notifId]: "idle" }));
      } else {
        Alert.alert("Error", msg || "Could not process. Please try again.");
        setActionStates(p => ({ ...p, [notifId]: "idle" }));
      }
    }
  }

  // ── Tap to navigate ──────────────────────────────────────────────────────

  const handleTap = async (n: Notification) => {
    if (!n.is_read) {
      markRead(n.id).catch(() => {});
      setNotifications(prev =>
        prev.map(x => x.id === n.id ? { ...x, is_read: true } : x)
      );
    }
    if (n.conversation_id)  router.push(`/conversation/${n.conversation_id}`);
    else if (n.contribution_id) router.push(`/contribution/${n.contribution_id}`);
    else if (n.community_id)    router.push(`/community/${n.community_id}`);
  };

  // ── Bulk actions ─────────────────────────────────────────────────────────

  const handleMarkAllRead = async () => {
    setMenuVisible(false);
    await markAllRead();
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
  };

  const handleDeleteAll = () => {
    Alert.alert("Clear all", "Remove all notifications?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Clear all", style: "destructive",
        onPress: async () => {
          setMenuVisible(false);
          setNotifications([]);
          deleteAllNotifications().catch(() => {});
        },
      },
    ]);
  };

  const unread = notifications.filter(n => !n.is_read).length;

  // ── Render item ──────────────────────────────────────────────────────────

  const renderItem = ({ item: n }: { item: Notification }) => {
    const meta    = TYPE_META[n.notification_type] ?? { icon: "notifications", color: COLORS.primary };
    const state   = actionStates[n.id] ?? "idle";
    const loading = state === "loading";
    const acted   = state !== "idle" && state !== "loading";
    const isPending = n.join_request_status === "PENDING";

    return (
      <TouchableOpacity
        style={[s.item, !n.is_read && s.itemUnread]}
        onPress={() => handleTap(n)}
        onLongPress={() =>
          Alert.alert("Remove", "Remove this notification?", [
            { text: "Cancel", style: "cancel" },
            {
              text: "Remove", style: "destructive",
              onPress: () => {
                setNotifications(prev => prev.filter(x => x.id !== n.id));
                deleteNotification(n.id).catch(() => {});
              },
            },
          ])
        }
        activeOpacity={0.75}
        delayLongPress={400}
      >
        <View style={[s.iconBox, { backgroundColor: meta.color + "18" }]}>
          <Ionicons name={meta.icon as any} size={20} color={meta.color} />
        </View>

        <View style={{ flex: 1 }}>
          <View style={s.titleRow}>
            <Text style={s.title} numberOfLines={1}>{n.title}</Text>
            {!n.is_read && <View style={s.dot} />}
          </View>
          <Text style={s.message} numberOfLines={2}>{n.message}</Text>
          <Text style={s.time}>{timeAgo(n.created_at)}</Text>

          {/* ── Community join request — admin side ── */}
          {n.notification_type === "join_request" && n.join_request_id && (
            acted ? (
              <OutcomeBadge state={state} />
            ) : isPending ? (
              loading ? <InlineSpinner /> : (
                <ActionRow
                  onApprove={() => runAction(n.id, () => actionCommunityJoinRequest(n.join_request_id!, "approve"), "approved")}
                  onDecline={() => runAction(n.id, () => actionCommunityJoinRequest(n.join_request_id!, "reject"),  "rejected")}
                />
              )
            ) : (
              <OutcomeBadge state={n.join_request_status === "APPROVED" ? "approved" : "rejected"} byOther />
            )
          )}

          {/* ── Contribution join request — admin side ── */}
          {n.notification_type === "contribution_join_request" && n.join_request_id && (
            acted ? (
              <OutcomeBadge state={state} />
            ) : isPending ? (
              loading ? <InlineSpinner /> : (
                <ActionRow
                  onApprove={() => runAction(n.id, () => actionContribJoinRequest(n.join_request_id!, "approve"), "approved")}
                  onDecline={() => runAction(n.id, () => actionContribJoinRequest(n.join_request_id!, "reject"),  "rejected")}
                />
              )
            ) : (
              <OutcomeBadge state={n.join_request_status === "APPROVED" ? "approved" : "rejected"} byOther />
            )
          )}

          {/* ── Contribution invite — invitee side ── */}
          {n.notification_type === "contribution_invite" && n.join_request_id && (
            acted ? (
              <OutcomeBadge state={state} acceptDecline />
            ) : isPending ? (
              loading ? <InlineSpinner /> : (
                <ActionRow
                  approveLabel="Accept"
                  declineLabel="Decline"
                  onApprove={() => runAction(n.id, () => respondToContributionInvite(n.join_request_id!, "accept"),  "accepted")}
                  onDecline={() => runAction(n.id, () => respondToContributionInvite(n.join_request_id!, "decline"), "declined")}
                />
              )
            ) : null
          )}

          {/* ── Disbursement request — admin vote ── */}
          {n.notification_type === "disbursement_requested" && n.join_request_id && (
            acted ? (
              <OutcomeBadge state={state} voteLabels />
            ) : loading ? <InlineSpinner /> : (
              <ActionRow
                approveLabel="Approve"
                declineLabel="Reject"
                onApprove={() => runAction(n.id, () => voteDisbursement(n.join_request_id!, "APPROVE"), "approved")}
                onDecline={() => runAction(n.id, () => voteDisbursement(n.join_request_id!, "REJECT"),  "rejected")}
              />
            )
          )}

          {/* ── Welfare claim — admin approve/reject ── */}
          {n.notification_type === "welfare_claim" && n.join_request_id && (
            acted ? (
              <OutcomeBadge state={state} voteLabels />
            ) : loading ? <InlineSpinner /> : (
              <ActionRow
                approveLabel="Approve"
                declineLabel="Reject"
                onApprove={() => runAction(n.id, () => voteWelfareClaim(n.join_request_id!, "approve"), "approved")}
                onDecline={() => runAction(n.id, () => voteWelfareClaim(n.join_request_id!, "reject"),  "rejected")}
              />
            )
          )}

          {/* ── Emergency advance — admin approve/reject ── */}
          {n.notification_type === "advance_requested" && n.join_request_id && (
            acted ? (
              <OutcomeBadge state={state} voteLabels />
            ) : loading ? <InlineSpinner /> : (
              <ActionRow
                approveLabel="Approve"
                declineLabel="Reject"
                onApprove={() => runAction(n.id, () => actionAdvance(n.join_request_id!, "approve"), "approved")}
                onDecline={() => runAction(n.id, () => actionAdvance(n.join_request_id!, "reject"),  "rejected")}
              />
            )
          )}

          {/* ── Simple status badges (no action required) ── */}
          {["join_approved", "contribution_join_approved"].includes(n.notification_type) && (
            <OutcomeBadge state="approved" />
          )}
          {["join_rejected", "contribution_join_rejected"].includes(n.notification_type) && (
            <OutcomeBadge state="rejected" />
          )}
        </View>
      </TouchableOpacity>
    );
  };

  // ── Screen ───────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={s.headerTitle}>Notifications</Text>
          {unread > 0 && (
            <View style={s.unreadBadge}>
              <Text style={s.unreadBadgeText}>{unread > 99 ? "99+" : unread}</Text>
            </View>
          )}
        </View>
        <TouchableOpacity onPress={() => setMenuVisible(true)} hitSlop={10}>
          <Ionicons name="ellipsis-vertical" size={22} color={COLORS.text} />
        </TouchableOpacity>
      </View>

      {/* 3-dot menu */}
      <Modal visible={menuVisible} transparent animationType="fade" onRequestClose={() => setMenuVisible(false)}>
        <Pressable style={s.backdrop} onPress={() => setMenuVisible(false)}>
          <View style={s.menuCard}>
            <TouchableOpacity style={s.menuRow} onPress={handleMarkAllRead} disabled={unread === 0}>
              <Ionicons name="checkmark-done-outline" size={18} color={unread === 0 ? COLORS.textMuted : COLORS.text} />
              <Text style={[s.menuText, unread === 0 && { color: COLORS.textMuted }]}>Mark all as read</Text>
            </TouchableOpacity>
            <View style={s.menuDivider} />
            <TouchableOpacity style={s.menuRow} onPress={handleDeleteAll} disabled={notifications.length === 0}>
              <Ionicons name="trash-outline" size={18} color={notifications.length === 0 ? COLORS.textMuted : COLORS.error} />
              <Text style={[s.menuText, { color: notifications.length === 0 ? COLORS.textMuted : COLORS.error }]}>
                Clear all
              </Text>
            </TouchableOpacity>
          </View>
        </Pressable>
      </Modal>

      {loading ? (
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : notifications.length === 0 ? (
        <View style={s.empty}>
          <Ionicons name="notifications-outline" size={52} color={COLORS.textMuted} />
          <Text style={s.emptyTitle}>All caught up</Text>
          <Text style={s.emptySub}>Activity from your communities and contributions appears here.</Text>
        </View>
      ) : (
        <FlatList
          data={notifications}
          keyExtractor={n => String(n.id)}
          renderItem={renderItem}
          ItemSeparatorComponent={() => <View style={s.divider} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
          contentContainerStyle={{ paddingBottom: 24 }}
        />
      )}
    </SafeAreaView>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────

function InlineSpinner() {
  return (
    <ActivityIndicator
      size="small"
      color={COLORS.primary}
      style={{ marginTop: 10, alignSelf: "flex-start" }}
    />
  );
}

function ActionRow({
  onApprove, onDecline,
  approveLabel = "Approve",
  declineLabel = "Decline",
}: {
  onApprove: () => void;
  onDecline: () => void;
  approveLabel?: string;
  declineLabel?: string;
}) {
  return (
    <View style={s.actionRow}>
      <TouchableOpacity style={s.approveBtn} onPress={onApprove}>
        <Text style={s.approveBtnText}>{approveLabel}</Text>
      </TouchableOpacity>
      <TouchableOpacity style={s.declineBtn} onPress={onDecline}>
        <Text style={s.declineBtnText}>{declineLabel}</Text>
      </TouchableOpacity>
    </View>
  );
}

function OutcomeBadge({
  state,
  byOther,
  acceptDecline,
  voteLabels,
}: {
  state: ActionState | string;
  byOther?: boolean;
  acceptDecline?: boolean;
  voteLabels?: boolean;
}) {
  const approved = state === "approved" || state === "accepted";
  const icon     = approved ? "checkmark-circle" : "close-circle";
  const color    = approved ? COLORS.success : COLORS.error;

  let label = "";
  if (acceptDecline) {
    label = state === "accepted" ? "Invitation accepted" : "Invitation declined";
  } else if (voteLabels) {
    label = approved
      ? (byOther ? "Approved by another admin" : "Vote cast — Approved")
      : (byOther ? "Rejected by another admin" : "Vote cast — Rejected");
  } else {
    label = approved
      ? (byOther ? "Approved by another admin" : "Approved")
      : (byOther ? "Declined by another admin" : "Declined");
  }

  return (
    <View style={s.outcomeBadge}>
      <Ionicons name={icon as any} size={14} color={color} />
      <Text style={[s.outcomeText, { color }]}>{label}</Text>
    </View>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  headerTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text },
  unreadBadge: {
    backgroundColor: COLORS.primary, borderRadius: 10,
    paddingHorizontal: 7, paddingVertical: 2, minWidth: 20, alignItems: "center",
  },
  unreadBadgeText: { color: "#fff", fontSize: 11, fontWeight: "700" },

  backdrop: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.2)",
    justifyContent: "flex-start", alignItems: "flex-end",
    paddingTop: 70, paddingRight: 16,
  },
  menuCard: {
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg,
    paddingVertical: 6, minWidth: 200,
    shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 }, elevation: 8,
  },
  menuRow: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 16, paddingVertical: 13, gap: 10,
  },
  menuText: { fontSize: FONTS.md, color: COLORS.text, fontWeight: "500" },
  menuDivider: { height: 1, backgroundColor: COLORS.divider, marginHorizontal: 12 },

  empty: {
    flex: 1, justifyContent: "center", alignItems: "center",
    paddingHorizontal: 40, gap: 12,
  },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  item: {
    flexDirection: "row", alignItems: "flex-start",
    paddingHorizontal: 16, paddingVertical: 14,
    backgroundColor: COLORS.white, gap: 12,
  },
  itemUnread: { backgroundColor: COLORS.primaryBg },
  iconBox:    { width: 40, height: 40, borderRadius: RADIUS.full, justifyContent: "center", alignItems: "center" },
  titleRow:   { flexDirection: "row", alignItems: "center", marginBottom: 3, gap: 6 },
  title:      { flex: 1, fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  dot:        { width: 7, height: 7, borderRadius: 4, backgroundColor: COLORS.primary },
  message:    { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 19, marginBottom: 4 },
  time:       { fontSize: 11, color: COLORS.textMuted },
  divider:    { height: 1, backgroundColor: COLORS.divider },

  actionRow: { flexDirection: "row", gap: 10, marginTop: 10 },
  approveBtn: {
    flex: 1, height: 34, backgroundColor: COLORS.primary,
    borderRadius: RADIUS.md, justifyContent: "center", alignItems: "center",
  },
  declineBtn: {
    flex: 1, height: 34,
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: RADIUS.md, justifyContent: "center", alignItems: "center",
    backgroundColor: COLORS.white,
  },
  approveBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },
  declineBtnText: { color: COLORS.text,  fontWeight: "600", fontSize: FONTS.sm },

  outcomeBadge: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 8 },
  outcomeText:  { fontSize: FONTS.sm, fontWeight: "600" },
});
