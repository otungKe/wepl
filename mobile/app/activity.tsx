import { useCallback, useRef, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  ScrollView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getActivity, type Activity } from "../api/activity";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

// ─── Activity type metadata ───────────────────────────────────────────────────

type ActivityMeta = {
  icon:    string;
  color:   string;
  bg:      string;
  label:   string;
};

const ACTIVITY_META: Record<string, ActivityMeta> = {
  payment:           { icon: "card",                    color: COLORS.accent,        bg: COLORS.accentPale,   label: "Payment"       },
  mpesa:             { icon: "phone-portrait-outline",  color: COLORS.accent,        bg: COLORS.accentPale,   label: "M-Pesa"        },
  contribution:      { icon: "wallet",                  color: COLORS.primary,       bg: COLORS.primaryPale,  label: "Contribution"  },
  contribution_due:  { icon: "alarm",                   color: COLORS.warning,       bg: COLORS.warning+"18", label: "Due"           },
  join:              { icon: "person-add",              color: "#5C7AE0",            bg: "#5C7AE018",         label: "Joined"        },
  join_request:      { icon: "person-add-outline",      color: "#5C7AE0",            bg: "#5C7AE018",         label: "Join Request"  },
  leave:             { icon: "exit-outline",            color: COLORS.textMuted,     bg: COLORS.divider,      label: "Left"          },
  advance:           { icon: "trending-up",             color: "#9C4FE0",            bg: "#9C4FE018",         label: "Advance"       },
  repayment:         { icon: "trending-down",           color: COLORS.success,       bg: COLORS.primaryPale,  label: "Repayment"     },
  welfare:           { icon: "heart",                   color: "#E05C5C",            bg: "#E05C5C18",         label: "Welfare"       },
  welfare_payout:    { icon: "gift",                    color: "#E05C5C",            bg: "#E05C5C18",         label: "Welfare"       },
  admin:             { icon: "shield",                  color: COLORS.primary,       bg: COLORS.primaryPale,  label: "Admin"         },
  admin_action:      { icon: "shield-checkmark",        color: COLORS.primary,       bg: COLORS.primaryPale,  label: "Admin"         },
  kyc:               { icon: "checkmark-circle",        color: COLORS.success,       bg: COLORS.primaryPale,  label: "KYC"           },
  message:           { icon: "chatbubble",              color: "#5C9AE0",            bg: "#5C9AE018",         label: "Message"       },
  community_created: { icon: "people",                  color: COLORS.primary,       bg: COLORS.primaryPale,  label: "Community"     },
};

const DEFAULT_META: ActivityMeta = {
  icon:  "ellipse",
  color: COLORS.textMuted,
  bg:    COLORS.divider,
  label: "Activity",
};

function metaFor(type: string): ActivityMeta {
  // Try exact match first
  if (ACTIVITY_META[type]) return ACTIVITY_META[type];
  // Try prefix match
  for (const key of Object.keys(ACTIVITY_META)) {
    if (type.startsWith(key) || key.startsWith(type)) return ACTIVITY_META[key];
  }
  return DEFAULT_META;
}

// ─── Filter chips config ──────────────────────────────────────────────────────

const FILTERS = [
  { key: null,           label: "All"           },
  { key: "payment",      label: "Payments"      },
  { key: "contribution", label: "Contributions" },
  { key: "join",         label: "Community"     },
  { key: "advance",      label: "Advances"      },
  { key: "welfare",      label: "Welfare"       },
  { key: "admin",        label: "Admin"         },
];

// ─── Date grouping helpers ────────────────────────────────────────────────────

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const now   = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yest  = new Date(today.getTime() - 86_400_000);
  const dd    = new Date(d.getFullYear(), d.getMonth(), d.getDate());

  if (dd.getTime() === today.getTime()) return "Today";
  if (dd.getTime() === yest.getTime())  return "Yesterday";
  return d.toLocaleDateString("en-KE", { weekday: "long", month: "short", day: "numeric" });
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-KE", { hour: "numeric", minute: "2-digit" });
}

function groupActivities(list: Activity[]): Array<{ type: "header"; date: string } | { type: "item"; data: Activity }> {
  const rows: Array<{ type: "header"; date: string } | { type: "item"; data: Activity }> = [];
  let lastDate = "";
  for (const a of list) {
    const date = fmtDate(a.created_at);
    if (date !== lastDate) {
      rows.push({ type: "header", date });
      lastDate = date;
    }
    rows.push({ type: "item", data: a });
  }
  return rows;
}

