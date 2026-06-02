import { useState, useCallback } from "react";
import {
  View, Text, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getMyJoinRequests, PendingRequest } from "../api/communities";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";
import Avatar from "../components/app/Avatar";

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins  = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days  = Math.floor(diff / 86_400_000);
  if (mins  < 60)  return `${mins}m ago`;
  if (hours < 24)  return `${hours}h ago`;
  return `${days}d ago`;
}

export default function JoinRequestsScreen() {
  const [requests, setRequests]   = useState<PendingRequest[]>([]);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getMyJoinRequests();
      setRequests(data);
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

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader title="Pending Requests" variant="light" leading="back" />

      {loading ? (
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : (
        <FlatList
          data={requests}
          keyExtractor={(r) => String(r.id)}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
          contentContainerStyle={requests.length === 0 ? s.emptyContainer : { paddingVertical: 8 }}
          ListHeaderComponent={
            requests.length > 0 ? (
              <View style={s.infoBar}>
                <Ionicons name="information-circle-outline" size={15} color={COLORS.textMuted} />
                <Text style={s.infoText}>
                  You'll be notified when an admin reviews your request.
                </Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => (
            <TouchableOpacity
              style={s.row}
              onPress={() => router.push({ pathname: `/community/${item.community_id}` })}
              activeOpacity={0.7}
            >
              <Avatar name={item.community_name} uri={item.community_photo} size={48} />
              <View style={s.rowText}>
                <Text style={s.name}>{item.community_name}</Text>
                <Text style={s.meta}>
                  {item.member_count} member{item.member_count !== 1 ? "s" : ""}
                </Text>
              </View>
              <View style={s.right}>
                <View style={s.badge}>
                  <Ionicons name="time-outline" size={11} color={COLORS.accent} />
                  <Text style={s.badgeText}>Pending</Text>
                </View>
                <Text style={s.time}>{timeAgo(item.created_at)}</Text>
              </View>
            </TouchableOpacity>
          )}
          ListEmptyComponent={
            <View style={s.empty}>
              <Ionicons name="checkmark-circle-outline" size={52} color={COLORS.textMuted} />
              <Text style={s.emptyTitle}>No pending requests</Text>
              <Text style={s.emptySub}>
                All your community join requests have been resolved.
              </Text>
              <TouchableOpacity
                style={s.discoverBtn}
                onPress={() => { router.back(); router.push("/(drawer)/discover"); }}
              >
                <Text style={s.discoverBtnText}>Browse communities</Text>
              </TouchableOpacity>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  infoBar: {
    flexDirection: "row", alignItems: "center", gap: 8,
    marginHorizontal: 16, marginTop: 12, marginBottom: 4,
  },
  infoText: { flex: 1, fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  row: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: COLORS.white,
    marginHorizontal: 16, marginVertical: 5,
    borderRadius: RADIUS.md, padding: 14,
    borderWidth: 1, borderColor: COLORS.border,
  },
  rowText: { flex: 1, marginLeft: 12 },
  name:    { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginBottom: 3 },
  meta:    { fontSize: FONTS.sm, color: COLORS.textMuted },

  right:   { alignItems: "flex-end", gap: 6 },
  badge: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: "#fef7e0", paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: RADIUS.full,
  },
  badgeText: { fontSize: 11, fontWeight: "700", color: COLORS.accent },
  time:      { fontSize: 11, color: COLORS.textMuted },

  emptyContainer: { flex: 1, justifyContent: "center" },
  empty:     { alignItems: "center", paddingHorizontal: 40, gap: 12 },
  emptyTitle:{ fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub:  { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },
  discoverBtn: {
    marginTop: 8, backgroundColor: COLORS.primary,
    paddingHorizontal: 24, paddingVertical: 12, borderRadius: RADIUS.md,
  },
  discoverBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
});
