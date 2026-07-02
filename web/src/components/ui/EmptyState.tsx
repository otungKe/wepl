import { AlertTriangle, LucideIcon } from 'lucide-react'
import { Button } from './Button'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-primary-bg/50 px-6 py-14 text-center">
      {Icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-pale text-primary">
          <Icon size={24} />
        </div>
      )}
      <div>
        <p className="font-semibold text-text">{title}</p>
        {description && <p className="mt-1 text-sm text-text-muted">{description}</p>}
      </div>
      {action}
    </div>
  )
}

interface ErrorStateProps {
  title?: string
  description?: string
  /** When provided, renders a "Try again" button that calls it. */
  onRetry?: () => void
  retrying?: boolean
}

/** Shared failure state for data-fetch errors — the error-tone sibling of EmptyState. */
export function ErrorState({
  title = 'Something went wrong',
  description = "We couldn't load this. Please try again.",
  onRetry,
  retrying,
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-error/30 bg-error/5 px-6 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-error/10 text-error">
        <AlertTriangle size={24} />
      </div>
      <div>
        <p className="font-semibold text-text">{title}</p>
        {description && <p className="mt-1 text-sm text-text-muted">{description}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} loading={retrying}>
          Try again
        </Button>
      )}
    </div>
  )
}
