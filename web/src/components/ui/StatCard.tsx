import { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StatCardProps {
  label: string
  value: string
  icon?: LucideIcon
  hint?: string
  className?: string
  accent?: boolean
}

export function StatCard({ label, value, icon: Icon, hint, className, accent }: StatCardProps) {
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
      <p className={cn('mt-1.5 text-2xl font-bold tabular-nums', accent ? 'text-white' : 'text-text')}>{value}</p>
      {hint && <p className={cn('mt-0.5 text-xs', accent ? 'text-white/70' : 'text-text-muted')}>{hint}</p>}
    </div>
  )
}
