import { useEffect, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Share,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import * as storage from "../../utils/secureStorage";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";

export default function InviteScreen() {
  const [phone, setPhone] = useState("");

  useEffect(() => {
    storage.getItem("phone").then((p) => p && setPhone(p));
  }, []);

  const message =
    `Join me on Wepl — the easiest way to save and chat with your community.\n\n` +
    `Sign up with your phone number and add ${phone || "me"} as a friend!`;

  const handleShare = async () => {
    try {
      await Share.share({ message });
    } catch {}
  };

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader title="Invite a friend" variant="light" leading="back" onBack={() => router.replace("/(drawer)/profile")} />

      <View style={styles.body}>
        <Text style={styles.hero}>🎉</Text>
        <Text style={styles.title}>Invite friends to Wepl</Text>
        <Text style={styles.sub}>
          Save together, chat in groups, and reach your goals as a community.
        </Text>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>Your message</Text>
          <Text style={styles.cardBody}>{message}</Text>
        </View>

        <TouchableOpacity style={styles.shareBtn} onPress={handleShare}>
          <Text style={styles.shareBtnText}>Share Invite</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  body: { flex: 1, alignItems: "center", paddingHorizontal: 32, paddingTop: 40 },
  hero: { fontSize: 72, marginBottom: 16 },
  title: { fontSize: FONTS.xl, fontWeight: "bold", color: COLORS.text, marginBottom: 10, textAlign: "center" },
  sub: { fontSize: FONTS.md, color: COLORS.textSecondary, textAlign: "center", lineHeight: 22, marginBottom: 32 },

  card: {
    width: "100%",
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    padding: 18,
    marginBottom: 28,
  },
  cardLabel: { fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 },
  cardBody: { fontSize: FONTS.md, color: COLORS.text, lineHeight: 22 },

  shareBtn: {
    width: "100%",
    backgroundColor: COLORS.primary,
    paddingVertical: 16,
    borderRadius: RADIUS.md,
    alignItems: "center",
  },
  shareBtnText: { color: COLORS.white, fontWeight: "bold", fontSize: FONTS.md },
});
