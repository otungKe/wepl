import { useState, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
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
      <AppHeader title="Transactions" variant="light" leading="back" />

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : transactions.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyEmoji}>📈</Text>
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
  emptyEmoji: { fontSize: 56, marginBottom: 16 },
  emptyTitle: { fontSize: FONTS.xl, fontWeight: "bold", color: COLORS.text, marginBottom: 8 },
  emptySub:   { fontSize: FONTS.md, color: COLORS.textSecondary, textAlign: "center" },

  row: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 14, paddingHorizontal: 16,
    backgroundColor: COLORS.white, gap: 12,
  },
  iconBox: { width: 40, height: 40, borderRadius: RADIUS.full, justifyContent: "center", alignItems: "center" },
  iconOut: { backgroundColor: COLORS.primary + "15" },
  iconIn:  { backgroundColor: COLORS.success + "15" },
  icon:    { fontSize: 18, fontWeight: "bold", color: COLORS.primary },

  title: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  date:  { fontSize: FONTS.sm, color: COLORS.textMuted },

  amount: { fontSize: FONTS.md, fontWeight: "bold" },
  amountOut: { color: COLORS.text },
  amountIn: { color: COLORS.success },

  divider: { height: 1, backgroundColor: COLORS.divider, marginLeft: 68 },
});
