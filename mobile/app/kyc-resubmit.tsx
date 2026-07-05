/**
 * Targeted KYC re-submission — the user tops up ONLY the items a reviewer asked
 * for (kyc.resubmission_requested). Everything else in their KYC is left as-is;
 * they do not re-fill the whole form. Submits to POST users/kyc/resubmit/.
 */
import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator,
  TextInput, Alert, Image, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { getKYCStatus, resubmitKYC, KYC_ITEM_LABELS } from "../api/auth";
import { suppressNextLock } from "../utils/lockSuppress";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";

type Photo = { uri: string; name: string; type: string } | null;

const PHOTO_KEYS = ["id_front", "id_back", "selfie"];
const SELECT_SOURCES: Record<string, string> = {
  county: "counties",
  source_of_income: "income_sources",
  expected_monthly_income: "income_bands",
};

export default function KYCResubmitScreen() {
  const [loading, setLoading]     = useState(true);
  const [requested, setRequested] = useState<string[]>([]);
  const [kyc, setKyc]             = useState<any>(null);
  const [values, setValues]       = useState<Record<string, string>>({});
  const [photos, setPhotos]       = useState<Record<string, Photo>>({});
  const [submitting, setSubmitting] = useState(false);

  useFocusEffect(useCallback(() => {
    let active = true;
    getKYCStatus()
      .then((d) => {
        if (!active) return;
        setKyc(d);
        const req: string[] = d?.resubmission_requested ?? [];
        setRequested(req);
        // Pre-fill text/select items from the existing KYC so the user only
        // edits what changed.
        const v: Record<string, string> = {};
        req.forEach((k) => { if (!PHOTO_KEYS.includes(k)) v[k] = String(d?.[k] ?? ""); });
        setValues(v);
      })
      .catch(() => {})
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []));

  const capture = async (key: string) => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "Allow camera access to take the photo.");
      return;
    }
    suppressNextLock();
    const result = await ImagePicker.launchCameraAsync({
      quality: 0.7,
      aspect: key === "selfie" ? [1, 1] : [4, 3],
      cameraType: key === "selfie" ? ImagePicker.CameraType.front : ImagePicker.CameraType.back,
    });
    if (result.canceled) return;
    const a = result.assets[0];
    setPhotos((p) => ({ ...p, [key]: { uri: a.uri, name: a.uri.split("/").pop() ?? `${key}.jpg`, type: a.mimeType ?? "image/jpeg" } }));
  };

  const missing = requested.filter((k) =>
    PHOTO_KEYS.includes(k) ? !photos[k] : !(values[k] ?? "").trim());

  const submit = async () => {
    if (missing.length) {
      Alert.alert("Almost there", `Please provide: ${missing.map((k) => KYC_ITEM_LABELS[k] ?? k).join(", ")}.`);
      return;
    }
    setSubmitting(true);
    try {
      const form = new FormData();
      requested.forEach((k) => {
        if (PHOTO_KEYS.includes(k)) {
          const ph = photos[k]!;
          form.append(k, { uri: ph.uri, name: ph.name, type: ph.type } as any);
        } else {
          form.append(k, (values[k] ?? "").trim());
        }
      });
      await resubmitKYC(form);
      Alert.alert("Submitted", "Thanks — we've received your update and will review it shortly.", [
        { text: "OK", onPress: () => router.replace("/verification") },
      ]);
    } catch (e: any) {
      const miss = e?.response?.data?.missing;
      Alert.alert("Couldn't submit", Array.isArray(miss)
        ? `Still needed: ${miss.join(", ")}.`
        : (e?.response?.data?.error || "Please try again."));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Re-submit KYC" variant="light" leading="back" onBack={() => router.back()} />
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  if (!requested.length) {
    return (
      <SafeAreaView style={s.safe}>
        <AppHeader title="Re-submit KYC" variant="light" leading="back" onBack={() => router.back()} />
        <View style={s.center}>
          <Ionicons name="checkmark-done-outline" size={40} color={COLORS.textMuted} />
          <Text style={s.emptyText}>Nothing to re-submit right now.</Text>
          <TouchableOpacity style={s.primaryBtn} onPress={() => router.replace("/verification")}>
            <Text style={s.primaryBtnText}>Back to Verification Center</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <AppHeader title="Re-submit KYC" variant="light" leading="back" onBack={() => router.back()} />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <Text style={s.lead}>
            We only need the {requested.length === 1 ? "item" : "items"} below — the rest of your
            details stay exactly as they are.
          </Text>

          {requested.map((key) => {
            const label = KYC_ITEM_LABELS[key] ?? key;
            if (PHOTO_KEYS.includes(key)) {
              const ph = photos[key];
              return (
                <View key={key} style={s.field}>
                  <Text style={s.fieldLabel}>{label}</Text>
                  <TouchableOpacity style={[s.photoBox, ph && s.photoBoxDone]} onPress={() => capture(key)} activeOpacity={0.8}>
                    {ph ? (
                      <>
                        <Image source={{ uri: ph.uri }} style={s.photoPreview} resizeMode="cover" />
                        <View style={s.retake}><Ionicons name="camera" size={18} color="#fff" /><Text style={s.retakeText}>Retake</Text></View>
                      </>
                    ) : (
                      <View style={s.photoPrompt}>
                        <Ionicons name="camera-outline" size={34} color={COLORS.primary} />
                        <Text style={s.photoPromptText}>Tap to take photo</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                </View>
              );
            }
            const source = SELECT_SOURCES[key];
            if (source) {
              const opts: any[] = kyc?.[source] ?? [];
              return (
                <View key={key} style={s.field}>
                  <Text style={s.fieldLabel}>{label}</Text>
                  <View style={s.chipWrap}>
                    {opts.map((o) => {
                      const val = typeof o === "string" ? o : o.value;
                      const lbl = typeof o === "string" ? o : o.label;
                      const sel = values[key] === val;
                      return (
                        <TouchableOpacity key={val} style={[s.chip, sel && s.chipOn]}
                          onPress={() => setValues((v) => ({ ...v, [key]: val }))}>
                          <Text style={[s.chipText, sel && s.chipTextOn]}>{lbl}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              );
            }
            return (
              <View key={key} style={s.field}>
                <Text style={s.fieldLabel}>{label}</Text>
                <TextInput
                  style={s.input}
                  value={values[key] ?? ""}
                  onChangeText={(t) => setValues((v) => ({ ...v, [key]: key === "kra_pin" ? t.toUpperCase() : t }))}
                  placeholder={key === "date_of_birth" ? "YYYY-MM-DD" : `Enter ${label.toLowerCase()}`}
                  placeholderTextColor={COLORS.textMuted}
                  autoCapitalize={key === "kra_pin" ? "characters" : "none"}
                  keyboardType={key === "id_number" ? "numeric" : key === "email" ? "email-address" : "default"}
                />
              </View>
            );
          })}

          <TouchableOpacity style={[s.primaryBtn, (submitting || missing.length > 0) && { opacity: 0.6 }]}
            onPress={submit} disabled={submitting}>
            {submitting ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryBtnText}>Submit</Text>}
          </TouchableOpacity>
          <Text style={s.note}>Your information is encrypted and used only to verify your identity.</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24, gap: 12 },
  scroll: { padding: 20, paddingBottom: 48 },
  lead:   { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 20, marginBottom: 18 },

  field:      { marginBottom: 18 },
  fieldLabel: { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.text, marginBottom: 8 },
  input: {
    borderWidth: 1, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, fontSize: FONTS.md, color: COLORS.text, backgroundColor: COLORS.white,
  },

  photoBox: {
    height: 170, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border,
    borderStyle: "dashed", justifyContent: "center", alignItems: "center",
    backgroundColor: COLORS.white, overflow: "hidden",
  },
  photoBoxDone:   { borderStyle: "solid", borderColor: COLORS.primary },
  photoPrompt:    { alignItems: "center", gap: 6 },
  photoPromptText:{ fontSize: FONTS.sm, color: COLORS.textMuted },
  photoPreview:   { width: "100%", height: "100%" },
  retake: {
    position: "absolute", bottom: 8, right: 8, flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: "rgba(0,0,0,0.55)", paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full,
  },
  retakeText: { color: "#fff", fontSize: FONTS.xs, fontWeight: "600" },

  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    paddingHorizontal: 13, paddingVertical: 8, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.white,
  },
  chipOn:     { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText:   { fontSize: FONTS.sm, color: COLORS.text },
  chipTextOn: { color: "#fff", fontWeight: "700" },

  primaryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    backgroundColor: COLORS.primary, paddingVertical: 14, borderRadius: RADIUS.md, marginTop: 6,
  },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: FONTS.md },
  emptyText: { fontSize: FONTS.md, color: COLORS.textSecondary, textAlign: "center" },
  note: { fontSize: FONTS.xs, color: COLORS.textMuted, textAlign: "center", marginTop: 18, lineHeight: 18 },
});
