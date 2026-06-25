import { useEffect, useState, useCallback, useRef } from "react";
import {
  View, Text, StyleSheet, ActivityIndicator,
  ScrollView, RefreshControl, TouchableOpacity,
  FlatList, Animated,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getMyTransactions, Transaction, getMyContributions, Contribution } from "../../api/contributions";
import { getFinancialSummary } from "../../api/activity";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";

type Tab = "overview" | "transactions" | "contributions";
type TxFilter = "all" | "CONTRIBUTION" | "WITHDRAWAL" | "ADVANCE" | "REPAYMENT";

const TX_TYPE_LABEL: Record<string, string>  = {
  CONTRIBUTION: "Contribution", WITHDRAWAL: "Withdrawal", ADVANCE: "Advance", REPAYMENT: "Repayment",
};
const TX_TYPE_COLOR: Record<string, string>  = {
  CONTRIBUTION: COLORS.primary, WITHDRAWAL: COLORS.success, ADVANCE: COLORS.warning, REPAYMENT: "#0891B2",
};
const TX_TYPE_ICON: Record<string, string>   = {
  CONTRIBUTION: "arrow-up-circle", WITHDRAWAL: "arrow-down-circle", ADVANCE: "flash", REPAYMENT: "checkmark-circle",
};
const TX_DIRECTION: Record<string, 1 | -1>  = { CONTRIBUTION: -1, WITHDRAWAL: 1, ADVANCE: 1, REPAYMENT: -1 };

