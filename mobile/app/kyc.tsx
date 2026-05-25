import { useRef, useState, useCallback } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform,
  TextInput as RNTextInput, Animated,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { submitKYC } from "../api/auth";
import { COLORS, FONTS, RADIUS } from "../constants/theme";

// ── Static data ───────────────────────────────────────────────────────────────

const COUNTIES = [
  'Baringo','Bomet','Bungoma','Busia','Elgeyo-Marakwet','Embu','Garissa',
  'Homa Bay','Isiolo','Kajiado','Kakamega','Kericho','Kiambu','Kilifi',
  'Kirinyaga','Kisii','Kisumu','Kitui','Kwale','Laikipia','Lamu','Machakos',
  'Makueni','Mandera','Marsabit','Meru','Migori','Mombasa',"Murang'a",
  'Nairobi','Nakuru','Nandi','Narok','Nyamira','Nyandarua','Nyeri','Samburu',
  'Siaya','Taita-Taveta','Tana River','Tharaka-Nithi','Trans Nzoia','Turkana',
  'Uasin Gishu','Vihiga','Wajir','West Pokot',
];

const INCOME_SOURCES = [
  { value: 'employment',  label: 'Employment / Salary' },
  { value: 'business',    label: 'Business / Self-employment' },
  { value: 'investment',  label: 'Investment Returns' },
  { value: 'pension',     label: 'Pension / Retirement' },
  { value: 'rental',      label: 'Rental Income' },
  { value: 'remittance',  label: 'Remittance from Abroad' },
  { value: 'farming',     label: 'Farming / Agriculture' },
  { value: 'other',       label: 'Other' },
];

const INCOME_BANDS = [
  { value: 'under_250k', label: 'Up to KES 250,000 / month' },
  { value: '250k_to_1m', label: 'KES 250,001 – 1,000,000 / month' },
  { value: 'above_1m',   label: 'Above KES 1,000,000 / month' },
];

const TOTAL_STEPS = 5;

// ── Reusable sub-components (defined OUTSIDE the screen to keep identity stable) ──

type FieldProps = { label: string; children: React.ReactNode };
function Field({ label, children }: FieldProps) {
  return (
    <View style={s.fieldGroup}>
      <Text style={s.label}>{label}</Text>
      {children}
    </View>
  );
}

