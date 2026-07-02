import { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from './Spinner'

interface StatCardProps {
  label: string
  value: string
  icon?: LucideIcon
  hint?: string
  className?: string
  accent?: boolean
  /** Render a skeleton in place of the value while data loads. */
  loading?: boolean
}

export function StatCard({ label, value, icon: Icon, hint, className, accent, loading }: StatCardProps) {
  return (
    <div className={cn(
      'rounded-lg border p-4',
      accent ? 'border-transparent bg-primary text-white' : 'border-border bg-surface',
      className,
    )}>
      <div className="flex items-center justify-between">
        <p className={cn('text-sm', accent ? 'text-white/80' : 'text-text-muted')}>{label}</p>
        {Icon && <Icon size={18} className={accent ? 'text-white/80' : 'text-primary'} />}
      </div>
      {loading
        ? <Skeleton className={cn('mt-2 h-7 w-20', accent && 'bg-white/25')} />
        : <p className={cn('mt-1.5 text-2xl font-bold tabular-nums', accent ? 'text-white' : 'text-text')}>{value}</p>}
      {hint && !loading && <p className={cn('mt-0.5 text-xs', accent ? 'text-white/70' : 'text-text-muted')}>{hint}</p>}
    </div>
  )
}
