import { useState, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, router } from "expo-router";
import { getMyTransactions, Transaction } from "../../api/contributions";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";

export default function TransactionsScreen() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const t = await getMyTransactions();
      setTransactions(t);
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

  const renderItem = ({ item }: { item: Transaction }) => {
    const isOut = item.transaction_type === "CONTRIBUTION";
    return (
      <View style={styles.row}>
        <View style={[styles.iconBox, isOut ? styles.iconOut : styles.iconIn]}>
          <Text style={styles.icon}>{isOut ? "↑" : "↓"}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>{item.contribution_title}</Text>
          <Text style={styles.date}>{new Date(item.created_at).toLocaleString()}</Text>
        </View>
        <Text style={[styles.amount, isOut ? styles.amountOut : styles.amountIn]}>
          {isOut ? "-" : "+"} KES {Number(item.amount).toLocaleString()}
        </Text>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader title="Transactions" variant="light" leading="back" onBack={() => router.replace("/(drawer)/profile")} />

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : transactions.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="swap-vertical-outline" size={40} color={COLORS.border} />
          <Text style={styles.emptyTitle}>No transactions yet</Text>
          <Text style={styles.emptySub}>Your contributions and payments will appear here.</Text>
        </View>
      ) : (
        <FlatList
          data={transactions}
          keyExtractor={(t) => String(t.id)}
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
  emptySub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  row: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 14, paddingHorizontal: 16,
    backgroundColor: COLORS.white, gap: 12,
  },
  iconBox: { width: 40, height: 40, borderRadius: RADIUS.full, justifyContent: "center", alignItems: "center" },
  iconOut: { backgroundColor: COLORS.primary + "15" },
  iconIn:  { backgroundColor: COLORS.success + "15" },
  icon:    { fontSize: 18, fontWeight: "700", color: COLORS.primary },

  title: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  date:  { fontSize: FONTS.sm, color: COLORS.textMuted },

  amount: { fontSize: FONTS.md, fontWeight: "600" },
  amountOut: { color: COLORS.text },
  amountIn: { color: COLORS.success },

  divider: { height: 1, backgroundColor: COLORS.divider, marginLeft: 68 },
});