// ─── Activity row ─────────────────────────────────────────────────────────────

function ActivityRow({ item }: { item: Activity }) {
  const meta = metaFor(item.activity_type);
  return (
    <View style={ar.row}>
      {/* Icon */}
      <View style={[ar.icon, { backgroundColor: meta.bg }]}>
        <Ionicons name={meta.icon as any} size={18} color={meta.color} />
      </View>

      {/* Body */}
      <View style={ar.body}>
        <View style={ar.topRow}>
          <Text style={ar.message} numberOfLines={2}>{item.message}</Text>
        </View>
        <View style={ar.bottomRow}>
          <View style={[ar.badge, { backgroundColor: meta.bg }]}>
            <Text style={[ar.badgeText, { color: meta.color }]}>{meta.label}</Text>
          </View>
          <Text style={ar.time}>{fmtTime(item.created_at)}</Text>
        </View>
      </View>
    </View>
  );
}

const ar = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },
  icon: {
    width: 38, height: 38,
    borderRadius: RADIUS.md,
    justifyContent: "center",
    alignItems: "center",
    marginRight: 12,
    marginTop: 1,
  },
  body: { flex: 1 },
  topRow: { marginBottom: 5 },
  message: {
    fontSize: FONTS.md,
    color: COLORS.text,
    lineHeight: 20,
  },
  bottomRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: RADIUS.full,
  },
  badgeText: {
    fontSize: FONTS.xs,
    fontWeight: "700",
  },
  time: {
    fontSize: FONTS.xs,
    color: COLORS.textMuted,
    marginLeft: "auto",
  },
});

// ─── Section header ───────────────────────────────────────────────────────────

function DateHeader({ date }: { date: string }) {
  return (
    <View style={dh.wrap}>
      <View style={dh.line} />
      <Text style={dh.text}>{date}</Text>
      <View style={dh.line} />
    </View>
  );
}

const dh = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: COLORS.background,
  },
  line: { flex: 1, height: 1, backgroundColor: COLORS.divider },
  text: {
    fontSize: FONTS.xs,
    color: COLORS.textMuted,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.7,
    paddingHorizontal: 10,
  },
});

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <View style={es.wrap}>
      <Ionicons name="pulse-outline" size={52} color={COLORS.border} />
      <Text style={es.title}>{filtered ? "No matching activity" : "No activity yet"}</Text>
      <Text style={es.body}>
        {filtered
          ? "Try a different filter or clear the selection."
          : "Your financial activity will appear here as you contribute, receive payouts, and interact with communities."
        }
      </Text>
    </View>
  );
}

const es = StyleSheet.create({
  wrap: {
    alignItems: "center",
    paddingTop: 80,
    paddingHorizontal: 36,
    gap: 12,
  },
  title: {
    fontSize: FONTS.lg,
    fontWeight: "700",
    color: COLORS.textSecondary,
    textAlign: "center",
  },
  body: {
    fontSize: FONTS.md,
    color: COLORS.textMuted,
    textAlign: "center",
    lineHeight: 22,
  },
});

// ─── Main Screen ─────────────────────────────────────────────────────────────

const PAGE_SIZE = 40;

