import { useRef, useState, useCallback } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform,
  TextInput as RNTextInput, Animated, Modal, Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { suppressNextLock } from "../utils/lockSuppress";
import DateTimePicker from "@react-native-community/datetimepicker";
import { Image } from "expo-image";
import { submitKYC } from "../api/auth";
import API from "../api/client";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import { Ionicons } from "@expo/vector-icons";

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

const PROFESSIONS = [
  { value: 'accountant',       label: 'Accountant / Finance' },
  { value: 'agriculture',      label: 'Agriculture / Farming' },
  { value: 'architecture',     label: 'Architecture / Design' },
  { value: 'business_owner',   label: 'Business Owner / Entrepreneur' },
  { value: 'casual_labour',    label: 'Casual Labourer' },
  { value: 'construction',     label: 'Construction / Engineering' },
  { value: 'customer_service', label: 'Customer Service' },
  { value: 'doctor',           label: 'Doctor / Medical' },
  { value: 'driver',           label: 'Driver / Transport' },
  { value: 'education',        label: 'Education / Teaching' },
  { value: 'freelancer',       label: 'Freelancer / Consultant' },
  { value: 'government',       label: 'Government Employee' },
  { value: 'hospitality',      label: 'Hospitality / Tourism' },
  { value: 'it',               label: 'IT / Technology' },
  { value: 'journalism',       label: 'Journalist / Media' },
  { value: 'legal',            label: 'Lawyer / Legal' },
  { value: 'manufacturing',    label: 'Manufacturing / Production' },
  { value: 'ngo',              label: 'NGO / Non-profit' },
  { value: 'nurse',            label: 'Nurse / Healthcare' },
  { value: 'police_security',  label: 'Police / Security' },
  { value: 'real_estate',      label: 'Real Estate' },
  { value: 'retail_sales',     label: 'Retail / Sales' },
  { value: 'student',          label: 'Student' },
  { value: 'other',            label: 'Other' },
];

const INCOME_SOURCES = [
  { value: 'employment',  label: '💼  Employment / Salary' },
  { value: 'business',    label: '🏪  Business / Self-employment' },
  { value: 'investment',  label: '📈  Investment Returns' },
  { value: 'pension',     label: '🏦  Pension / Retirement' },
  { value: 'rental',      label: '🏠  Rental Income' },
  { value: 'remittance',  label: '✈️  Remittance from Abroad' },
  { value: 'farming',     label: '🌾  Farming / Agriculture' },
  { value: 'other',       label: '•••  Other' },
];

const INCOME_BANDS = [
  { value: 'under_250k', label: 'Up to KES 250,000 / month' },
  { value: '250k_to_1m', label: 'KES 250,001 – 1,000,000 / month' },
  { value: 'above_1m',   label: 'Above KES 1,000,000 / month' },
];

const TOTAL_STEPS = 5;

// ── Reusable sub-components (defined OUTSIDE the screen to keep identity stable) ──

type FieldProps = { label: string; hint?: string; children: React.ReactNode };
function Field({ label, hint, children }: FieldProps) {
  return (
    <View style={s.fieldGroup}>
      <Text style={s.label}>{label}</Text>
      {hint ? <Text style={s.fieldHint}>{hint}</Text> : null}
      {children}
    </View>
  );
}

