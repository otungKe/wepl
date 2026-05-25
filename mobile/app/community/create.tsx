import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Switch,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Modal,
  Pressable,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { createCommunity } from "../../api/communities";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import FAB from "../../components/app/FAB";

const CATEGORIES = [
  { key: "general",    label: "General"              },
  { key: "savings",    label: "Savings"              },
  { key: "chama",      label: "Chama / Investment Club" },
  { key: "investment", label: "Investment"           },
  { key: "welfare",    label: "Welfare"              },
  { key: "emergency",  label: "Emergency Fund"       },
  { key: "business",   label: "Business"             },
];

export default function CreateCommunityScreen() {
  const [name, setName]               = useState("");
  const [description, setDescription] = useState("");
  const [hasWelfare, setHasWelfare]   = useState(false);
  const [hasShares, setHasShares]     = useState(false);
  const [sharePrice, setSharePrice]   = useState("100");
  const [isPublic, setIsPublic]       = useState(false);
  const [category, setCategory]       = useState("general");
  const [location, setLocation]       = useState("");
  const [showCatPicker, setShowCatPicker] = useState(false);
  const [saving, setSaving]           = useState(false);

  const categoryLabel = CATEGORIES.find((c) => c.key === category)?.label ?? "General";

  const handleSave = async () => {
    if (!name.trim()) {
      Alert.alert("Name required", "Please choose a name for your community.");
      return;
    }
    setSaving(true);
    try {
      const c = await createCommunity({
        name:             name.trim(),
        description:      description.trim() || undefined,
        has_welfare_fund: hasWelfare,
        has_shares_fund:  hasShares,
        share_price:      hasShares ? Number(sharePrice) : undefined,
        is_private:       !isPublic,
        category,
        location:         location.trim() || undefined,
      });
      router.replace({ pathname: `/community/${c.id}`, params: { name: c.name } });
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.name?.[0] || "Failed to create community.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader title="Create a Community" variant="light" leading="back" />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        {/* Photo picker placeholder */}
        <TouchableOpacity style={styles.photoBox} activeOpacity={0.7}>
          <Ionicons name="camera-outline" size={40} color={COLORS.textMuted} />
        </TouchableOpacity>

        <TextInput
          placeholder="Choose the name of your Community"
          placeholderTextColor={COLORS.textMuted}
          value={name}
          onChangeText={setName}
          style={styles.input}
          autoFocus
        />

        <TextInput
          placeholder="Description (optional)"
          placeholderTextColor={COLORS.textMuted}
          value={description}
          onChangeText={setDescription}
          style={[styles.input, styles.textarea]}
          multiline
        />

        {/* Discoverability */}
        <Text style={styles.sectionTitle}>Discoverability</Text>

        <View style={styles.toggleRow}>
          <View style={styles.toggleIcon}>
            <Ionicons name="compass-outline" size={20} color={COLORS.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleLabel}>Make publicly discoverable</Text>
            <Text style={styles.toggleDesc}>
              Anyone can find and request to join this community from the Discover screen.
            </Text>
          </View>
          <Switch
            value={isPublic}
            onValueChange={setIsPublic}
            trackColor={{ true: COLORS.primary }}
            thumbColor={COLORS.white}
          />
        </View>

        {isPublic && (
          <>
            {/* Category */}
            <Text style={styles.label}>Category</Text>
            <TouchableOpacity
              style={styles.picker}
              onPress={() => setShowCatPicker(true)}
            >
              <Text style={styles.pickerText}>{categoryLabel}</Text>
              <Ionicons name="chevron-down" size={16} color={COLORS.textMuted} />
            </TouchableOpacity>

            {/* Location */}
            <Text style={styles.label}>Location (optional)</Text>
            <TextInput
              placeholder="e.g. Nairobi, Westlands"
              placeholderTextColor={COLORS.textMuted}
              value={location}
              onChangeText={setLocation}
              style={styles.input}
            />
            <Text style={styles.hint}>
              Helps members nearby find your community.
            </Text>
          </>
        )}

        {/* Community funds */}
        <Text style={styles.sectionTitle}>Community Funds</Text>

        <View style={styles.toggleRow}>
          <View style={styles.toggleIcon}>
            <Ionicons name="heart-outline" size={20} color="#c0392b" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleLabel}>Welfare Fund</Text>
            <Text style={styles.toggleDesc}>A shared emergency pool — members submit claims, others vote to release funds.</Text>
          </View>
          <Switch
            value={hasWelfare}
            onValueChange={setHasWelfare}
            trackColor={{ true: COLORS.primary }}
            thumbColor={COLORS.white}
          />
        </View>

        <View style={styles.toggleRow}>
          <View style={styles.toggleIcon}>
            <Ionicons name="stats-chart-outline" size={20} color={COLORS.accent} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleLabel}>Shares Fund</Text>
            <Text style={styles.toggleDesc}>Members earn shares and track their ownership stake in community funds.</Text>
          </View>
          <Switch
            value={hasShares}
            onValueChange={setHasShares}
            trackColor={{ true: COLORS.primary }}
            thumbColor={COLORS.white}
          />
        </View>

        {hasShares && (
          <>
            <Text style={styles.label}>Share price (KES per share)</Text>
            <TextInput
              placeholder="100"
              placeholderTextColor={COLORS.textMuted}
              value={sharePrice}
              onChangeText={setSharePrice}
              style={styles.input}
              keyboardType="numeric"
            />
            <Text style={styles.hint}>e.g. KES 100 per share — KES 1,000 contribution = 10 shares.</Text>
          </>
        )}

        <View style={{ height: 100 }} />
      </ScrollView>
      </KeyboardAvoidingView>

      {saving ? (
        <View style={styles.savingOverlay}>
          <ActivityIndicator size="large" color={COLORS.white} />
        </View>
      ) : (
        <FAB icon="check" onPress={handleSave} disabled={saving} />
      )}

      {/* Category picker modal */}
      <Modal
        visible={showCatPicker}
        transparent
        animationType="slide"
        onRequestClose={() => setShowCatPicker(false)}
      >
        <Pressable style={styles.modalBackdrop} onPress={() => setShowCatPicker(false)}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>Community Category</Text>
            {CATEGORIES.map((c) => (
              <TouchableOpacity
                key={c.key}
                style={[styles.modalOption, category === c.key && styles.modalOptionActive]}
                onPress={() => { setCategory(c.key); setShowCatPicker(false); }}
              >
                <Text style={[styles.modalOptionText, category === c.key && styles.modalOptionTextActive]}>
                  {c.label}
                </Text>
                {category === c.key && (
                  <Ionicons name="checkmark" size={18} color={COLORS.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.background },
  body: { paddingHorizontal: 24, paddingTop: 16, alignItems: "center" },

  photoBox: {
    width: 140, height: 140,
    borderRadius: RADIUS.full,
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
    marginBottom: 12,
  },
  textarea: { height: 90, textAlignVertical: "top" },

  sectionTitle: {
    alignSelf: "flex-start",
    fontSize: FONTS.md,
    fontWeight: "700",
    color: COLORS.text,
    marginTop: 8,
    marginBottom: 4,
  },

  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    width: "100%",
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
    backgroundColor: COLORS.white,
  },
  toggleIcon: {
    width: 36, height: 36,
    borderRadius: RADIUS.full,
    backgroundColor: COLORS.background,
    justifyContent: "center", alignItems: "center",
  },
  toggleLabel: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, marginBottom: 2 },
  toggleDesc:  { fontSize: FONTS.sm, color: COLORS.textMuted, lineHeight: 18 },

  label: {
    alignSelf: "flex-start",
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginTop: 16, marginBottom: 8,
    textTransform: "uppercase", letterSpacing: 0.4,
  },
  hint: { alignSelf: "flex-start", fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 4, lineHeight: 18 },

  savingOverlay: {
    position: "absolute",
    right: 20, bottom: 24,
    width: 60, height: 60,
    borderRadius: RADIUS.full,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
  },

  // Picker
  picker: {
    flexDirection:   "row",
    alignItems:      "center",
    justifyContent:  "space-between",
    width:           "100%",
    borderWidth:     1.5,
    borderColor:     COLORS.border,
    borderRadius:    RADIUS.md,
    padding:         14,
    backgroundColor: COLORS.white,
    marginBottom:    12,
  },
  pickerText: {
    fontSize: FONTS.md,
    color:    COLORS.text,
  },

  // Modal
  modalBackdrop: {
    flex:            1,
    backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent:  "flex-end",
  },
  modalSheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius:  RADIUS.lg,
    borderTopRightRadius: RADIUS.lg,
    paddingTop:      12,
    paddingBottom:   36,
    paddingHorizontal: 20,
  },
  modalHandle: {
    width:           40,
    height:          4,
    borderRadius:    RADIUS.full,
    backgroundColor: COLORS.border,
    alignSelf:       "center",
    marginBottom:    16,
  },
  modalTitle: {
    fontSize:     FONTS.lg,
    fontWeight:   "700",
    color:        COLORS.text,
    marginBottom: 12,
  },
  modalOption: {
    flexDirection:   "row",
    alignItems:      "center",
    justifyContent:  "space-between",
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },
  modalOptionActive: {
    // no bg change — just show checkmark
  },
  modalOptionText: {
    fontSize:   FONTS.md,
    color:      COLORS.text,
  },
  modalOptionTextActive: {
    fontWeight: "700",
    color:      COLORS.primary,
  },
});
