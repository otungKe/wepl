import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Selectable option card — the web counterpart of the mobile create flows'
 * OptionCard. Used for single-choice fields (contribution type, cadence,
 * governance threshold, …) where radio buttons would read as cramped.
 */
export function OptionCard({
  label, desc, active, onClick, icon,
}: {
  label: string
  desc?: string
  active: boolean
  onClick: () => void
  icon?: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition-colors',
        active
          ? 'border-primary bg-primary-pale/60 ring-1 ring-primary/30'
          : 'border-border bg-surface hover:border-primary/40 hover:bg-primary-bg/40',
      )}
    >
      {icon && <span className={cn('mt-0.5 shrink-0', active ? 'text-primary' : 'text-text-muted')}>{icon}</span>}
      <span className="min-w-0 flex-1">
        <span className={cn('block text-sm font-semibold', active ? 'text-primary' : 'text-text')}>{label}</span>
        {desc && <span className="mt-0.5 block text-xs text-text-muted">{desc}</span>}
      </span>
      <span className={cn(
        'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border',
        active ? 'border-primary bg-primary text-white' : 'border-border',
      )}>
        {active && <Check size={13} />}
      </span>
    </button>
  )
}

/** Inline on/off toggle row for boolean settings (welfare fund, shares, campaign). */
export function ToggleRow({
  label, desc, checked, onChange, icon,
}: {
  label: string
  desc?: string
  checked: boolean
  onChange: (v: boolean) => void
  icon?: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-left transition-colors hover:border-primary/30"
    >
      {icon && <span className="shrink-0 text-text-muted">{icon}</span>}
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-text">{label}</span>
        {desc && <span className="mt-0.5 block text-xs text-text-muted">{desc}</span>}
      </span>
      <span className={cn(
        'relative h-6 w-10 shrink-0 rounded-full transition-colors',
        checked ? 'bg-primary' : 'bg-divider',
      )}>
        <span className={cn(
          'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform',
          checked ? 'translate-x-[18px]' : 'translate-x-0.5',
        )} />
      </span>
    </button>
  )
}