type ChipGroupProps = {
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (v: string) => void;
};
function ChipGroup({ options, selected, onSelect }: ChipGroupProps) {
  return (
    <View style={s.chipRow}>
      {options.map(o => (
        <TouchableOpacity
          key={o.value}
          style={[s.chip, selected === o.value && s.chipSelected]}
          onPress={() => onSelect(o.value)}
        >
          <Text style={[s.chipText, selected === o.value && s.chipTextSelected]}>
            {o.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

type PhotoAsset = { uri: string; name: string; type: string } | null;

// ── Screen ────────────────────────────────────────────────────────────────────

export default function KYCScreen() {
  const [step, setStep] = useState(1);
  const fadeAnim = useRef(new Animated.Value(1)).current;

  const goToStep = useCallback((next: number) => {
    Animated.timing(fadeAnim, {
      toValue: 0, duration: 150, useNativeDriver: true,
    }).start(() => {
      setStep(next);
      Animated.timing(fadeAnim, {
        toValue: 1, duration: 200, useNativeDriver: true,
      }).start();
    });
  }, [fadeAnim]);

  // Step 1
  const [givenNames, setGivenNames] = useState("");
  const [surname,    setSurname]    = useState("");
  const [idNumber,   setIdNumber]   = useState("");
  const [dobDay,     setDobDay]     = useState("");
  const [dobMonth,   setDobMonth]   = useState("");
  const [dobYear,    setDobYear]    = useState("");
  const [email,      setEmail]      = useState("");

  // Step 2
  const [idFront, setIdFront] = useState<PhotoAsset>(null);
  const [idBack,  setIdBack]  = useState<PhotoAsset>(null);

  // Step 3
  const [county,           setCounty]           = useState("");
  const [subCounty,        setSubCounty]        = useState("");
  const [showCountyPicker, setShowCountyPicker] = useState(false);

  // Step 4
  const [occupation,   setOccupation]   = useState("");
  const [incomeSource, setIncomeSource] = useState("");
  const [incomeBand,   setIncomeBand]   = useState("");

  // Step 5
  const [referralCode, setReferralCode] = useState("");

  const [error,   setError]   = useState("");
  const [loading, setLoading] = useState(false);

  const monthRef = useRef<RNTextInput>(null);
  const yearRef  = useRef<RNTextInput>(null);

  // ── Photo picker ────────────────────────────────────────────────────────────

  const pickPhoto = async (side: "front" | "back") => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
      allowsEditing: true,
    });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    const photo: PhotoAsset = {
      uri:  asset.uri,
      name: `id_${side}_${Date.now()}.jpg`,
      type: "image/jpeg",
    };
    if (side === "front") setIdFront(photo);
    else                  setIdBack(photo);
  };

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const dobString = () =>
    `${dobYear.padStart(4, "0")}-${dobMonth.padStart(2, "0")}-${dobDay.padStart(2, "0")}`;

  const isDobFormatValid = () => {
    const day   = parseInt(dobDay,   10);
    const month = parseInt(dobMonth, 10);
    const year  = parseInt(dobYear,  10);
    if (!dobDay || !dobMonth || !dobYear) return false;
    if (isNaN(day)   || day   < 1 || day   > 31) return false;
    if (isNaN(month) || month < 1 || month > 12) return false;
    if (isNaN(year)  || dobYear.length !== 4 || year < 1900 || year > new Date().getFullYear()) return false;
    return true;
  };

  const isAgeAtLeast18 = () => {
    const dob   = new Date(parseInt(dobYear, 10), parseInt(dobMonth, 10) - 1, parseInt(dobDay, 10));
    const today = new Date();
    const cutoff = new Date(dob);
    cutoff.setFullYear(cutoff.getFullYear() + 18);
    return cutoff <= today;
  };

  const validate = (): string | null => {
    if (step === 1) {
      if (!givenNames.trim())   return "Given names are required.";
      if (!surname.trim())      return "Surname is required.";
      if (!idNumber.trim())     return "ID number is required.";
      if (!isDobFormatValid())  return "Please enter a valid date of birth.";
      if (!isAgeAtLeast18())    return "You must be at least 18 years old to register.";
    }
    if (step === 2 && !idFront)      return "A photo of the front of your ID is required.";
    if (step === 3 && !county)       return "Please select your county.";
    if (step === 4) {
      if (!occupation.trim()) return "Occupation is required.";
      if (!incomeSource)      return "Please select your source of income.";
      if (!incomeBand)        return "Please select your income band.";
    }
    return null;
  };

  const handleNext = () => {
    const err = validate();
    if (err) { setError(err); return; }
    setError("");
    goToStep(step + 1);
  };

  const handleSubmit = async () => {
    const err = validate();
    if (err) { setError(err); return; }
    setError("");
    setLoading(true);

    const form = new FormData();
    form.append("given_names",             givenNames.trim());
    form.append("surname",                 surname.trim());
    form.append("id_number",               idNumber.trim());
    form.append("date_of_birth",           dobString());
    form.append("email",                   email.trim());
    form.append("county",                  county);
    form.append("sub_county",              subCounty.trim());
    form.append("occupation",              occupation.trim());
    form.append("source_of_income",        incomeSource);
    form.append("expected_monthly_income", incomeBand);
    form.append("referral_code",           referralCode.trim());
    // @ts-ignore — RN FormData accepts file objects
    form.append("id_front", idFront as any);
    if (idBack) form.append("id_back", idBack as any);

    try {
      await submitKYC(form);
      router.replace("/(drawer)/index");
    } catch (e: any) {
      const data = e?.response?.data;
      setError(
        typeof data === "object"
          ? Object.values(data).flat().join(" ")
          : "Submission failed. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  // ── Step content ─────────────────────────────────────────────────────────────

  const renderStep = () => {
    switch (step) {

      case 1:
        return (
          <>
            <Text style={s.title}>Personal Information</Text>
            <Text style={s.subtitle}>As it appears on your national ID.</Text>

            <Field label="Given Names">
              <TextInput
                style={s.input}
                value={givenNames}
                onChangeText={t => { setGivenNames(t); setError(""); }}
                placeholder="e.g. Jane Wanjiku"
                placeholderTextColor={COLORS.textMuted}
                autoCapitalize="words"
                autoFocus
              />
            </Field>

            <Field label="Surname">
              <TextInput
                style={s.input}
                value={surname}
                onChangeText={t => { setSurname(t); setError(""); }}
                placeholder="e.g. Kamau"
                placeholderTextColor={COLORS.textMuted}
                autoCapitalize="words"
              />
            </Field>

            <Field label="ID Number">
              <TextInput
                style={s.input}
                value={idNumber}
                onChangeText={t => { setIdNumber(t); setError(""); }}
                placeholder="e.g. 12345678"
                placeholderTextColor={COLORS.textMuted}
                keyboardType="numeric"
              />
            </Field>

            <Field label="Date of Birth">
              <View style={s.dobRow}>
                <View style={s.dobCell}>
                  <Text style={s.dobHint}>DD</Text>
                  <TextInput
                    style={[s.input, s.dobInput]}
                    value={dobDay}
                    onChangeText={t => {
                      const v = t.replace(/[^0-9]/g, "").slice(0, 2);
                      setDobDay(v);
                      setError("");
                      if (v.length === 2) monthRef.current?.focus();
                    }}
                    placeholder="DD"
                    placeholderTextColor={COLORS.textMuted}
                    keyboardType="numeric"
                    maxLength={2}
                  />
                </View>
                <Text style={s.dobSep}>/</Text>
                <View style={s.dobCell}>
                  <Text style={s.dobHint}>MM</Text>
                  <TextInput
                    ref={monthRef}
                    style={[s.input, s.dobInput]}
                    value={dobMonth}
                    onChangeText={t => {
                      const v = t.replace(/[^0-9]/g, "").slice(0, 2);
                      setDobMonth(v);
                      setError("");
                      if (v.length === 2) yearRef.current?.focus();
                    }}
                    placeholder="MM"
                    placeholderTextColor={COLORS.textMuted}
                    keyboardType="numeric"
                    maxLength={2}
                  />
                </View>
                <Text style={s.dobSep}>/</Text>
                <View style={[s.dobCell, s.dobCellYear]}>
                  <Text style={s.dobHint}>YYYY</Text>
                  <TextInput
                    ref={yearRef}
                    style={[s.input, s.dobInput]}
                    value={dobYear}
                    onChangeText={t => {
                      const v = t.replace(/[^0-9]/g, "").slice(0, 4);
                      setDobYear(v);
                      setError("");
                    }}
                    placeholder="YYYY"
                    placeholderTextColor={COLORS.textMuted}
                    keyboardType="numeric"
                    maxLength={4}
                  />
                </View>
              </View>
            </Field>

            <Field label="Email Address (optional)">
              <TextInput
                style={s.input}
                value={email}
                onChangeText={t => { setEmail(t); setError(""); }}
                placeholder="e.g. jane@example.com"
                placeholderTextColor={COLORS.textMuted}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </Field>
          </>
        );

      case 2:
        return (
          <>
            <Text style={s.title}>ID Document Scans</Text>
            <Text style={s.subtitle}>Take clear photos of both sides of your national ID.</Text>

            <Field label="Front of ID">
              <TouchableOpacity style={s.photoBox} onPress={() => pickPhoto("front")}>
                {idFront
                  ? <Image source={{ uri: idFront.uri }} style={s.photoPreview} contentFit="cover" />
                  : <Text style={s.photoPrompt}>📷  Tap to upload front</Text>}
              </TouchableOpacity>
            </Field>

            <Field label="Back of ID (optional)">
              <TouchableOpacity style={s.photoBox} onPress={() => pickPhoto("back")}>
                {idBack
                  ? <Image source={{ uri: idBack.uri }} style={s.photoPreview} contentFit="cover" />
                  : <Text style={s.photoPrompt}>📷  Tap to upload back</Text>}
              </TouchableOpacity>
            </Field>
          </>
        );

      case 3:
        return (
          <>
            <Text style={s.title}>Address</Text>
            <Text style={s.subtitle}>Your county of residence.</Text>

            <Field label="County">
              <TouchableOpacity
                style={s.input}
                onPress={() => setShowCountyPicker(p => !p)}
              >
                <Text style={{ color: county ? COLORS.text : COLORS.textMuted }}>
                  {county || "Select county…"}
                </Text>
              </TouchableOpacity>
              {showCountyPicker && (
                <ScrollView style={s.dropdown} nestedScrollEnabled>
                  {COUNTIES.map(c => (
                    <TouchableOpacity
                      key={c}
                      style={s.dropdownItem}
                      onPress={() => { setCounty(c); setShowCountyPicker(false); setError(""); }}
                    >
                      <Text style={s.dropdownText}>{c}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              )}
            </Field>

            <Field label="Sub-county / Area (optional)">
              <TextInput
                style={s.input}
                value={subCounty}
                onChangeText={setSubCounty}
                placeholder="e.g. Westlands"
                placeholderTextColor={COLORS.textMuted}
              />
            </Field>
          </>
        );

      case 4:
        return (
          <>
            <Text style={s.title}>Financial Profile</Text>
            <Text style={s.subtitle}>Required for regulatory compliance.</Text>

            <Field label="Occupation">
              <TextInput
                style={s.input}
                value={occupation}
                onChangeText={t => { setOccupation(t); setError(""); }}
                placeholder="e.g. Software Engineer"
                placeholderTextColor={COLORS.textMuted}
                autoCapitalize="words"
              />
            </Field>

            <Field label="Source of Income">
              <ChipGroup
                options={INCOME_SOURCES}
                selected={incomeSource}
                onSelect={v => { setIncomeSource(v); setError(""); }}
              />
            </Field>

            <Field label="Expected Monthly Income">
              <ChipGroup
                options={INCOME_BANDS}
                selected={incomeBand}
                onSelect={v => { setIncomeBand(v); setError(""); }}
              />
            </Field>
          </>
        );

      case 5:
        return (
          <>
            <Text style={s.title}>Almost done!</Text>
            <Text style={s.subtitle}>
              Got a referral or sales code? Add it below — otherwise tap Submit.
            </Text>

            <Field label="Referral / Sales Code (optional)">
              <TextInput
                style={s.input}
                value={referralCode}
                onChangeText={setReferralCode}
                placeholder="e.g. WEPL2026"
                placeholderTextColor={COLORS.textMuted}
                autoCapitalize="characters"
              />
            </Field>

            <View style={s.reviewBox}>
              <Text style={s.reviewTitle}>Your submission summary</Text>
              <Text style={s.reviewRow}>Given Names: <Text style={s.reviewVal}>{givenNames}</Text></Text>
              <Text style={s.reviewRow}>Surname:     <Text style={s.reviewVal}>{surname}</Text></Text>
              <Text style={s.reviewRow}>ID No:       <Text style={s.reviewVal}>{idNumber}</Text></Text>
              <Text style={s.reviewRow}>DOB:         <Text style={s.reviewVal}>{dobDay} / {dobMonth} / {dobYear}</Text></Text>
              <Text style={s.reviewRow}>County:      <Text style={s.reviewVal}>{county}</Text></Text>
              <Text style={s.reviewRow}>Income:      <Text style={s.reviewVal}>
                {INCOME_BANDS.find(b => b.value === incomeBand)?.label ?? "—"}
              </Text></Text>
            </View>
          </>
        );

      default:
        return null;
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 24}
      >
        <ScrollView
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Progress bar */}
          <View style={s.progressRow}>
            {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
              <View key={i} style={[s.progressDot, i + 1 <= step && s.progressDotActive]} />
            ))}
          </View>

          <Animated.View style={{ opacity: fadeAnim }}>
            <Text style={s.stepLabel}>Step {step} of {TOTAL_STEPS}</Text>

            {renderStep()}

          {error ? <Text style={s.error}>{error}</Text> : null}
          </Animated.View>

          <View style={s.navRow}>
            {step > 1 && (
              <TouchableOpacity
                style={s.backBtn}
                onPress={() => { setError(""); goToStep(step - 1); }}
              >
                <Text style={s.backBtnText}>← Back</Text>
              </TouchableOpacity>
            )}

            {step < TOTAL_STEPS ? (
              <TouchableOpacity
                style={[s.nextBtn, step === 1 && s.nextBtnFull]}
                onPress={handleNext}
              >
                <Text style={s.nextBtnText}>Continue →</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                style={[s.nextBtn, loading && s.nextBtnDisabled]}
                onPress={handleSubmit}
                disabled={loading}
              >
                {loading
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={s.nextBtnText}>Submit KYC</Text>}
              </TouchableOpacity>
            )}
          </View>

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:  { flex: 1, backgroundColor: COLORS.background },
  flex:  { flex: 1 },
  scroll:{ padding: 24, paddingBottom: 48 },

  progressRow:       { flexDirection: "row", gap: 6, marginBottom: 8 },
  progressDot:       { flex: 1, height: 4, borderRadius: 2, backgroundColor: COLORS.border },
  progressDotActive: { backgroundColor: COLORS.primary },

  stepLabel: { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 20 },

  title:    { fontSize: FONTS.xxl, fontWeight: "700", color: COLORS.text, marginBottom: 6 },
  subtitle: { fontSize: FONTS.md,  color: COLORS.textSecondary, marginBottom: 24, lineHeight: 22 },

  fieldGroup: { marginBottom: 20 },
  label: {
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 14, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.white,
  },

  dobRow:     { flexDirection: "row", alignItems: "flex-end", gap: 8 },
  dobCell:    { flex: 1 },
  dobCellYear:{ flex: 2 },
  dobHint:    { fontSize: 11, color: COLORS.textMuted, marginBottom: 4, textAlign: "center" },
  dobInput:   { textAlign: "center", padding: 12 },
  dobSep:     { fontSize: 20, color: COLORS.textMuted, marginBottom: 14 },

  photoBox: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    height: 160, justifyContent: "center", alignItems: "center",
    backgroundColor: COLORS.white, overflow: "hidden",
  },
  photoPreview: { width: "100%", height: "100%" },
  photoPrompt:  { fontSize: FONTS.md, color: COLORS.textMuted },

  dropdown: {
    maxHeight: 220, borderWidth: 1, borderColor: COLORS.border,
    borderRadius: RADIUS.md, backgroundColor: COLORS.white, marginTop: 4,
  },
  dropdownItem: { padding: 12, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  dropdownText: { fontSize: FONTS.md, color: COLORS.text },

  chipRow:          { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip:             { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.white },
  chipSelected:     { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText:         { fontSize: FONTS.sm, color: COLORS.text },
  chipTextSelected: { color: COLORS.white, fontWeight: "600" },

  reviewBox: {
    backgroundColor: COLORS.white, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.border,
    padding: 16, marginTop: 8, gap: 6,
  },
  reviewTitle: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, marginBottom: 8 },
  reviewRow:   { fontSize: FONTS.sm, color: COLORS.textSecondary },
  reviewVal:   { color: COLORS.text, fontWeight: "600" },

  error: { color: COLORS.error, fontSize: FONTS.sm, marginTop: 8, marginBottom: 4 },

  navRow:  { flexDirection: "row", gap: 12, marginTop: 28 },
  backBtn: {
    flex: 1, padding: 16, borderRadius: RADIUS.md,
    borderWidth: 1.5, borderColor: COLORS.border,
    alignItems: "center", backgroundColor: COLORS.white,
  },
  backBtnText:     { color: COLORS.text, fontWeight: "600", fontSize: FONTS.md },
  nextBtn:         { flex: 2, backgroundColor: COLORS.primary, padding: 16, borderRadius: RADIUS.md, alignItems: "center" },
  nextBtnFull:     { flex: 1 },
  nextBtnDisabled: { opacity: 0.6 },
  nextBtnText:     { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
});
