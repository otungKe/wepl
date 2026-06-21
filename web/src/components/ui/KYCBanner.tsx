import { AlertCircle, CheckCircle, Clock, XCircle } from 'lucide-react'
import { Button } from './Button'
import Link from 'next/link'

type KycStatus = 'not_submitted' | 'pending' | 'approved' | 'rejected'

const configs: Record<KycStatus, { icon: React.ElementType; color: string; bg: string; title: string; cta: string }> = {
  not_submitted: { icon: AlertCircle, color: 'text-accent', bg: 'bg-accent-pale', title: 'Complete identity verification to unlock all features.', cta: 'Verify Now' },
  pending:       { icon: Clock,        color: 'text-accent', bg: 'bg-accent-pale', title: 'Your identity is under review. You\'ll be notified when approved.', cta: 'View Status' },
  approved:      { icon: CheckCircle,  color: 'text-primary', bg: 'bg-primary-pale', title: 'Your identity has been verified.', cta: '' },
  rejected:      { icon: XCircle,      color: 'text-error',  bg: 'bg-red-50',     title: 'Verification was not successful. Please resubmit.', cta: 'Resubmit' },
}

export function KYCBanner({ status }: { status: KycStatus }) {
  if (status === 'approved') return null
  const { icon: Icon, color, bg, title, cta } = configs[status]
  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-lg ${bg}`}>
      <Icon size={18} className={color} />
      <p className={`flex-1 text-sm ${color}`}>{title}</p>
      {cta && (
        <Link href="/kyc">
          <Button size="sm" variant="secondary" className="shrink-0">{cta}</Button>
        </Link>
      )}
    </div>
  )
}
