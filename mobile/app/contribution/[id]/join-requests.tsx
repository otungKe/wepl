import { useState, useCallback } from "react";
import {
  View, Text, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  getPendingJoinRequests, actionJoinRequest,
  ContributionJoinRequest,
} from "../../../api/contributions";
import { COLORS, FONTS, RADIUS } from "../../../constants/theme";
import AppHeader from "../../../components/app/AppHeader";
import Avatar from "../../../components/app/Avatar";

export default function ContributionJoinRequestsScreen() {
  const { id, title } = useLocalSearchParams<{ id: string; title?: string }>();
  const contributionId = Number(id);

  const [requests, setRequests]     = useState<ContributionJoinRequest[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actioning, setActioning]   = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getPendingJoinRequests(contributionId);
      setRequests(data);
    } catch {}
  }, [contributionId]);

  useFocusEffect(useCallback(() => {
    load().finally(() => setLoading(false));
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleAction = async (requestId: number, action: 'approve' | 'reject') => {
    setActioning(requestId);
    try {
      await actionJoinRequest(requestId, action);
      const remaining = requests.filter((r) => r.id !== requestId);
      setRequests(remaining);
      if (remaining.length === 0) router.back();
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Action failed.");
    } finally {
      setActioning(null);
    }
  };

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader
        title="Join Requests"
        variant="light"
        leading="back"
      />

      {loading ? (
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : (
        <FlatList
          data={requests}
          keyExtractor={(r) => String(r.id)}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
          contentContainerStyle={requests.length === 0 ? s.emptyContainer : { padding: 16, gap: 10 }}
          ListHeaderComponent={
            requests.length > 0 ? (
              <Text style={s.subheader}>
                {requests.length} pending request{requests.length !== 1 ? 's' : ''} for{' '}
                <Text style={{ fontWeight: '700', color: COLORS.text }}>{title}</Text>
              </Text>
            ) : null
          }
          renderItem={({ item }) => {
            const name        = item.name || item.phone_number;
            const isActioning = actioning === item.id;
            return (
              <View style={s.card}>
                <View style={s.cardTop}>
                  <Avatar name={name} size={44} />
                  <View style={{ flex: 1, marginLeft: 12 }}>
                    <Text style={s.name}>{name}</Text>
                    {item.name ? <Text style={s.phone}>{item.phone_number}</Text> : null}
                    <Text style={s.time}>
                      Requested {new Date(item.created_at).toLocaleDateString('en-GB', {
                        day: '2-digit', month: 'short', year: 'numeric',
                      })}
                    </Text>
                  </View>
                </View>

                {isActioning ? (
                  <ActivityIndicator color={COLORS.primary} style={{ marginTop: 12 }} />
                ) : (
                  <View style={s.actions}>
                    <TouchableOpacity
                      style={[s.btn, s.approveBtn]}
                      onPress={() => handleAction(item.id, 'approve')}
                    >
                      <Ionicons name="checkmark-outline" size={16} color={COLORS.white} />
                      <Text style={s.btnText}>Approve</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[s.btn, s.declineBtn]}
                      onPress={() => handleAction(item.id, 'reject')}
                    >
                      <Ionicons name="close-outline" size={16} color={COLORS.error} />
                      <Text style={[s.btnText, { color: COLORS.error }]}>Decline</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            );
          }}
          ListEmptyComponent={
            <View style={s.empty}>
              <Ionicons name="people-outline" size={52} color={COLORS.textMuted} />
              <Text style={s.emptyTitle}>No pending requests</Text>
              <Text style={s.emptySub}>All join requests have been reviewed.</Text>
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

  subheader: { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 8 },

  card: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  cardTop: { flexDirection: "row", alignItems: "center" },
  name:    { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginBottom: 2 },
  phone:   { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 2 },
  time:    { fontSize: 12, color: COLORS.textMuted },

  actions:    { flexDirection: "row", gap: 10, marginTop: 14 },
  btn:        { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 11, borderRadius: RADIUS.md },
  approveBtn: { backgroundColor: COLORS.primary },
  declineBtn: { borderWidth: 1.5, borderColor: COLORS.error },
  btnText:    { fontWeight: "700", fontSize: FONTS.sm, color: COLORS.white },

  emptyContainer: { flex: 1, justifyContent: "center" },
  empty:      { alignItems: "center", gap: 12, paddingHorizontal: 40 },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },
});
