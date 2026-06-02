/**
 * useKYCGate
 *
 * Provides KYC status and a gate function for financial actions.
 *
 * Usage:
 *   const { isVerified, kycStatus, requireKYC } = useKYCGate();
 *
 *   // In an onPress handler:
 *   function handlePay() {
 *     if (!requireKYC()) return;   // shows alert + navigates to KYC if not verified
 *     initiatePayment();
 *   }
 *
 * Status values match the backend KYCProfile.status choices:
 *   'approved' | 'pending' | 'rejected' | 'not_submitted'
 */
import { useEffect, useState, useCallback } from "react";
import { Alert } from "react-native";
import { router } from "expo-router";
import { getKYCStatus } from "../api/auth";

export type KYCStatus = "approved" | "pending" | "rejected" | "not_submitted" | "loading";

const MESSAGES: Record<string, { title: string; body: string; cta: string }> = {
  not_submitted: {
    title: "Verify your identity",
    body:  "Complete a quick KYC check to unlock payments, contributions, and advances.",
    cta:   "Verify Now",
  },
  pending: {
    title: "KYC under review",
    body:  "Your identity documents are being reviewed. This usually takes less than 24 hours.",
    cta:   "View Status",
  },
  rejected: {
    title: "KYC action required",
    body:  "Your identity verification was not approved. Please re-submit your documents.",
    cta:   "Re-submit",
  },
};

export function useKYCGate() {
  const [kycStatus, setKycStatus] = useState<KYCStatus>("loading");

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getKYCStatus();
      setKycStatus(data.status ?? "not_submitted");
    } catch {
      // If the fetch fails (e.g. offline) treat as unknown — don't block UI
      setKycStatus("not_submitted");
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const isVerified = kycStatus === "approved";

  /**
   * Call before any financial action.
   * Returns true if the user is verified (action should proceed).
   * Returns false and shows an alert if not verified (action should be blocked).
   */
  function requireKYC(): boolean {
    if (isVerified || kycStatus === "loading") return true;

    const msg = MESSAGES[kycStatus] ?? MESSAGES.not_submitted;

    Alert.alert(
      msg.title,
      msg.body,
      [
        { text: "Not now", style: "cancel" },
        {
          text:    msg.cta,
          onPress: () => router.push("/kyc"),
        },
      ],
    );
    return false;
  }

  return { kycStatus, isVerified, requireKYC, refetch: fetchStatus };
}
