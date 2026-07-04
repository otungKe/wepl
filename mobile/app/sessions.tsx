/**
 * Active Devices — where this account is signed in, with per-session revoke and
 * "sign out everywhere else". Backed by the existing users/sessions endpoints.
 * The single highest-value security screen for a PIN-secured money app.
 */
import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { getSessions, revokeSession, revokeOtherSessions, type UserSession } from "../api/sessions";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

function relTime(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "yesterday" : `${d}d ago`;
}

function deviceIcon(label: string): string {
  const l = (label || "").toLowerCase();
  if (l.includes("iphone") || l.includes("ios") || l.includes("ipad")) return "phone-portrait-outline";
  if (l.includes("android")) return "phone-portrait-outline";
  if (l.includes("web") || l.includes("chrome") || l.includes("safari") || l.includes("firefox")) return "desktop-outline";
  return "hardware-chip-outline";
}

export default function SessionsScreen() {
  const [sessions, setSessions] = useState<UserSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getSessions().then(setSessions).catch(() => {});
  }, []);

  useFocusEffect(useCallback(() => {
    getSessions().then(setSessions).catch(() => {}).finally(() => setLoading(false));
  }, []));

  const others = sessions.filter(s => !s.is_current).length;

  const onRevoke = (sess: UserSession) => {
    Alert.alert(
      "Sign out this device?",
      `${sess.device_label || "This device"} will be signed out immediately.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Sign out", style: "destructive",
          onPress: async () => {
            setBusy(true);
            try { await revokeSession(sess.sid); load(); }
            catch { Alert.alert("Error", "Could not sign out that device."); }
            finally { setBusy(false); }
          },
        },
      ],
    );
  };

  const onRevokeOthers = () => {
    Alert.alert(
      "Sign out everywhere else?",
      "Every device except this one will be signed out. You'll stay signed in here.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Sign out others", style: "destructive",
          onPress: async () => {
            setBusy(true);
            try {
              const n = await revokeOtherSessions();
              load();
              Alert.alert("Done", n ? `Signed out ${n} other device${n === 1 ? "" : "s"}.` : "No other devices were signed in.");
            } catch { Alert.alert("Error", "Could not sign out other devices."); }
            finally { setBusy(false); }
          },
        },
      ],
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Active Devices" variant="light" leading="back" onBack={() => router.back()} />
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  const current = sessions.find(s => s.is_current);
  const rest = sessions.filter(s => !s.is_current);

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader title="Active Devices" variant="light" leading="back" onBack={() => router.back()} />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <Text style={s.intro}>
          These are the devices signed in to your WEPL account. If you don&apos;t
          recognise one, sign it out — and change your PIN.
        </Text>

        {current && (
          <>
            <Text style={s.sectionLabel}>THIS DEVICE</Text>
            <View style={s.card}>
              <SessionRow sess={current} current />
            </View>
          </>
        )}

        {rest.length > 0 && (
          <>
            <Text style={s.sectionLabel}>OTHER DEVICES</Text>
            <View style={s.card}>
              {rest.map((sess, i) => (
                <View key={sess.sid}>
                  {i > 0 && <View style={s.divider} />}
                  <SessionRow sess={sess} onRevoke={() => onRevoke(sess)} />
                </View>
              ))}
            </View>
          </>
        )}

        {others > 0 && (
          <TouchableOpacity style={[s.dangerBtn, busy && { opacity: 0.6 }]} onPress={onRevokeOthers} disabled={busy}>
            <Ionicons name="log-out-outline" size={18} color={COLORS.error} />
            <Text style={s.dangerBtnText}>Sign out all other devices</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function SessionRow({ sess, current, onRevoke }: { sess: UserSession; current?: boolean; onRevoke?: () => void }) {
  return (
    <View style={s.row}>
      <View style={[s.rowIcon, { backgroundColor: current ? COLORS.primary + "18" : COLORS.background }]}>
        <Ionicons name={deviceIcon(sess.device_label) as any} size={20} color={current ? COLORS.primary : COLORS.textSecondary} />
      </View>
      <View style={{ flex: 1 }}>
        <View style={s.rowTitleLine}>
          <Text style={s.rowTitle} numberOfLines={1}>{sess.device_label || "Unknown device"}</Text>
          {current && <View style={s.currentChip}><Text style={s.currentChipText}>This device</Text></View>}
        </View>
        <Text style={s.rowSub}>
          {sess.ip_address ? `${sess.ip_address} · ` : ""}Active {relTime(sess.last_seen_at)}
        </Text>
      </View>
      {onRevoke && (
        <TouchableOpacity style={s.revokeBtn} onPress={onRevoke} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Ionicons name="close" size={16} color={COLORS.error} />
        </TouchableOpacity>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  scroll: { padding: 16, paddingBottom: 48 },

  intro: { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 20, marginBottom: 4, paddingHorizontal: 4 },
  sectionLabel: { fontSize: 11, fontWeight: "700", color: COLORS.textMuted, letterSpacing: 0.6, marginTop: 20, marginBottom: 8, marginLeft: 4 },

  card: { backgroundColor: COLORS.white, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, overflow: "hidden" },
  divider: { height: 1, backgroundColor: COLORS.divider, marginLeft: 66 },

  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingVertical: 14 },
  rowIcon: { width: 40, height: 40, borderRadius: 11, justifyContent: "center", alignItems: "center" },
  rowTitleLine: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowTitle: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, flexShrink: 1 },
  rowSub: { fontSize: FONTS.xs, color: COLORS.textMuted, marginTop: 2 },

  currentChip: { backgroundColor: COLORS.primaryPale, paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full },
  currentChipText: { fontSize: 11, fontWeight: "700", color: COLORS.primary },
  revokeBtn: { width: 30, height: 30, borderRadius: 15, backgroundColor: COLORS.error + "12", justifyContent: "center", alignItems: "center" },

  dangerBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    marginTop: 20, paddingVertical: 14, borderRadius: RADIUS.md,
    borderWidth: 1.5, borderColor: COLORS.error + "55", backgroundColor: COLORS.error + "0D",
  },
  dangerBtnText: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.error },
});
