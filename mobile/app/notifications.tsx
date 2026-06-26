import { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import {
  getNotifications,
  markRead,
  markAllRead,
  Notification,
} from "../api/notifications";
import { Ionicons } from "@expo/vector-icons";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

const TYPE_META: Record<string, { emoji: string; color: string }> = {
  community_join:         { emoji: "👥", color: COLORS.primary },
  conversation_created:   { emoji: "💬", color: "#7C3AED" },
  new_message:            { emoji: "✉️", color: COLORS.primary },
  contribution_payment:   { emoji: "💸", color: "#10B981" },
  payment_recorded:       { emoji: "🧾", color: "#0891B2" },
  contribution_milestone: { emoji: "🎯", color: "#F59E0B" },
  contribution_joined:    { emoji: "🤝", color: COLORS.primary },
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

export default function NotificationsScreen() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setNotifications(await getNotifications());
    } catch {}
  }, []);

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

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

    if (n.conversation_id) {
      router.push({ pathname: "/conversation/[id]", params: { id: String(n.conversation_id) } });
    } else if (n.contribution_id) {
      router.push({ pathname: "/contribution/[id]", params: { id: String(n.contribution_id) } });
    } else if (n.community_id) {
      router.push({ pathname: "/community/[id]", params: { id: String(n.community_id) } });
    }
  };

  const handleMarkAll = async () => {
    await markAllRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  const renderItem = ({ item }: { item: Notification }) => {
    const meta = TYPE_META[item.notification_type] ?? { emoji: "🔔", color: COLORS.primary };
    return (
      <TouchableOpacity
        style={[styles.item, !item.is_read && styles.itemUnread]}
        onPress={() => handleTap(item)}
        activeOpacity={0.7}
      >
        <View style={[styles.iconBox, { backgroundColor: meta.color + "18" }]}>
          <Text style={styles.icon}>{meta.emoji}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <View style={styles.titleRow}>
            <Text style={styles.title} numberOfLines={1}>{item.title}</Text>
            {!item.is_read && <View style={styles.dot} />}
          </View>
          <Text style={styles.message} numberOfLines={2}>{item.message}</Text>
          <Text style={styles.time}>{timeAgo(item.created_at)}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader
        title={`Notifications${unreadCount > 0 ? ` (${unreadCount})` : ""}`}
        variant="light"
        leading="back"
        rightExtra={
          unreadCount > 0 ? (
            <TouchableOpacity style={styles.markAllBtn} onPress={handleMarkAll}>
              <Text style={styles.markAllText}>Mark all read</Text>
            </TouchableOpacity>
          ) : null
        }
      />

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : notifications.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="notifications-outline" size={40} color={COLORS.border} />
          <Text style={styles.emptyTitle}>All caught up!</Text>
          <Text style={styles.emptySub}>
            Notifications about contributions, messages and community activity will appear here.
          </Text>
        </View>
      ) : (
        <FlatList
          data={notifications}
          keyExtractor={(n) => String(n.id)}
          renderItem={renderItem}
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

  empty: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 32 },
  emptyTitle: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.textSecondary, marginTop: 10, marginBottom: 6 },
  emptySub: { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  item: {
    flexDirection: "row",
    paddingHorizontal: 16, paddingVertical: 14,
    backgroundColor: COLORS.white, gap: 12,
  },
  itemUnread: { backgroundColor: COLORS.primaryBg },

  iconBox: { width: 44, height: 44, borderRadius: RADIUS.full, justifyContent: "center", alignItems: "center" },
  icon: { fontSize: 22 },

  titleRow: { flexDirection: "row", alignItems: "center", marginBottom: 3, gap: 6 },
  title: { flex: 1, fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.primary },

  message: { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 20, marginBottom: 4 },
  time: { fontSize: 11, color: COLORS.textMuted },

  divider: { height: 1, backgroundColor: COLORS.divider },

  markAllBtn: {
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: RADIUS.full,
    backgroundColor: "rgba(255,255,255,0.2)",
    marginRight: 8,
  },
  markAllText: { fontSize: FONTS.sm, color: COLORS.white, fontWeight: "600" },
});
