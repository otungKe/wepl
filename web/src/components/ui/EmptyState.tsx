import { type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  icon: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: Props) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 py-16 text-center', className)}>
      <div className="w-14 h-14 rounded-full bg-primary-pale flex items-center justify-center">
        <Icon size={24} className="text-primary" />
      </div>
      <p className="text-base font-semibold text-text">{title}</p>
      {description && <p className="text-sm text-text-secondary max-w-xs">{description}</p>}
      {action}
    </div>
  )
}
