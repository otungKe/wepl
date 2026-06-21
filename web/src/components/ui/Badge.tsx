import { cn } from '@/lib/utils'

type Variant = 'approved' | 'pending' | 'rejected' | 'default' | 'accent'

interface Props {
  variant?: Variant
  children: React.ReactNode
  className?: string
}

const styles: Record<Variant, string> = {
  approved: 'bg-primary-pale text-primary',
  pending:  'bg-accent-pale text-accent',
  rejected: 'bg-red-50 text-error',
  default:  'bg-divider text-text-secondary',
  accent:   'bg-accent text-white',
}

export function Badge({ variant = 'default', children, className }: Props) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold',
      styles[variant],
      className
    )}>
      {children}
    </span>
  )
}
