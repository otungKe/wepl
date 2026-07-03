'use client'
import { useAuthStore } from '@/store/auth'

export type KycStatus = 'not_submitted' | 'pending' | 'approved' | 'rejected'

/**
 * Web counterpart of the mobile `useKYCGate` — exposes the user's KYC status and
 * derived access tier (ADR-0022) so tier-aware UI (verify prompts, lock badges,
 * gated actions) reads from one place. Tier is derived from the auth-store user,
 * which the app layout refreshes on load.
 */
export function useTier() {
  const user = useAuthStore(s => s.user)
  const kycStatus = (user?.kyc_status ?? 'not_submitted') as KycStatus
  const isVerified = kycStatus === 'approved'
  return {
    kycStatus,
    isVerified,
    tier: isVerified ? ('tier1' as const) : ('tier0' as const),
  }
}

/** Status-specific copy for verify prompts (mirrors the mobile messages). */
export const KYC_PROMPT: Record<KycStatus, { badge: string; title: string; body: string; cta: string; href: string }> = {
  not_submitted: {
    badge: 'Not verified',
    title: 'Verify your identity',
    body: 'Complete a quick identity check to unlock payments, contributions, advances, and group savings.',
    cta: 'Verify now',
    href: '/kyc',
  },
  pending: {
    badge: 'Under review',
    title: 'Verification under review',
    body: 'Your identity documents are being reviewed. This usually takes less than 24 hours.',
    cta: 'View status',
    href: '/kyc',
  },
  rejected: {
    badge: 'Action needed',
    title: 'Verification needs attention',
    body: 'Your identity verification was not approved. Please re-submit your documents.',
    cta: 'Re-submit',
    href: '/kyc',
  },
  approved: {
    badge: 'Verified',
    title: 'Verified',
    body: '',
    cta: '',
    href: '/kyc',
  },
}
