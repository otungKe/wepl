import { useState, useCallback, useRef } from "react";
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getMyContributions, getOpenContributions, Contribution } from "../../api/contributions";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import FAB from "../../components/app/FAB";

type Tab = "mine" | "open";

const FREQ_LABEL: Record<string, string> = {
  daily: "Daily", weekly: "Weekly", monthly: "Monthly", anytime: "Anytime",
};
const TENURE_LABEL: Record<string, string> = {
  open: "Open-ended", date: "Fixed date", period: "Fixed period",
};

function ContributionCard({ item }: { item: Contribution }) {
  const cur = Number(item.current_amount);
  const tgt = item.target_amount ? Number(item.target_amount) : 0;
  const pct = tgt > 0 ? Math.min((cur / tgt) * 100, 100) : 0;

  return (
    <TouchableOpacity
      style={styles.card}
      onPress={() => router.push({ pathname: `/contribution/${item.id}` })}
      activeOpacity={0.75}
    >
      {/* Badges row */}
      <View style={styles.badgeRow}>
        <View style={styles.badge}>
          <Ionicons name="time-outline" size={11} color={COLORS.primary} />
          <Text style={styles.badgeText}>{FREQ_LABEL[item.frequency] ?? item.frequency}</Text>
        </View>
        <View style={styles.badge}>
          <Ionicons name="cash-outline" size={11} color={COLORS.primary} />
          <Text style={styles.badgeText}>
            {item.amount_type === 'fixed' && item.fixed_amount
              ? `KES ${Number(item.fixed_amount).toLocaleString()} fixed`
              : 'Open amount'}
          </Text>
        </View>
        {item.has_welfare_fund && (
          <View style={[styles.badge, styles.badgeWelfare]}>
            <Ionicons name="heart-outline" size={11} color="#c0392b" />
            <Text style={[styles.badgeText, { color: "#c0392b" }]}>Welfare</Text>
          </View>
        )}
        {item.has_shares_fund && (
          <View style={[styles.badge, styles.badgeShares]}>
            <Ionicons name="stats-chart-outline" size={11} color={COLORS.accent} />
            <Text style={[styles.badgeText, { color: COLORS.accent }]}>Shares</Text>
          </View>
        )}
      </View>

      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.amount}>KES {cur.toLocaleString()}</Text>

      {tgt > 0 && (
        <>
          <View style={styles.progressBg}>
            <View style={[styles.progressFill, { width: `${pct}%` }]} />
          </View>
          <Text style={styles.progressLabel}>{pct.toFixed(0)}% of KES {tgt.toLocaleString()}</Text>
        </>
      )}

      <View style={styles.cardFooter}>
        <Ionicons name="people-outline" size={13} color={COLORS.textMuted} />
        <Text style={styles.meta}>
          {item.participant_count} {item.participant_count === 1 ? "member" : "members"}
        </Text>
        <View style={styles.dot} />
        <Ionicons name="shield-checkmark-outline" size={13} color={COLORS.textMuted} />
        <Text style={styles.meta}>{item.voting_label}</Text>
      </View>
    </TouchableOpacity>
  );
}

export default function ContributionsScreen() {
  const [tab, setTab]           = useState<Tab>("mine");
  const [mine, setMine]         = useState<Contribution[]>([]);
  const [open, setOpen]         = useState<Contribution[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const firstLoad = useRef(true);

  const load = useCallback(async () => {
    try {
      const [m, o] = await Promise.all([getMyContributions(), getOpenContributions()]);
      setMine(m);
      setOpen(o);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => {
    if (firstLoad.current) {
      firstLoad.current = false;
      load().finally(() => setLoading(false));
    } else {
      setRefreshing(true);
      load().finally(() => setRefreshing(false));
    }
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const data = tab === "mine" ? mine : open;

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Contributions</Text>
      </View>

      <View style={styles.tabRow}>
        {(["mine", "open"] as Tab[]).map((t) => (
          <TouchableOpacity
            key={t}
            style={[styles.tabBtn, tab === t && styles.tabBtnActive]}
            onPress={() => setTab(t)}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === "mine" ? "My Groups" : "Discover"}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : data.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="wallet-outline" size={52} color={COLORS.textMuted} />
          <Text style={styles.emptyTitle}>
            {tab === "mine" ? "No contribution groups yet" : "No open groups"}
          </Text>
          <Text style={styles.emptySub}>
            {tab === "mine"
              ? "Create a savings group, welfare fund, or shares pool for your community."
              : "Open groups you can join will appear here."}
          </Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(i) => String(i.id)}
          renderItem={({ item }) => <ContributionCard item={item} />}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        />
      )}

      <FAB icon="plus" onPress={() => router.push("/contribution/create")} tabBarOffset={56} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  header: {
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12,
    backgroundColor: COLORS.white, borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  headerTitle: { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text },

  tabRow: {
    flexDirection: "row", backgroundColor: COLORS.divider,
    margin: 16, marginBottom: 8, padding: 3, borderRadius: RADIUS.sm,
  },
  tabBtn:       { flex: 1, paddingVertical: 9, alignItems: "center", borderRadius: RADIUS.sm - 1 },
  tabBtnActive: { backgroundColor: COLORS.white },
  tabText:       { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },
  tabTextActive: { color: COLORS.text },

  empty:      { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 40, gap: 10 },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  emptySub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  list: { padding: 16, gap: 10 },

  card: {
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg, padding: 16,
    shadowColor: "#000", shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 4, elevation: 2,
  },
  badgeRow:    { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 10 },
  badge:       { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, backgroundColor: COLORS.primaryPale, borderRadius: RADIUS.full },
  badgeWelfare: { backgroundColor: "#fdecea" },
  badgeShares:  { backgroundColor: "#fef3e2" },
  badgeText:   { fontSize: 11, fontWeight: "700", color: COLORS.primary },

  title:  { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginBottom: 4 },
  amount: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginBottom: 10 },

  progressBg:    { height: 5, backgroundColor: COLORS.divider, borderRadius: RADIUS.full, overflow: "hidden", marginBottom: 4 },
  progressFill:  { height: "100%", backgroundColor: COLORS.primary },
  progressLabel: { fontSize: 11, color: COLORS.textMuted, marginBottom: 8 },

  cardFooter: { flexDirection: "row", alignItems: "center", gap: 5, flexWrap: "wrap" },
  dot:  { width: 3, height: 3, borderRadius: 2, backgroundColor: COLORS.textMuted },
  meta: { fontSize: 12, color: COLORS.textMuted },
});