export default function ActivityScreen() {
  const [items,       setItems]       = useState<Activity[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [refreshing,  setRefreshing]  = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore,     setHasMore]     = useState(false);
  const [total,       setTotal]       = useState(0);
  const [filter,      setFilter]      = useState<string | null>(null);

  const offsetRef = useRef(0);

  async function fetchPage(reset: boolean, typeFilter: string | null) {
    const offset = reset ? 0 : offsetRef.current;
    const result = await getActivity({
      type:   typeFilter ?? undefined,
      limit:  PAGE_SIZE,
      offset,
    });
    return result;
  }

  async function load(resetFilter?: string | null) {
    const t = resetFilter !== undefined ? resetFilter : filter;
    setLoading(true);
    try {
      const result = await fetchPage(true, t);
      setItems(result.results);
      setHasMore(result.has_more);
      setTotal(result.count);
      offsetRef.current = result.results.length;
    } catch {
      // silently fail on initial load
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const result = await fetchPage(false, filter);
      setItems(prev => [...prev, ...result.results]);
      setHasMore(result.has_more);
      offsetRef.current += result.results.length;
    } catch {
    } finally {
      setLoadingMore(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    offsetRef.current = 0;
    try {
      const result = await fetchPage(true, filter);
      setItems(result.results);
      setHasMore(result.has_more);
      setTotal(result.count);
      offsetRef.current = result.results.length;
    } catch {
    } finally {
      setRefreshing(false);
    }
  }

  function applyFilter(key: string | null) {
    setFilter(key);
    offsetRef.current = 0;
    load(key);
  }

  useFocusEffect(
    useCallback(() => {
      load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
  );

  const grouped = groupActivities(items);

  type RowItem = { type: "header"; date: string } | { type: "item"; data: Activity };

  const renderRow = ({ item }: { item: RowItem }) => {
    if (item.type === "header") return <DateHeader date={item.date} />;
    return <ActivityRow item={item.data} />;
  };

  const keyExtractor = (item: RowItem, idx: number) => {
    if (item.type === "header") return `hdr-${item.date}`;
    return `act-${item.data.id}-${idx}`;
  };

  return (
    <SafeAreaView style={ms.safe}>
      <AppHeader
        title="Activity"
        variant="light"
        leading="back"
        rightExtra={
          total > 0 ? (
            <View style={ms.countChip}>
              <Text style={ms.countText}>{total}</Text>
            </View>
          ) : undefined
        }
      />

      {/* Filter chips */}
      <View style={ms.filterBar}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={ms.filterScroll}
        >
          {FILTERS.map(f => (
            <TouchableOpacity
              key={String(f.key)}
              style={[ms.chip, filter === f.key && ms.chipActive]}
              onPress={() => applyFilter(f.key)}
            >
              <Text style={[ms.chipText, filter === f.key && ms.chipTextActive]}>
                {f.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {loading ? (
        <View style={ms.center}>
          <ActivityIndicator color={COLORS.primary} size="large" />
          <Text style={ms.loadingText}>Loading activity…</Text>
        </View>
      ) : (
        <FlatList
          data={grouped}
          keyExtractor={keyExtractor}
          renderItem={renderRow}
          contentContainerStyle={grouped.length === 0 ? { flex: 1 } : undefined}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />
          }
          ListEmptyComponent={<EmptyState filtered={filter !== null} />}
          ListFooterComponent={
            hasMore ? (
              <TouchableOpacity style={ms.loadMore} onPress={loadMore} disabled={loadingMore}>
                {loadingMore
                  ? <ActivityIndicator color={COLORS.primary} size="small" />
                  : (
                    <View style={ms.loadMoreInner}>
                      <Ionicons name="chevron-down" size={16} color={COLORS.primary} />
                      <Text style={ms.loadMoreText}>Load more</Text>
                    </View>
                  )
                }
              </TouchableOpacity>
            ) : (
              items.length > 0 ? (
                <View style={ms.endRow}>
                  <View style={ms.endLine} />
                  <Text style={ms.endText}>All caught up</Text>
                  <View style={ms.endLine} />
                </View>
              ) : null
            )
          }
          showsVerticalScrollIndicator={false}
          initialNumToRender={20}
          maxToRenderPerBatch={20}
          windowSize={10}
        />
      )}
    </SafeAreaView>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const ms = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center", gap: 12 },

  loadingText: {
    fontSize: FONTS.sm,
    color: COLORS.textMuted,
  },

  countChip: {
    backgroundColor: COLORS.primaryPale,
    borderRadius: RADIUS.full,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginRight: 6,
  },
  countText: {
    fontSize: FONTS.xs,
    color: COLORS.primary,
    fontWeight: "700",
  },

  filterBar: {
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },
  filterScroll: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: RADIUS.full,
    borderWidth: 1.5,
    borderColor: COLORS.border,
    backgroundColor: COLORS.white,
  },
  chipActive: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  chipText:       { fontSize: FONTS.sm, color: COLORS.textSecondary, fontWeight: "600" },
  chipTextActive: { color: COLORS.white },

  loadMore: {
    paddingVertical: 16,
    alignItems: "center",
  },
  loadMoreInner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  loadMoreText: {
    fontSize: FONTS.sm,
    color: COLORS.primary,
    fontWeight: "600",
  },

  endRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 24,
    paddingVertical: 20,
  },
  endLine: { flex: 1, height: 1, backgroundColor: COLORS.divider },
  endText: {
    fontSize: FONTS.xs,
    color: COLORS.textMuted,
    paddingHorizontal: 12,
    fontWeight: "600",
  },
});
