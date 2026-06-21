'use client'
import Link from 'next/link'
import { ShieldAlert, ShieldCheck, Clock } from 'lucide-react'
import { useAuthStore } from '@/store/auth'

export function KYCBanner() {
  const user = useAuthStore(s => s.user)
  const status = user?.kyc_status
  if (!status || status === 'approved') return null

  if (status === 'pending') {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-accent/30 bg-accent-pale px-4 py-2.5 text-sm text-accent">
        <Clock size={16} /> Your identity verification is under review.
      </div>
    )
  }

  const rejected = status === 'rejected'
  return (
    <Link
      href="/kyc"
      className="flex items-center justify-between gap-2 rounded-lg border border-accent/30 bg-accent-pale px-4 py-2.5 text-sm text-accent hover:bg-accent-pale/70"
    >
      <span className="flex items-center gap-2">
        {rejected ? <ShieldAlert size={16} /> : <ShieldCheck size={16} />}
        {rejected ? 'Your KYC was not approved. Tap to re-submit.' : 'Verify your identity to unlock payments & contributions.'}
      </span>
      <span className="font-semibold">{rejected ? 'Re-submit' : 'Verify'} →</span>
    </Link>
  )
}
