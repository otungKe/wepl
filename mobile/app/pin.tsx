import { useRef, useState } from "react";
import * as storage from "../utils/secureStorage";
import { router, useLocalSearchParams } from "expo-router";
import { setPIN, resetPIN } from "../api/auth";
import PinPad from "../components/app/PinPad";

type Step = "enter" | "confirm";

export default function PINScreen() {
  const { phone_number, mode } = useLocalSearchParams<{
    phone_number: string;
    mode?: string;
  }>();
  const isReset = mode === "reset";

  const [step,     setStep]     = useState<Step>("enter");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");
  const [resetKey, setResetKey] = useState(0);

  // ── Use a ref for the first PIN so handleConfirm always reads the current
  // value — useState updates are async and can cause stale closures across
  // renders; useRef.current is always synchronous and up-to-date.
  const firstPinRef = useRef("");

  // ── Step 1: user has entered their new PIN ───────────────────────────────
  function handleEnter(pin: string) {
    firstPinRef.current = pin;   // always current — no stale closure risk
    setError("");
    setStep("confirm");          // PinPad delays onComplete by 80ms so the
                                 // last dot fills before the screen swaps.
  }

  // ── Step 2: user confirms their PIN ─────────────────────────────────────
  async function handleConfirm(pin: string) {
    if (pin !== firstPinRef.current) {
      setError("PINs don't match. Please try again.");
      setResetKey(k => k + 1);
      // Go back to step 1 after the error animation
      setTimeout(() => {
        firstPinRef.current = "";
        setStep("enter");
        setError("");
      }, 1400);
      return;
    }

    setError("");
    setLoading(true);
    try {
      const data = isReset ? await resetPIN(pin) : await setPIN(pin);
      await storage.setItem("access",  data.access);
      await storage.setItem("refresh", data.refresh);
      if (phone_number) await storage.setItem("phone", phone_number);
      // New users → display name screen before entering the app.
      // Reset users → straight into the app (they already have a profile).
      if (isReset) {
        // PIN reset for existing user — go to drawer root.
        // Tab layout resolves to Communities (verified) or Profile (unverified).
        router.replace("/(drawer)" as any);
      } else {
        // New user — display name screen first, then into the app.
        router.replace("/display-name");
      }
    } catch (e: any) {
      const msg = e?.response?.data?.error || "Something went wrong. Please try again.";
      setError(msg);
      setResetKey(k => k + 1);
      setTimeout(() => {
        firstPinRef.current = "";
        setStep("enter");
        setError("");
      }, 1600);
    } finally {
      setLoading(false);
    }
  }

  // ── Confirm step ─────────────────────────────────────────────────────────
  // key="confirm" ensures React unmounts the enter PinPad and mounts a fresh
  // one — without this, React reuses the same instance and the internal `pin`
  // state (filled with digits from step 1) persists into the confirm step.
  if (step === "confirm") {
    return (
      <PinPad
        key="pin-confirm"
        icon="shield-checkmark"
        title="Confirm your PIN"
        subtitle="Enter the same PIN again"
        onComplete={handleConfirm}
        error={error}
        loading={loading}
        resetKey={resetKey}
        onBack={() => {
          firstPinRef.current = "";
          setStep("enter");
          setError("");
          setResetKey(k => k + 1);
        }}
      />
    );
  }

  // ── Enter step ───────────────────────────────────────────────────────────
  return (
    <PinPad
      key="pin-enter"
      icon="lock-closed"
      title={isReset ? "New PIN" : "Create your PIN"}
      subtitle={
        isReset
          ? "Choose a new 6-digit PIN"
          : "Choose a secure 6-digit PIN"
      }
      onComplete={handleEnter}
      error={error}
      loading={false}
      resetKey={resetKey}
      onBack={() => router.back()}
    />
  );
}
