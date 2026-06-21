import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'primary'

const tones: Record<Tone, string> = {
  neutral: 'bg-divider text-text-secondary',
  success: 'bg-primary-pale text-primary',
  warning: 'bg-accent-pale text-accent',
  danger:  'bg-red-50 text-error',
  info:    'bg-blue-50 text-blue-700',
  primary: 'bg-primary text-white',
}

/** Maps common backend statuses to a tone. */
export function statusTone(status?: string | null): Tone {
  switch ((status ?? '').toUpperCase()) {
    case 'APPROVED': case 'EXECUTED': case 'DISBURSED': case 'SUCCESS': case 'ACTIVE': return 'success'
    case 'PENDING': return 'warning'
    case 'REJECTED': case 'FAILED': case 'WITHDRAWN': return 'danger'
    default: return 'neutral'
  }
}

export function Badge({ children, tone = 'neutral', className }: { children: React.ReactNode; tone?: Tone; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold', tones[tone], className)}>
      {children}
    </span>
  )
}
