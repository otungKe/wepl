import { useState, useCallback, useRef } from "react";
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
import { actionJoinRequest } from "../../api/communities";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";

const TYPE_ICON: Record<string, { icon: string; color: string }> = {
  community_join:                { icon: "people",           color: COLORS.primary },
  conversation_created:          { icon: "chatbubbles",      color: "#6D28D9" },
  new_message:                   { icon: "chatbubble",       color: COLORS.primary },
  contribution_payment:          { icon: "arrow-up-circle",  color: COLORS.success },
  payment_recorded:              { icon: "receipt",          color: "#0891B2" },
  contribution_milestone:        { icon: "trophy",           color: COLORS.accent },
  contribution_joined:           { icon: "person-add",       color: COLORS.primary },
  rosca_payout:                  { icon: "cash",             color: COLORS.success },
  advance_approved:              { icon: "flash",            color: COLORS.accent },
  welfare_disbursed:             { icon: "heart",            color: "#DC2626" },
  join_request:                  { icon: "person-add",       color: COLORS.primary },
  join_approved:                 { icon: "checkmark-circle", color: COLORS.success },
  join_rejected:                 { icon: "close-circle",     color: COLORS.error },
  contribution_join_request:     { icon: "person-add",       color: COLORS.primary },
  contribution_invite:           { icon: "mail",             color: "#6D28D9" },
  contribution_join_approved:    { icon: "checkmark-circle", color: COLORS.success },
  contribution_join_rejected:    { icon: "close-circle",     color: COLORS.error },
  contribution_invite_accepted:  { icon: "people",           color: COLORS.success },
  amendment_proposed:            { icon: "git-pull-request", color: COLORS.accent },
  amendment_approved:            { icon: "checkmark-done",   color: COLORS.success },
  amendment_rejected:            { icon: "close-circle",     color: COLORS.error },
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// Tracks join-request action result keyed by notification id
type JoinOutcome = "approved" | "rejected";

export default function NotificationsScreen() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actioning, setActioning] = useState<Record<number, boolean>>({});
  const [joinOutcomes, setJoinOutcomes] = useState<Record<number, JoinOutcome>>({});
  const [menuVisible, setMenuVisible] = useState(false);

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

  const handleTap = async (n: Notification) => {
    if (!n.is_read) {
      await markRead(n.id);
      setNotifications((prev) => prev.map((x) => x.id === n.id ? { ...x, is_read: true } : x));
    }
    if (n.conversation_id) router.push({ pathname: `/conversation/${n.conversation_id}` });
    else if (n.contribution_id) router.push({ pathname: `/contribution/${n.contribution_id}` });
    else if (n.community_id) router.push({ pathname: `/community/${n.community_id}` });
  };

  const handleJoinAction = async (n: Notification, action: "approve" | "reject") => {
    if (!n.join_request_id) return;
    setActioning((prev) => ({ ...prev, [n.id]: true }));
    try {
      await actionJoinRequest(n.join_request_id, action);
      await markRead(n.id);
      setNotifications((prev) => prev.map((x) =>
        x.id === n.id ? { ...x, is_read: true, join_request_status: action === "approve" ? "APPROVED" : "REJECTED" } : x
      ));
      setJoinOutcomes((prev) => ({ ...prev, [n.id]: action === "approve" ? "approved" : "rejected" }));
    } catch (e: any) {
      const msg: string = e?.response?.data?.error ?? "";
      if (msg.toLowerCase().includes("already been reviewed")) {
        // Another admin acted first — refresh so this admin sees the current status
        await load();
      } else {
        Alert.alert("Error", msg || "Could not process request.");
      }
    } finally {
      setActioning((prev) => ({ ...prev, [n.id]: false }));
    }
  };

  const handleDeleteOne = async (id: number) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
    try { await deleteNotification(id); } catch {}
  };

  const handleDeleteAll = () => {
    Alert.alert("Delete All", "Remove all notifications?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete All",
        style: "destructive",
        onPress: async () => {
          setMenuVisible(false);
          setNotifications([]);
          try { await deleteAllNotifications(); } catch {}
        },
      },
    ]);
  };

  const handleMarkAllRead = async () => {
    setMenuVisible(false);
    await markAllRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Notifications</Text>
        <TouchableOpacity onPress={() => setMenuVisible(true)} hitSlop={10}>
          <Ionicons name="ellipsis-vertical" size={22} color={COLORS.text} />
        </TouchableOpacity>
      </View>

      {/* 3-dots menu */}
      <Modal visible={menuVisible} transparent animationType="fade" onRequestClose={() => setMenuVisible(false)}>
        <Pressable style={styles.menuBackdrop} onPress={() => setMenuVisible(false)}>
          <View style={styles.menuCard}>
            <TouchableOpacity style={styles.menuItem} onPress={handleMarkAllRead} disabled={unreadCount === 0}>
              <Ionicons name="checkmark-done-outline" size={18} color={unreadCount === 0 ? COLORS.textMuted : COLORS.text} />
              <Text style={[styles.menuItemText, unreadCount === 0 && { color: COLORS.textMuted }]}>
                Mark all as read
              </Text>
            </TouchableOpacity>
            <View style={styles.menuDivider} />
            <TouchableOpacity style={styles.menuItem} onPress={handleDeleteAll} disabled={notifications.length === 0}>
              <Ionicons name="trash-outline" size={18} color={notifications.length === 0 ? COLORS.textMuted : COLORS.error} />
              <Text style={[styles.menuItemText, { color: notifications.length === 0 ? COLORS.textMuted : COLORS.error }]}>
                Delete all
              </Text>
            </TouchableOpacity>
          </View>
        </Pressable>
      </Modal>

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : notifications.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="notifications-outline" size={48} color={COLORS.textMuted} />
          <Text style={styles.emptyTitle}>All caught up</Text>
          <Text style={styles.emptySub}>Activity from your communities and contributions will appear here.</Text>
        </View>
      ) : (
        <FlatList
          data={notifications}
          keyExtractor={(n) => String(n.id)}
          renderItem={({ item }) => {
            const meta = TYPE_ICON[item.notification_type] ?? { icon: "notifications", color: COLORS.primary };
            // Only show action buttons if the request is still genuinely PENDING (live status from server)
            const isJoinRequest = item.notification_type === "join_request"
              && !!item.join_request_id
              && item.join_request_status === 'PENDING';
            // A resolved join_request notification (another admin already acted)
            const isJoinResolved = item.notification_type === "join_request"
              && !!item.join_request_id
              && item.join_request_status !== 'PENDING'
              && item.join_request_status !== null;
            const isActioning = !!actioning[item.id];
            const outcome = joinOutcomes[item.id];

            return (
              <TouchableOpacity
                style={[styles.item, !item.is_read && styles.itemUnread]}
                onPress={() => handleTap(item)}
                onLongPress={() =>
                  Alert.alert("Delete notification", "Remove this notification?", [
                    { text: "Cancel", style: "cancel" },
                    { text: "Delete", style: "destructive", onPress: () => handleDeleteOne(item.id) },
                  ])
                }
                activeOpacity={0.7}
                delayLongPress={400}
              >
                <View style={[styles.iconBox, { backgroundColor: meta.color + "18" }]}>
                  <Ionicons name={meta.icon as any} size={20} color={meta.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={styles.titleRow}>
                    <Text style={styles.itemTitle} numberOfLines={1}>{item.title}</Text>
                    {!item.is_read && <View style={styles.dot} />}
                  </View>
                  <Text style={styles.message} numberOfLines={2}>{item.message}</Text>
                  <Text style={styles.time}>{timeAgo(item.created_at)}</Text>

                  {/* Join request actions / outcome */}
                  {isJoinRequest && (
                    outcome ? (
                      <View style={styles.outcomeBadge}>
                        <Ionicons
                          name={outcome === "approved" ? "checkmark-circle" : "close-circle"}
                          size={14}
                          color={outcome === "approved" ? COLORS.success : COLORS.error}
                        />
                        <Text style={[
                          styles.outcomeText,
                          { color: outcome === "approved" ? COLORS.success : COLORS.error },
                        ]}>
                          {outcome === "approved" ? "Member approved and added" : "Request declined"}
                        </Text>
                      </View>
                    ) : isActioning ? (
                      <ActivityIndicator size="small" color={COLORS.primary} style={{ marginTop: 10, alignSelf: "flex-start" }} />
                    ) : (
                      <View style={styles.actionRow}>
                        <TouchableOpacity
                          style={styles.approveBtn}
                          onPress={() => handleJoinAction(item, "approve")}
                        >
                          <Text style={styles.approveBtnText}>Approve</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={styles.declineBtn}
                          onPress={() => handleJoinAction(item, "reject")}
                        >
                          <Text style={styles.declineBtnText}>Decline</Text>
                        </TouchableOpacity>
                      </View>
                    )
                  )}

                  {/* Already reviewed by another admin */}
                  {isJoinResolved && !outcome && (
                    <View style={styles.outcomeBadge}>
                      <Ionicons
                        name={item.join_request_status === "APPROVED" ? "checkmark-circle" : "close-circle"}
                        size={14}
                        color={item.join_request_status === "APPROVED" ? COLORS.success : COLORS.error}
                      />
                      <Text style={[
                        styles.outcomeText,
                        { color: item.join_request_status === "APPROVED" ? COLORS.success : COLORS.error },
                      ]}>
                        {item.join_request_status === "APPROVED" ? "Approved by another admin" : "Declined by another admin"}
                      </Text>
                    </View>
                  )}

                  {/* Status badges for the requester */}
                  {item.notification_type === "join_approved" && (
                    <View style={styles.outcomeBadge}>
                      <Ionicons name="checkmark-circle" size={14} color={COLORS.success} />
                      <Text style={[styles.outcomeText, { color: COLORS.success }]}>Approved</Text>
                    </View>
                  )}
                  {item.notification_type === "join_rejected" && (
                    <View style={styles.outcomeBadge}>
                      <Ionicons name="close-circle" size={14} color={COLORS.error} />
                      <Text style={[styles.outcomeText, { color: COLORS.error }]}>Declined</Text>
                    </View>
                  )}
                </View>
              </TouchableOpacity>
            );
          }}
          ItemSeparatorComponent={() => <View style={styles.divider} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },
  headerTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text },

  // 3-dots menu
  menuBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.2)",
    justifyContent: "flex-start",
    alignItems: "flex-end",
    paddingTop: 70,
    paddingRight: 16,
  },
  menuCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    paddingVertical: 6,
    minWidth: 200,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  menuItem: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 16, paddingVertical: 13, gap: 10,
  },
  menuItemText: { fontSize: FONTS.md, color: COLORS.text, fontWeight: "500" },
  menuDivider: { height: 1, backgroundColor: COLORS.divider, marginHorizontal: 12 },

  empty: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 40, gap: 12 },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub: { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  item: {
    flexDirection: "row", alignItems: "flex-start",
    paddingHorizontal: 16, paddingVertical: 14,
    backgroundColor: COLORS.white, gap: 12,
  },
  itemUnread: { backgroundColor: COLORS.primaryBg },
  iconBox: { width: 40, height: 40, borderRadius: RADIUS.full, justifyContent: "center", alignItems: "center" },
  titleRow: { flexDirection: "row", alignItems: "center", marginBottom: 3, gap: 6 },
  itemTitle: { flex: 1, fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: COLORS.primary },
  message: { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 19, marginBottom: 4 },
  time: { fontSize: 11, color: COLORS.textMuted },
  divider: { height: 1, backgroundColor: COLORS.divider },

  // Join request buttons
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
  declineBtnText: { color: COLORS.text, fontWeight: "600", fontSize: FONTS.sm },

  // Outcome / status
  outcomeBadge: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 8 },
  outcomeText: { fontSize: FONTS.sm, fontWeight: "600" },
});