function fmtKES(n: number) {
  if (n >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `KES ${(n / 1_000).toFixed(1)}K`;
  return `KES ${Math.round(n).toLocaleString()}`;
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-KE", { day: "numeric", month: "short", year: "numeric" });
}

export default function ReportsScreen() {
  const [tab,           setTab]           = useState<Tab>("overview");
  const [summary,       setSummary]       = useState<any>(null);
  const [contributions, setContributions] = useState<Contribution[]>([]);
  const [transactions,  setTransactions]  = useState<Transaction[]>([]);
  const [txFilter,      setTxFilter]      = useState<TxFilter>("all");
  const [loading,       setLoading]       = useState(true);
  const [refreshing,    setRefreshing]    = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, c, t] = await Promise.all([
        getFinancialSummary().catch(() => null),
        getMyContributions(),
        getMyTransactions(),
      ]);
      setSummary(s);
      setContributions(c);
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

  const filteredTx = txFilter === "all" ? transactions
    : transactions.filter((t) => t.transaction_type === txFilter);

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title="Reports & Statements" variant="light" leading="back" onBack={() => router.navigate("/(drawer)/profile")} />
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader title="Reports & Statements" variant="light" leading="back" onBack={() => router.replace("/(drawer)/profile")} />

      {/* Tab bar */}
      <View style={styles.tabBar}>
        {(["overview", "transactions", "contributions"] as Tab[]).map((t) => (
          <TouchableOpacity
            key={t}
            style={[styles.tabItem, tab === t && styles.tabItemActive]}
            onPress={() => setTab(t)}
          >
            <Text style={[styles.tabLabel, tab === t && styles.tabLabelActive]}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        key={tab}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
        contentContainerStyle={{ padding: 14, gap: 12, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
      >

        {/* ── OVERVIEW TAB ────────────────────────────────────────────── */}
        {tab === "overview" && summary && (
          <>
            {/* Top KPI row */}
            <View style={styles.kpiRow}>
              <KPICard
                label="Total Saved"
                value={fmtKES(summary.total_contributed)}
                sub={summary.this_month > 0 ? `↑ ${fmtKES(summary.this_month)} this month` : "No contributions yet"}
                icon="arrow-up-circle"
                color={COLORS.primary}
              />
              <KPICard
                label="Total Received"
                value={fmtKES(summary.total_received)}
                sub={`${summary.active_contributions} active pools`}
                icon="arrow-down-circle"
                color={COLORS.success}
              />
            </View>

            {/* Secondary KPI row */}
            <View style={styles.kpiRow}>
              <KPICard
                label="Transactions"
                value={String(summary.tx_count)}
                sub={`${summary.total_contributions} pools total`}
                icon="receipt"
                color="#0891B2"
              />
              <KPICard
                label="This Month"
                value={fmtKES(summary.this_month)}
                sub={summary.last_month > 0 ? `${fmtKES(summary.last_month)} last month` : "—"}
                icon="calendar"
                color={COLORS.accent}
              />
            </View>

            {/* Monthly trend chart */}
            {summary.monthly_trend && summary.monthly_trend.length > 0 && (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Monthly Contributions</Text>
                <MonthlyBarChart data={summary.monthly_trend} />
              </View>
            )}

            {/* Advance balance */}
            {summary.pending_advances > 0 && (
              <View style={[styles.card, styles.warningCard]}>
                <View style={styles.warningRow}>
                  <Ionicons name="flash" size={20} color={COLORS.warning} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.warningTitle}>Outstanding Advance</Text>
                    <Text style={styles.warningValue}>{fmtKES(summary.advance_balance_due)} due</Text>
                  </View>
                  <Text style={styles.warningCount}>{summary.pending_advances} active</Text>
                </View>
              </View>
            )}

            {/* Member since */}
            <View style={styles.memberCard}>
              <Ionicons name="person-circle" size={28} color={COLORS.primary} />
              <View>
                <Text style={styles.memberLabel}>WEPL member since</Text>
                <Text style={styles.memberDate}>
                  {new Date(summary.member_since).toLocaleDateString("en-KE", { month: "long", day: "numeric", year: "numeric" })}
                </Text>
              </View>
            </View>
          </>
        )}

        {tab === "overview" && !summary && (
          <Text style={styles.emptyText}>Could not load summary.</Text>
        )}

        {/* ── TRANSACTIONS TAB ────────────────────────────────────────── */}
        {tab === "transactions" && (
          <>
            {/* Filter chips */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 4 }}>
              <View style={styles.filterRow}>
                {(["all", "CONTRIBUTION", "WITHDRAWAL", "ADVANCE", "REPAYMENT"] as TxFilter[]).map((f) => (
                  <TouchableOpacity
                    key={f}
                    style={[styles.filterChip, txFilter === f && styles.filterChipActive]}
                    onPress={() => setTxFilter(f)}
                  >
                    <Text style={[styles.filterChipText, txFilter === f && styles.filterChipTextActive]}>
                      {f === "all" ? "All" : TX_TYPE_LABEL[f]}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>

            {/* Transaction totals for filter */}
            {txFilter !== "all" && (
              <View style={styles.filterSummary}>
                <Text style={styles.filterSummaryLabel}>{TX_TYPE_LABEL[txFilter]} total</Text>
                <Text style={styles.filterSummaryValue}>
                  {fmtKES(filteredTx.reduce((s, t) => s + Number(t.amount), 0))}
                </Text>
              </View>
            )}

            {filteredTx.length === 0 ? (
              <View style={styles.empty}>
                <Ionicons name="receipt-outline" size={40} color={COLORS.textMuted} />
                <Text style={styles.emptyTitle}>No transactions</Text>
              </View>
            ) : (
              filteredTx.map((tx) => {
                const dir   = TX_DIRECTION[tx.transaction_type] ?? -1;
                const color = TX_TYPE_COLOR[tx.transaction_type] ?? COLORS.primary;
                const icon  = TX_TYPE_ICON[tx.transaction_type]  ?? "swap-horizontal";
                return (
                  <View key={tx.id} style={styles.txRow}>
                    <View style={[styles.txIcon, { backgroundColor: color + "18" }]}>
                      <Ionicons name={icon as any} size={18} color={color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.txTitle} numberOfLines={1}>{tx.contribution_title}</Text>
                      <Text style={styles.txDate}>{fmtDate(tx.created_at)}</Text>
                      {tx.mpesa_receipt && (
                        <Text style={styles.txRef}>{tx.mpesa_receipt}</Text>
                      )}
                    </View>
                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={[styles.txAmount, { color: dir === 1 ? COLORS.success : COLORS.text }]}>
                        {dir === 1 ? "+" : "−"} KES {Number(tx.amount).toLocaleString()}
                      </Text>
                      <Text style={styles.txType}>{TX_TYPE_LABEL[tx.transaction_type]}</Text>
                    </View>
                  </View>
                );
              })
            )}
          </>
        )}

        {/* ── CONTRIBUTIONS TAB ───────────────────────────────────────── */}
        {tab === "contributions" && (
          <>
            <View style={styles.kpiRow}>
              <KPICard
                label="Active Pools"
                value={String(contributions.filter((c) => c.is_active).length)}
                sub={`${contributions.length} total`}
                icon="wallet"
                color={COLORS.primary}
              />
              <KPICard
                label="Total Pool Size"
                value={fmtKES(contributions.reduce((s, c) => s + Number(c.current_amount), 0))}
                sub="Combined balance"
                icon="cash"
                color={COLORS.success}
              />
            </View>

            {contributions.length === 0 ? (
              <View style={styles.empty}>
                <Ionicons name="wallet-outline" size={40} color={COLORS.textMuted} />
                <Text style={styles.emptyTitle}>No contributions yet</Text>
                <Text style={styles.emptySub}>Join or create a contribution pool to get started.</Text>
              </View>
            ) : (
              contributions.map((c) => {
                const cur = Number(c.current_amount);
                const tgt = c.target_amount ? Number(c.target_amount) : 0;
                const pct = tgt > 0 ? Math.min((cur / tgt) * 100, 100) : 0;
                const myTxCount = transactions.filter((t) => t.contribution === c.id).length;
                const myAmount  = transactions.filter((t) => t.contribution === c.id && t.transaction_type === "CONTRIBUTION")
                                    .reduce((s, t) => s + Number(t.amount), 0);

                return (
                  <TouchableOpacity
                    key={c.id}
                    style={styles.contribCard}
                    onPress={() => router.push({ pathname: "/contribution/[id]", params: { id: String(c.id) } })}
                    activeOpacity={0.75}
                  >
                    <View style={styles.contribHeader}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.contribTitle}>{c.title}</Text>
                        <Text style={styles.contribMeta}>
                          {c.frequency.charAt(0).toUpperCase() + c.frequency.slice(1)}
                          {c.fixed_amount ? ` · KES ${Number(c.fixed_amount).toLocaleString()}` : " · Open"}
                        </Text>
                      </View>
                      <View style={[styles.statusChip, c.is_active ? styles.statusActive : styles.statusClosed]}>
                        <Text style={[styles.statusText, c.is_active ? { color: COLORS.success } : { color: COLORS.textMuted }]}>
                          {c.status}
                        </Text>
                      </View>
                    </View>

                    {/* Pool balance */}
                    <View style={styles.contribAmounts}>
                      <View>
                        <Text style={styles.contribAmountLabel}>Pool Balance</Text>
                        <Text style={styles.contribAmount}>{fmtKES(cur)}</Text>
                      </View>
                      {myAmount > 0 && (
                        <View style={{ alignItems: "flex-end" }}>
                          <Text style={styles.contribAmountLabel}>My Contribution</Text>
                          <Text style={[styles.contribAmount, { color: COLORS.primary }]}>{fmtKES(myAmount)}</Text>
                        </View>
                      )}
                    </View>

                    {/* Progress bar */}
                    {tgt > 0 && (
                      <View style={{ marginTop: 10 }}>
                        <View style={styles.progressBg}>
                          <View style={[styles.progressFill, { width: `${pct}%` }]} />
                        </View>
                        <View style={styles.progressLabels}>
                          <Text style={styles.progressLabel}>{pct.toFixed(0)}% of goal</Text>
                          <Text style={styles.progressLabel}>Target {fmtKES(tgt)}</Text>
                        </View>
                      </View>
                    )}

                    {/* Meta row */}
                    <View style={styles.contribFooter}>
                      <Text style={styles.contribFooterText}>
                        {c.participant_count} member{c.participant_count !== 1 ? "s" : ""}
                      </Text>
                      {myTxCount > 0 && (
                        <Text style={styles.contribFooterText}>{myTxCount} tx by me</Text>
                      )}
                      <Ionicons name="chevron-forward" size={13} color={COLORS.textMuted} />
                    </View>
                  </TouchableOpacity>
                );
              })
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function KPICard({ label, value, sub, icon, color }: {
  label: string; value: string; sub?: string; icon: string; color: string;
}) {
  return (
    <View style={styles.kpiCard}>
      <View style={[styles.kpiIcon, { backgroundColor: color + "18" }]}>
        <Ionicons name={icon as any} size={17} color={color} />
      </View>
      <Text style={styles.kpiValue}>{value}</Text>
      <Text style={styles.kpiLabel}>{label}</Text>
      {sub && <Text style={styles.kpiSub}>{sub}</Text>}
    </View>
  );
}

function MonthlyBarChart({ data }: { data: { month: string; amount: number }[] }) {
  const max = Math.max(...data.map((d) => d.amount), 1);
  return (
    <View>
      <View style={styles.barChart}>
        {data.map((d) => {
          const pct = (d.amount / max) * 100;
          return (
            <View key={d.month} style={styles.barCol}>
              <Text style={styles.barValue}>{d.amount > 0 ? `${(d.amount / 1000).toFixed(0)}k` : ""}</Text>
              <View style={styles.barBg}>
                <View style={[styles.barFill, { height: `${Math.max(pct, 3)}%` }]} />
              </View>
              <Text style={styles.barLabel}>{d.month.split(" ")[0]}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  // Tabs
  tabBar: {
    flexDirection: "row",
    backgroundColor: COLORS.white,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
    paddingHorizontal: 4,
  },
  tabItem: {
    flex: 1, paddingVertical: 13, alignItems: "center",
    borderBottomWidth: 2.5, borderBottomColor: "transparent",
  },
  tabItemActive:   { borderBottomColor: COLORS.primary },
  tabLabel:        { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },
  tabLabelActive:  { color: COLORS.primary },

  // KPI grid
  kpiRow:  { flexDirection: "row", gap: 10 },
  kpiCard: {
    flex: 1, backgroundColor: COLORS.white, borderRadius: RADIUS.lg,
    padding: 14, borderWidth: 1, borderColor: COLORS.divider,
  },
  kpiIcon:  { width: 32, height: 32, borderRadius: RADIUS.md, justifyContent: "center", alignItems: "center", marginBottom: 8 },
  kpiValue: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text, marginBottom: 2 },
  kpiLabel: { fontSize: FONTS.xs, color: COLORS.textMuted,  },
  kpiSub:   { fontSize: FONTS.xs, color: COLORS.textSecondary, marginTop: 3 },

  // Cards
  card:      { backgroundColor: COLORS.white, borderRadius: RADIUS.lg, padding: 16, borderWidth: 1, borderColor: COLORS.divider },
  cardTitle: { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.text, marginBottom: 14,  },

  // Warning card
  warningCard: { borderColor: COLORS.warning + "50", backgroundColor: "#FFFCF0" },
  warningRow:  { flexDirection: "row", alignItems: "center", gap: 12 },
  warningTitle:  { fontSize: FONTS.sm, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  warningValue:  { fontSize: FONTS.md, fontWeight: "700", color: COLORS.warning },
  warningCount:  { fontSize: FONTS.sm, color: COLORS.warning, fontWeight: "700" },

  // Member card
  memberCard: {
    flexDirection: "row", alignItems: "center", gap: 12,
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg,
    padding: 14, borderWidth: 1, borderColor: COLORS.divider,
  },
  memberLabel: { fontSize: FONTS.xs, color: COLORS.textMuted,  },
  memberDate:  { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },

  // Bar chart
  barChart: { flexDirection: "row", alignItems: "flex-end", gap: 6, height: 100 },
  barCol:   { flex: 1, alignItems: "center", height: "100%" },
  barBg:    { flex: 1, width: "100%", justifyContent: "flex-end", borderRadius: RADIUS.sm, overflow: "hidden", backgroundColor: COLORS.background },
  barFill:  { width: "100%", backgroundColor: COLORS.primary + "CC", borderRadius: RADIUS.sm },
  barValue: { fontSize: 8, color: COLORS.textMuted, marginBottom: 3 },
  barLabel: { fontSize: 9, color: COLORS.textMuted, marginTop: 4, fontWeight: "600" },

  // Filter chips
  filterRow:         { flexDirection: "row", gap: 8, paddingBottom: 4 },
  filterChip:        { paddingHorizontal: 14, paddingVertical: 7, borderRadius: RADIUS.full, backgroundColor: COLORS.white, borderWidth: 1, borderColor: COLORS.divider },
  filterChipActive:  { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  filterChipText:    { fontSize: FONTS.sm, color: COLORS.textSecondary, fontWeight: "600" },
  filterChipTextActive: { color: COLORS.white },

  // Filter summary
  filterSummary: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: COLORS.primaryPale, borderRadius: RADIUS.md,
    paddingHorizontal: 14, paddingVertical: 10,
    marginBottom: 4,
  },
  filterSummaryLabel: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },
  filterSummaryValue: { fontSize: FONTS.md, color: COLORS.primary, fontWeight: "700" },

  // Transaction rows
  txRow: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: COLORS.white, borderRadius: RADIUS.md,
    padding: 13, gap: 12,
    marginBottom: 2,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  txIcon:   { width: 38, height: 38, borderRadius: RADIUS.full, justifyContent: "center", alignItems: "center" },
  txTitle:  { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  txDate:   { fontSize: FONTS.sm, color: COLORS.textMuted },
  txRef:    { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 1 },
  txAmount: { fontSize: FONTS.md, fontWeight: "700", marginBottom: 2 },
  txType:   { fontSize: FONTS.xs, color: COLORS.textMuted,  },

  // Contribution cards
  contribCard: {
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg,
    padding: 15, borderWidth: 1, borderColor: COLORS.divider,
    marginBottom: 2,
  },
  contribHeader: { flexDirection: "row", alignItems: "flex-start", marginBottom: 10 },
  contribTitle:  { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginBottom: 2 },
  contribMeta:   { fontSize: FONTS.xs, color: COLORS.textMuted },
  statusChip:    { paddingHorizontal: 10, paddingVertical: 4, borderRadius: RADIUS.full },
  statusActive:  { backgroundColor: COLORS.success + "18" },
  statusClosed:  { backgroundColor: COLORS.background },
  statusText:    { fontSize: FONTS.xs, fontWeight: "700",  },
  contribAmounts: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  contribAmountLabel: { fontSize: FONTS.xs, color: COLORS.textMuted, marginBottom: 2,  },
  contribAmount:  { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },

  progressBg:     { height: 6, backgroundColor: COLORS.divider, borderRadius: RADIUS.full, overflow: "hidden" },
  progressFill:   { height: "100%", backgroundColor: COLORS.primary, borderRadius: RADIUS.full },
  progressLabels: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
  progressLabel:  { fontSize: FONTS.xs, color: COLORS.textMuted },

  contribFooter: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 10, paddingTop: 8, borderTopWidth: 1, borderTopColor: COLORS.divider },
  contribFooterText: { fontSize: FONTS.xs, color: COLORS.textSecondary, flex: 1 },

  empty: { alignItems: "center", paddingVertical: 48, gap: 10 },
  emptyTitle: { fontSize: FONTS.lg, fontWeight: "600", color: COLORS.text },
  emptySub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", paddingHorizontal: 32 },
  emptyText:  { textAlign: "center", color: COLORS.textMuted, padding: 24 },
});
