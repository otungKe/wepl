import { useState } from "react";
import {
  View,
  TextInput,
  TouchableOpacity,
  Text,
  StyleSheet,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { createConversation } from "../../api/conversations";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import FAB from "../../components/app/FAB";

export default function CreateConversationScreen() {
  const { communityId } = useLocalSearchParams<{ communityId: string }>();
  const [topic, setTopic] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!topic.trim()) {
      Alert.alert("Topic required", "Please enter a topic for this conversation.");
      return;
    }
    setSaving(true);
    try {
      const c = await createConversation(Number(communityId), { topic: topic.trim() });
      router.replace({
        pathname: `/conversation/${c.id}`,
        params: { topic: c.topic, communityId },
      });
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to create conversation.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader title="New Conversation" variant="light" leading="back" rightIcon="more" />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
      <View style={styles.body}>
        <TouchableOpacity style={styles.photoBox} activeOpacity={0.7}>
          <Ionicons name="camera-outline" size={40} color={COLORS.textMuted} />
        </TouchableOpacity>

        <TextInput
          placeholder="Topic of your discussion"
          placeholderTextColor={COLORS.textMuted}
          value={topic}
          onChangeText={setTopic}
          style={styles.input}
          autoFocus
        />
      </View>
      </KeyboardAvoidingView>

      <FAB icon="check" onPress={handleSave} disabled={saving} loading={saving} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  body: { paddingHorizontal: 24, paddingTop: 16, alignItems: "center" },

  photoBox: {
    width: 140, height: 140, borderRadius: RADIUS.full,
    backgroundColor: COLORS.divider,
    justifyContent: "center", alignItems: "center",
    marginBottom: 22,
  },

  input: {
    width: "100%",
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 14,
    fontSize: FONTS.md,
    color: COLORS.text,
    backgroundColor: COLORS.white,
    textAlign: "center",
  },

});