/** Vertical radio-button list — cleaner than chips for longer or multi-word options */
type RadioListProps = {
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (v: string) => void;
};
function RadioList({ options, selected, onSelect }: RadioListProps) {
  return (
    <View style={s.radioList}>
      {options.map((o, i) => {
        const active = selected === o.value;
        return (
          <TouchableOpacity
            key={o.value}
            style={[
              s.radioRow,
              active && s.radioRowActive,
              i === options.length - 1 && { borderBottomWidth: 0 },
            ]}
            onPress={() => onSelect(o.value)}
            activeOpacity={0.7}
          >
            <Text style={[s.radioLabel, active && s.radioLabelActive]}>{o.label}</Text>
            <View style={[s.radioCircle, active && s.radioCircleActive]}>
              {active && <View style={s.radioDot} />}
            </View>
          </TouchableOpacity>
        );
      })}
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
      // Reset the photo sub-flow when navigating to or from step 2
      if (next === 2) setPhotoSubStep("intro");
      Animated.timing(fadeAnim, {
        toValue: 1, duration: 200, useNativeDriver: true,
      }).start();
    });
  }, [fadeAnim]);

  // Step 1
  const [givenNames, setGivenNames] = useState("");
  const [surname,    setSurname]    = useState("");
  const [idNumber,        setIdNumber]        = useState("");
  const [kraPin,          setKraPin]          = useState("");
  const [idCheckState,    setIdCheckState]    = useState<"idle" | "checking" | "taken" | "ok">("idle");
  const [emailCheckState, setEmailCheckState] = useState<"idle" | "checking" | "warn" | "ok">("idle");
  const [emailWarning,    setEmailWarning]    = useState("");
  // Date of birth — stored as a Date object, formatted to string on submit
  const [dob,        setDob]        = useState<Date | null>(null);
  const [showDobPicker, setShowDobPicker] = useState(false);

  // Max selectable date: must be ≥ 18 years old
  const maxDob = new Date();
  maxDob.setFullYear(maxDob.getFullYear() - 18);
  const [email,      setEmail]      = useState("");

  // Step 2 — photo capture sub-flow
  // "intro" → "id_front" → "id_back" → "selfie" → (continues to step 3)
  type PhotoSubStep = "intro" | "id_front" | "id_back" | "selfie";
  const [photoSubStep, setPhotoSubStep] = useState<PhotoSubStep>("intro");
  const [idFront,      setIdFront]      = useState<PhotoAsset>(null);
  const [idBack,       setIdBack]       = useState<PhotoAsset>(null);
  const [selfie,       setSelfie]       = useState<PhotoAsset>(null);

  // Step 3
  const [county,              setCounty]              = useState("");
  const [physicalAddress,     setPhysicalAddress]     = useState("");
  const [showCountyPicker,    setShowCountyPicker]    = useState(false);
  const [showProfessionPicker, setShowProfessionPicker] = useState(false);

  // Step 4
  const [occupation,   setOccupation]   = useState("");
  const [incomeSource, setIncomeSource] = useState("");
  const [incomeBand,   setIncomeBand]   = useState("");

  // Step 5
  const [referralCode, setReferralCode] = useState("");

  const [error,        setError]       = useState("");
  const [loading,      setLoading]     = useState(false);
  const [submitted,    setSubmitted]   = useState(false);  // show "check your email" screen
  const [submittedEmail, setSubmittedEmail] = useState("");

  const monthRef = useRef<RNTextInput>(null);  // kept for other fields
  const yearRef  = useRef<RNTextInput>(null);  // kept for other fields

  // ── Camera capture ───────────────────────────────────────────────────────────
  // In development: manual review.
  // In production: integrate a third-party liveness/OCR SDK here.

  const capturePhoto = async (target: "id_front" | "id_back" | "selfie") => {
    // Request camera permission
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Camera access needed",
        "Please allow camera access in your device settings to scan your documents.",
      );
      return;
    }

    suppressNextLock();
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes:   ["images"],
      quality:      0.85,
      allowsEditing: true,
      aspect:       target === "selfie" ? [1, 1] : [4, 3],
      cameraType:   target === "selfie"
        ? ImagePicker.CameraType.front
        : ImagePicker.CameraType.back,
    });

    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    const photo: PhotoAsset = {
      uri:  asset.uri,
      name: `${target}_${Date.now()}.jpg`,
      type: "image/jpeg",
    };

    if (target === "id_front")  { setIdFront(photo);  setPhotoSubStep("id_back"); }
    else if (target === "id_back")   { setIdBack(photo);   setPhotoSubStep("selfie"); }
    else if (target === "selfie")    { setSelfie(photo); }
  };

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const dobString = () => {
    if (!dob) return "";
    const y = dob.getFullYear();
    const m = String(dob.getMonth() + 1).padStart(2, "0");
    const d = String(dob.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  };

  const dobDisplayString = () => {
    if (!dob) return "";
    return dob.toLocaleDateString("en-KE", {
      day: "2-digit", month: "long", year: "numeric",
    });
  };

  /** Check ID availability once — called on blur (when user leaves the field).
   *  One API call per field interaction, not per keystroke.
   *  The backend unique constraint is the authoritative safeguard;
   *  this is purely a UX hint to surface duplicates before the final submit.
   */
  const checkIdAvailability = async () => {
    const trimmed = idNumber.trim();
    if (trimmed.length < 4) return;   // too short to be a valid ID — skip

    setIdCheckState("checking");
    try {
      const res = await API.get(`users/kyc/check-id/?id_number=${encodeURIComponent(trimmed)}`);
      setIdCheckState(res.data.available ? "ok" : "taken");
      if (!res.data.available) setError(res.data.message);
    } catch {
      setIdCheckState("idle");   // network error — silently skip, backend validates on submit
    }
  };

  const handleIdNumberChange = (text: string) => {
    setIdNumber(text);
    setError("");
    setIdCheckState("idle");
  };

  /** Soft email availability check — warns but never blocks. */
  const checkEmailAvailability = async () => {
    const trimmed = email.trim();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) return;

    setEmailCheckState("checking");
    setEmailWarning("");
    try {
      const res = await API.get(`users/kyc/check-email/?email=${encodeURIComponent(trimmed)}`);
      if (!res.data.available) {
        setEmailCheckState("warn");
        setEmailWarning(res.data.message);
      } else {
        setEmailCheckState("ok");
      }
    } catch {
      setEmailCheckState("idle");
    }
  };

  const handleEmailChange = (text: string) => {
    setEmail(text);
    setError("");
    setEmailCheckState("idle");
    setEmailWarning("");
  };

  const isDobFormatValid = () => {
    if (!dob) return false;
    const year = dob.getFullYear();
    return year >= 1900 && year <= new Date().getFullYear();
  };

  const isAgeAtLeast18 = () => {
    if (!dob) return false;
    const cutoff = new Date(dob);
    cutoff.setFullYear(cutoff.getFullYear() + 18);
    return cutoff <= new Date();
  };

  const validate = (): string | null => {
    if (step === 1) {
      if (!givenNames.trim())   return "Given names are required.";
      if (!surname.trim())      return "Surname is required.";
      if (!idNumber.trim())     return "ID number is required.";
      if (idCheckState === "taken")    return "This ID number is already registered to another account.";
      if (idCheckState === "checking") return "Checking ID number availability…";
      if (!kraPin.trim())       return "KRA PIN is required.";
      if (!/^[A-Z]\d{9}[A-Z]$/.test(kraPin.trim().toUpperCase()))
                                return "Enter a valid KRA PIN (e.g. A012345678Z).";
      if (!isDobFormatValid())  return "Please enter a valid date of birth.";
      if (!isAgeAtLeast18())    return "You must be at least 18 years old to register.";
      if (!email.trim())        return "Email address is required.";
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
                                return "Please enter a valid email address.";
    }
    if (step === 2) {
      if (!idFront) return "A photo of the front of your ID is required.";
      if (!idBack)  return "A photo of the back of your ID is required.";
      if (!selfie)  return "A selfie photo is required to verify your identity.";
    }
    if (step === 3) {
      if (!county)                    return "Please select your county.";
      if (!physicalAddress.trim())    return "Physical address is required.";
    }
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

    // Step 1 — if the email check returned a warning, ask the user to
    // explicitly confirm before continuing. They can't accidentally skip it.
    if (step === 1 && emailCheckState === "warn") {
      Alert.alert(
        "Email already in use",
        `${email.trim()} is linked to another account.\n\nAre you sure this is your email? Verification emails and KYC updates will be sent here.`,
        [
          {
            text:  "Change email",
            style: "cancel",
            // Put focus back on the email field — user wants to edit it
          },
          {
            text:  "Yes, it's mine — continue",
            style: "default",
            onPress: () => {
              setEmailCheckState("ok");   // acknowledged — clear warning
              setEmailWarning("");
              setError("");
              goToStep(step + 1);
            },
          },
        ],
        { cancelable: false }
      );
      return;   // don't advance until user responds
    }

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
    form.append("kra_pin",                  kraPin.trim().toUpperCase());
    form.append("date_of_birth",           dobString());
    form.append("email",                   email.trim());
    form.append("county",                  county);
    form.append("physical_address",        physicalAddress.trim());
    // Send human-readable profession label, not the internal value key
    const professionLabel = PROFESSIONS.find(p => p.value === occupation)?.label ?? occupation;
    form.append("occupation",              professionLabel);
    form.append("source_of_income",        incomeSource);
    form.append("expected_monthly_income", incomeBand);
    form.append("referral_code",           referralCode.trim());
    // @ts-ignore — RN FormData accepts file objects
    form.append("id_front", idFront as any);
    if (idBack)  form.append("id_back",  idBack  as any);
    if (selfie)  form.append("selfie",   selfie  as any);

    try {
      await submitKYC(form);
      // Show the "check your email" confirmation screen.
      setSubmittedEmail(email.trim());
      setSubmitted(true);
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
              <View style={s.idRow}>
                <TextInput
                  style={[
                    s.input, s.idInput,
                    idCheckState === "taken" && s.inputError,
                    idCheckState === "ok"    && s.inputOk,
                  ]}
                  value={idNumber}
                  onChangeText={handleIdNumberChange}
                  onBlur={checkIdAvailability}
                  placeholder="e.g. 12345678"
                  placeholderTextColor={COLORS.textMuted}
                  keyboardType="numeric"
                  returnKeyType="next"
                />
                <View style={s.idStatus}>
                  {idCheckState === "checking" && (
                    <ActivityIndicator size="small" color={COLORS.primary} />
                  )}
                  {idCheckState === "ok" && (
                    <Ionicons name="checkmark-circle" size={20} color={COLORS.success} />
                  )}
                  {idCheckState === "taken" && (
                    <Ionicons name="close-circle" size={20} color={COLORS.error} />
                  )}
                </View>
              </View>
              {idCheckState === "taken" && (
                <Text style={s.idErrorText}>
                  This ID number is already registered to another account.
                </Text>
              )}
            </Field>

            <Field label="KRA PIN">
              <TextInput
                style={s.input}
                value={kraPin}
                onChangeText={(t) => setKraPin(t.toUpperCase())}
                placeholder="e.g. A012345678Z"
                placeholderTextColor={COLORS.textMuted}
                autoCapitalize="characters"
                autoCorrect={false}
                maxLength={11}
                returnKeyType="next"
              />
            </Field>

            <Field label="Date of Birth">
              {/* Tappable row that opens the date picker */}
              <TouchableOpacity
                style={s.dobTrigger}
                onPress={() => setShowDobPicker(true)}
                activeOpacity={0.7}
              >
                <Ionicons name="calendar-outline" size={18} color={COLORS.primary} />
                <Text style={[s.dobTriggerText, !dob && { color: COLORS.textMuted }]}>
                  {dob ? dobDisplayString() : "Select your date of birth"}
                </Text>
                <Ionicons name="chevron-down" size={16} color={COLORS.textMuted} />
              </TouchableOpacity>

              {/* Date picker — inline on iOS, modal on Android */}
              {Platform.OS === "ios" ? (
                showDobPicker && (
                  <Modal
                    visible={showDobPicker}
                    transparent
                    animationType="slide"
                    onRequestClose={() => setShowDobPicker(false)}
                  >
                    <View style={s.dobModalBackdrop}>
                      <View style={s.dobModalSheet}>
                        <View style={s.dobModalHeader}>
                          <TouchableOpacity onPress={() => setShowDobPicker(false)}>
                            <Text style={s.dobModalCancel}>Cancel</Text>
                          </TouchableOpacity>
                          <Text style={s.dobModalTitle}>Date of Birth</Text>
                          <TouchableOpacity onPress={() => setShowDobPicker(false)}>
                            <Text style={s.dobModalDone}>Done</Text>
                          </TouchableOpacity>
                        </View>
                        <DateTimePicker
                          value={dob ?? maxDob}
                          mode="date"
                          display="spinner"
                          maximumDate={maxDob}
                          minimumDate={new Date(1900, 0, 1)}
                          onChange={(_, selected) => {
                            if (selected) { setDob(selected); setError(""); }
                          }}
                          textColor={COLORS.text}
                        />
                      </View>
                    </View>
                  </Modal>
                )
              ) : (
                showDobPicker && (
                  <DateTimePicker
                    value={dob ?? maxDob}
                    mode="date"
                    display="default"
                    maximumDate={maxDob}
                    minimumDate={new Date(1900, 0, 1)}
                    onChange={(_, selected) => {
                      setShowDobPicker(false);
                      if (selected) { setDob(selected); setError(""); }
                    }}
                  />
                )
              )}
            </Field>

            <Field
              label="Email Address"
              hint="A verification link will be sent to this address"
            >
              <View style={s.idRow}>
                <TextInput
                  style={[
                    s.input, s.idInput,
                    emailCheckState === "warn" && s.inputWarn,
                    emailCheckState === "ok"   && s.inputOk,
                  ]}
                  value={email}
                  onChangeText={handleEmailChange}
                  onBlur={checkEmailAvailability}
                  placeholder="e.g. jane@example.com"
                  placeholderTextColor={COLORS.textMuted}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                  returnKeyType="done"
                />
                <View style={s.idStatus}>
                  {emailCheckState === "checking" && (
                    <ActivityIndicator size="small" color={COLORS.primary} />
                  )}
                  {emailCheckState === "ok" && (
                    <Ionicons name="checkmark-circle" size={20} color={COLORS.success} />
                  )}
                  {emailCheckState === "warn" && (
                    <Ionicons name="warning" size={20} color={COLORS.warning} />
                  )}
                </View>
              </View>
              {/* Inline hint — brief. Full confirmation happens on Continue tap. */}
              {emailCheckState === "warn" && (
                <View style={s.emailWarnBox}>
                  <Ionicons name="warning-outline" size={15} color="#92400E" />
                  <Text style={s.emailWarnText}>
                    This email is linked to another account. Tap Continue to confirm it's yours.
                  </Text>
                </View>
              )}
            </Field>
          </>
        );

      case 2:
        // ── Photo capture sub-flow ─────────────────────────────────────────
        // intro → id_front → id_back → selfie

        if (photoSubStep === "intro") {
          return (
            <>
              <Text style={s.title}>Identity Verification</Text>

              <View style={s.introCard}>
                <Text style={s.introGreeting}>📸  Before we take your photos</Text>
                <Text style={s.introBody}>
                  To verify your identity we'll take three quick photos using your camera:
                </Text>

                <View style={s.introSteps}>
                  {[
                    { icon: "card-outline",     label: "Front of your national ID" },
                    { icon: "card",             label: "Back of your national ID" },
                    { icon: "person-circle-outline", label: "A selfie — photo of your face" },
                  ].map((item, i) => (
                    <View key={i} style={s.introStep}>
                      <View style={s.introStepNum}><Text style={s.introStepNumText}>{i + 1}</Text></View>
                      <Ionicons name={item.icon as any} size={20} color={COLORS.primary} />
                      <Text style={s.introStepLabel}>{item.label}</Text>
                    </View>
                  ))}
                </View>

                <View style={s.introTips}>
                  <Text style={s.introTipsTitle}>Tips for the best result:</Text>
                  {[
                    "Find a well-lit area — natural light works best",
                    "Avoid glare, shadows or reflections on your ID",
                    "Hold your phone steady and keep documents flat",
                    "Make sure all text on your ID is clearly readable",
                    "For your selfie, look directly at the camera",
                  ].map((tip, i) => (
                    <View key={i} style={s.introTip}>
                      <Text style={s.introTipBullet}>•</Text>
                      <Text style={s.introTipText}>{tip}</Text>
                    </View>
                  ))}
                </View>
              </View>

              <TouchableOpacity
                style={s.introCta}
                onPress={() => setPhotoSubStep("id_front")}
              >
                <Ionicons name="camera" size={18} color="#fff" />
                <Text style={s.introCtaText}>I'm ready — start scanning</Text>
              </TouchableOpacity>
            </>
          );
        }

        if (photoSubStep === "id_front") {
          return (
            <>
              <Text style={s.title}>Front of ID</Text>
              <Text style={s.subtitle}>Place your national ID on a flat surface and take a clear photo of the front.</Text>

              <TouchableOpacity
                style={[s.photoBox, idFront && s.photoBoxDone]}
                onPress={() => capturePhoto("id_front")}
                activeOpacity={0.8}
              >
                {idFront ? (
                  <>
                    <Image source={{ uri: idFront.uri }} style={s.photoPreview} contentFit="cover" />
                    <View style={s.photoRetakeOverlay}>
                      <Ionicons name="camera" size={20} color="#fff" />
                      <Text style={s.photoRetakeText}>Retake</Text>
                    </View>
                  </>
                ) : (
                  <View style={s.photoPromptWrap}>
                    <Ionicons name="camera-outline" size={40} color={COLORS.primary} />
                    <Text style={s.photoPromptText}>Tap to open camera</Text>
                    <Text style={s.photoPromptHint}>ID front side facing up</Text>
                  </View>
                )}
              </TouchableOpacity>

              {idFront && (
                <TouchableOpacity style={s.introCta} onPress={() => setPhotoSubStep("id_back")}>
                  <Text style={s.introCtaText}>Looks good — next photo →</Text>
                </TouchableOpacity>
              )}
            </>
          );
        }

        if (photoSubStep === "id_back") {
          return (
            <>
              <Text style={s.title}>Back of ID</Text>
              <Text style={s.subtitle}>Now flip your ID over and take a photo of the back. This is required.</Text>

              <TouchableOpacity
                style={[s.photoBox, idBack && s.photoBoxDone]}
                onPress={() => capturePhoto("id_back")}
                activeOpacity={0.8}
              >
                {idBack ? (
                  <>
                    <Image source={{ uri: idBack.uri }} style={s.photoPreview} contentFit="cover" />
                    <View style={s.photoRetakeOverlay}>
                      <Ionicons name="camera" size={20} color="#fff" />
                      <Text style={s.photoRetakeText}>Retake</Text>
                    </View>
                  </>
                ) : (
                  <View style={s.photoPromptWrap}>
                    <Ionicons name="camera-outline" size={40} color={COLORS.primary} />
                    <Text style={s.photoPromptText}>Tap to open camera</Text>
                    <Text style={s.photoPromptHint}>ID back side facing up</Text>
                  </View>
                )}
              </TouchableOpacity>

              {idBack && (
                <TouchableOpacity style={s.introCta} onPress={() => setPhotoSubStep("selfie")}>
                  <Text style={s.introCtaText}>Looks good — take selfie →</Text>
                </TouchableOpacity>
              )}
            </>
          );
        }

        // selfie sub-step
        return (
          <>
            <Text style={s.title}>Your Selfie</Text>
            <Text style={s.subtitle}>
              Look directly at the front camera with your face clearly visible.
              Good lighting makes a big difference!
            </Text>

            <TouchableOpacity
              style={[s.photoBox, s.selfieBox, selfie && s.photoBoxDone]}
              onPress={() => capturePhoto("selfie")}
              activeOpacity={0.8}
            >
              {selfie ? (
                <>
                  <Image source={{ uri: selfie.uri }} style={s.photoPreview} contentFit="cover" />
                  <View style={s.photoRetakeOverlay}>
                    <Ionicons name="camera" size={20} color="#fff" />
                    <Text style={s.photoRetakeText}>Retake</Text>
                  </View>
                </>
              ) : (
                <View style={s.photoPromptWrap}>
                  <Ionicons name="person-circle-outline" size={48} color={COLORS.primary} />
                  <Text style={s.photoPromptText}>Tap to take selfie</Text>
                  <Text style={s.photoPromptHint}>Front camera will open</Text>
                </View>
              )}
            </TouchableOpacity>

            {selfie && (
              <>
                <View style={s.selfieConfirm}>
                  <Ionicons name="checkmark-circle" size={18} color={COLORS.success} />
                  <Text style={s.selfieConfirmText}>Selfie captured — you're all set.</Text>
                </View>
                <TouchableOpacity style={s.introCta} onPress={handleNext}>
                  <Text style={s.introCtaText}>Continue →</Text>
                </TouchableOpacity>
              </>
            )}
          </>
        );

      case 3:
        return (
          <>
            <Text style={s.title}>Address</Text>
            <Text style={s.subtitle}>Your county and physical location of residence.</Text>

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

            <Field label="Physical Address">
              <TextInput
                style={[s.input, { height: 80, textAlignVertical: "top", paddingTop: 12 }]}
                value={physicalAddress}
                onChangeText={t => { setPhysicalAddress(t); setError(""); }}
                placeholder="e.g. 14 Ngong Road, Karen, Nairobi"
                placeholderTextColor={COLORS.textMuted}
                autoCapitalize="words"
                multiline
              />
            </Field>
          </>
        );

      case 4:
        return (
          <>
            <Text style={s.title}>Your Financial Profile</Text>
            <Text style={s.subtitle}>
              A few quick details so we can tailor your WEPL experience and
              offer you the right financial tools.
            </Text>

            {/* Profession — scrollable picker */}
            <Field label="Profession">
              <TouchableOpacity
                style={s.input}
                onPress={() => setShowProfessionPicker(p => !p)}
              >
                <Text style={{ color: occupation ? COLORS.text : COLORS.textMuted }}>
                  {occupation
                    ? (PROFESSIONS.find(p => p.value === occupation)?.label ?? occupation)
                    : "Select your profession…"}
                </Text>
              </TouchableOpacity>
              {showProfessionPicker && (
                <ScrollView style={s.dropdown} nestedScrollEnabled>
                  {PROFESSIONS.map(p => (
                    <TouchableOpacity
                      key={p.value}
                      style={[s.dropdownItem, occupation === p.value && s.dropdownItemActive]}
                      onPress={() => {
                        setOccupation(p.value);
                        setShowProfessionPicker(false);
                        setError("");
                      }}
                    >
                      <Text style={[s.dropdownText, occupation === p.value && { color: COLORS.primary, fontWeight: "700" }]}>
                        {p.label}
                      </Text>
                      {occupation === p.value && (
                        <Ionicons name="checkmark" size={16} color={COLORS.primary} />
                      )}
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              )}
            </Field>

            {/* Source of income — radio list */}
            <Field label="Source of Income">
              <RadioList
                options={INCOME_SOURCES}
                selected={incomeSource}
                onSelect={v => { setIncomeSource(v); setError(""); }}
              />
            </Field>

            {/* Expected monthly income — radio list */}
            <Field label="Expected Monthly Income">
              <RadioList
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
              <Text style={s.reviewRow}>Full Name:    <Text style={s.reviewVal}>{givenNames} {surname}</Text></Text>
              <Text style={s.reviewRow}>ID No:        <Text style={s.reviewVal}>{idNumber}</Text></Text>
              <Text style={s.reviewRow}>KRA PIN:      <Text style={s.reviewVal}>{kraPin}</Text></Text>
              <Text style={s.reviewRow}>Date of Birth:<Text style={s.reviewVal}> {dob ? dobDisplayString() : "—"}</Text></Text>
              <Text style={s.reviewRow}>Email:        <Text style={s.reviewVal}>{email}</Text></Text>
              <Text style={s.reviewRow}>County:       <Text style={s.reviewVal}>{county}</Text></Text>
              <Text style={s.reviewRow}>Address:      <Text style={s.reviewVal}>{physicalAddress}</Text></Text>
              <Text style={s.reviewRow}>Profession:   <Text style={s.reviewVal}>
                {PROFESSIONS.find(p => p.value === occupation)?.label ?? occupation}
              </Text></Text>
              <Text style={s.reviewRow}>Income:       <Text style={s.reviewVal}>
                {INCOME_BANDS.find(b => b.value === incomeBand)?.label ?? "—"}
              </Text></Text>
            </View>
          </>
        );

      default:
        return null;
    }
  };

  // ── Email check screen ───────────────────────────────────────────────────────

  if (submitted) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.emailCheckContainer}>
          <View style={s.emailCheckIconWrap}>
            <Ionicons name="mail" size={56} color={COLORS.primary} />
          </View>

          <Text style={s.emailCheckTitle}>Almost there!</Text>

          {/* KYC received confirmation */}
          <View style={s.emailCheckReceived}>
            <Ionicons name="checkmark-circle" size={18} color={COLORS.success} />
            <Text style={s.emailCheckReceivedText}>
              Your identity documents have been received and are being verified.
            </Text>
          </View>

          <Text style={s.emailCheckBody}>
            One last step — verify your email address{"\n"}
            <Text style={s.emailCheckAddress}>{submittedEmail}</Text>
          </Text>
          <Text style={s.emailCheckSub}>
            We've sent a verification link to that address. Click it to confirm
            your email and unlock full access to WEPL.
          </Text>

          <TouchableOpacity
            style={s.emailCheckBtn}
            onPress={() => router.replace("/(drawer)/profile")}
          >
            <Text style={s.emailCheckBtnText}>Go to my profile</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={s.emailCheckResend}
            onPress={async () => {
              try {
                const API = (await import("../api/client")).default;
                await API.post("users/kyc/resend-verification/");
                Alert.alert("Sent", `Verification email resent to ${submittedEmail}`);
              } catch (e: any) {
                Alert.alert("Error", e?.response?.data?.error || "Could not resend. Try again.");
              }
            }}
          >
            <Text style={s.emailCheckResendText}>Didn't receive it? Resend email</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

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
          {/* Header row: back-to-profile chevron + progress dots */}
          <View style={s.headerRow}>
            <TouchableOpacity
              style={s.headerBack}
              onPress={() => router.back()}
              hitSlop={10}
            >
              <Ionicons name="chevron-back" size={24} color={COLORS.text} />
            </TouchableOpacity>

            <View style={[s.progressRow, { flex: 1 }]}>
              {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
                <View key={i} style={[s.progressDot, i + 1 <= step && s.progressDotActive]} />
              ))}
            </View>
          </View>

          <Animated.View style={{ opacity: fadeAnim }}>
            <Text style={s.stepLabel}>Step {step} of {TOTAL_STEPS}</Text>

            {renderStep()}

          {error ? <Text style={s.error}>{error}</Text> : null}
          </Animated.View>

          {/* Step 2 manages its own navigation via inline CTAs — hide the shared nav row */}
          {step !== 2 && (
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
          )}

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

  // Header row containing back button + progress bar
  headerRow: {
    flexDirection: "row", alignItems: "center",
    marginBottom: 4, gap: 4,
  },
  headerBack: {
    width: 36, height: 36,
    justifyContent: "center", alignItems: "center",
  },
  progressRow:       { flexDirection: "row", gap: 6, marginBottom: 8 },
  progressDot:       { flex: 1, height: 4, borderRadius: 2, backgroundColor: COLORS.border },
  progressDotActive: { backgroundColor: COLORS.primary },

  stepLabel: { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 20 },

  title:    { fontSize: FONTS.xxl, fontWeight: "700", color: COLORS.text, marginBottom: 6 },
  subtitle: { fontSize: FONTS.md,  color: COLORS.textSecondary, marginBottom: 24, lineHeight: 22 },

  // ID number real-time check
  idRow:      { flexDirection: "row", alignItems: "center", gap: 8 },
  idInput:    { flex: 1 },
  idStatus:   { width: 28, alignItems: "center" },
  inputError: { borderColor: COLORS.error },
  inputWarn:  { borderColor: COLORS.warning },
  inputOk:    { borderColor: COLORS.success },
  idErrorText: {
    fontSize: FONTS.sm, color: COLORS.error,
    marginTop: 6, fontWeight: "500",
  },
  emailWarnBox: {
    flexDirection: "row", alignItems: "flex-start", gap: 6,
    backgroundColor: "#FEF3C7", borderRadius: RADIUS.md,
    padding: 10, marginTop: 6,
  },
  emailWarnText: {
    flex: 1, fontSize: FONTS.sm, color: "#92400E", lineHeight: 18,
  },

  fieldGroup: { marginBottom: 20 },
  label: {
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginBottom: 4,
  },
  fieldHint: {
    fontSize: FONTS.xs, color: COLORS.textMuted, marginBottom: 8, lineHeight: 16,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 14, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.white,
  },

  // Date of birth picker trigger
  dobTrigger: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 14,
    backgroundColor: COLORS.white,
  },
  dobTriggerText: {
    flex: 1,
    fontSize: FONTS.md,
    color: COLORS.text,
  },
  // iOS modal sheet for the date picker
  dobModalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
  },
  dobModalSheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingBottom: 32,
  },
  dobModalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.divider,
  },
  dobModalTitle:  { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  dobModalCancel: { fontSize: FONTS.md, color: COLORS.textSecondary },
  dobModalDone:   { fontSize: FONTS.md, fontWeight: "700", color: COLORS.primary },

  photoPrompt:  { fontSize: FONTS.md, color: COLORS.textMuted },

  dropdown: {
    maxHeight: 220, borderWidth: 1, borderColor: COLORS.border,
    borderRadius: RADIUS.md, backgroundColor: COLORS.white, marginTop: 4,
  },
  dropdownItem: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    padding: 13, borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  dropdownItemActive: { backgroundColor: COLORS.primaryPale },
  dropdownText: { fontSize: FONTS.md, color: COLORS.text, flex: 1 },

  // Radio list
  radioList: {
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: RADIUS.md, overflow: "hidden",
    backgroundColor: COLORS.white,
  },
  radioRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: 16, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: COLORS.divider,
  },
  radioRowActive:  { backgroundColor: COLORS.primaryPale },
  radioLabel:      { fontSize: FONTS.md, color: COLORS.text, flex: 1 },
  radioLabelActive:{ color: COLORS.primary, fontWeight: "600" },
  radioCircle: {
    width: 22, height: 22, borderRadius: 11,
    borderWidth: 2, borderColor: COLORS.border,
    justifyContent: "center", alignItems: "center",
    flexShrink: 0,
  },
  radioCircleActive: { borderColor: COLORS.primary },
  radioDot: {
    width: 11, height: 11, borderRadius: 5.5,
    backgroundColor: COLORS.primary,
  },

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

  // ── Photo capture styles ────────────────────────────────────────────────────
  photoBox: {
    width: "100%", height: 200,
    borderRadius: RADIUS.lg,
    borderWidth: 2, borderColor: COLORS.border, borderStyle: "dashed",
    backgroundColor: COLORS.background,
    justifyContent: "center", alignItems: "center",
    overflow: "hidden", marginBottom: 16,
  },
  photoBoxDone: {
    borderStyle: "solid", borderColor: COLORS.primary, borderWidth: 2,
  },
  selfieBox:    { height: 240, borderRadius: 120, width: 240, alignSelf: "center" },
  photoPreview: { width: "100%", height: "100%" },
  photoRetakeOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.35)",
    justifyContent: "center", alignItems: "center", gap: 4,
  },
  photoRetakeText: { color: "#fff", fontSize: FONTS.sm, fontWeight: "700" },
  photoPromptWrap: { alignItems: "center", gap: 8 },
  photoPromptText: { fontSize: FONTS.md, color: COLORS.primary, fontWeight: "600" },
  photoPromptHint: { fontSize: FONTS.xs, color: COLORS.textMuted },
  selfieConfirm: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: COLORS.primaryPale, borderRadius: RADIUS.md,
    padding: 12, marginBottom: 8,
  },
  selfieConfirmText: { fontSize: FONTS.sm, color: COLORS.success, fontWeight: "600", flex: 1 },

  // ── Intro card ──────────────────────────────────────────────────────────────
  introCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    padding: 20,
    marginBottom: 20,
    borderWidth: 1, borderColor: COLORS.border,
  },
  introGreeting: {
    fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text,
    marginBottom: 8,
  },
  introBody: {
    fontSize: FONTS.sm, color: COLORS.textSecondary,
    lineHeight: 20, marginBottom: 16,
  },
  introSteps:  { gap: 12, marginBottom: 20 },
  introStep:   { flexDirection: "row", alignItems: "center", gap: 10 },
  introStepNum: {
    width: 24, height: 24, borderRadius: 12,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
  },
  introStepNumText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  introStepLabel:   { fontSize: FONTS.sm, color: COLORS.text, fontWeight: "500", flex: 1 },

  introTips:       { backgroundColor: COLORS.primaryBg, borderRadius: RADIUS.md, padding: 14, gap: 6 },
  introTipsTitle:  { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.primary, marginBottom: 4 },
  introTip:        { flexDirection: "row", gap: 6 },
  introTipBullet:  { fontSize: FONTS.sm, color: COLORS.primary, lineHeight: 20 },
  introTipText:    { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 20, flex: 1 },

  introCta: {
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    gap: 8, backgroundColor: COLORS.primary,
    padding: 16, borderRadius: RADIUS.md, marginBottom: 8,
  },
  introCtaText: { color: "#fff", fontWeight: "700", fontSize: FONTS.md },

  // ── Email check screen ─────────────────────────────────────────────────────
  emailCheckContainer: {
    flex: 1, alignItems: "center", justifyContent: "center",
    paddingHorizontal: 32, paddingVertical: 40,
  },
  emailCheckIconWrap: {
    width: 96, height: 96, borderRadius: 48,
    backgroundColor: COLORS.primaryPale,
    justifyContent: "center", alignItems: "center",
    marginBottom: 24,
  },
  emailCheckTitle: {
    fontSize: FONTS.xxl, fontWeight: "700",
    color: COLORS.text, textAlign: "center", marginBottom: 12,
  },
  emailCheckReceived: {
    flexDirection: "row", alignItems: "flex-start", gap: 8,
    backgroundColor: COLORS.primaryPale,
    borderRadius: RADIUS.md, padding: 12,
    marginBottom: 16, width: "100%",
  },
  emailCheckReceivedText: {
    flex: 1, fontSize: FONTS.sm, color: COLORS.success,
    fontWeight: "600", lineHeight: 18,
  },
  emailCheckBody: {
    fontSize: FONTS.md, color: COLORS.textSecondary,
    textAlign: "center", lineHeight: 24, marginBottom: 8,
  },
  emailCheckAddress: {
    fontWeight: "700", color: COLORS.primary,
  },
  emailCheckSub: {
    fontSize: FONTS.sm, color: COLORS.textMuted,
    textAlign: "center", lineHeight: 20, marginBottom: 32,
  },
  emailCheckBtn: {
    width: "100%", backgroundColor: COLORS.primary,
    padding: 16, borderRadius: RADIUS.md, alignItems: "center",
    marginBottom: 16,
  },
  emailCheckBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
  emailCheckResend:  { padding: 8 },
  emailCheckResendText: {
    color: COLORS.primary, fontSize: FONTS.sm,
    fontWeight: "600", textDecorationLine: "underline",
  },
});
