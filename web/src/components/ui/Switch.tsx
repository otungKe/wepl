import { cn } from '@/lib/utils'

/**
 * A single, shared on/off switch. Vertically centres the knob with flex (no
 * absolute positioning to drift), keeps a subtle knob shadow that reads on both
 * themes, and exposes proper switch semantics + a visible focus ring.
 */
export function Switch({
  checked, onChange, disabled, id, ariaLabel,
}: {
  checked: boolean
  onChange: () => void
  disabled?: boolean
  id?: string
  ariaLabel?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      id={id}
      onClick={onChange}
      disabled={disabled}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-surface',
        'disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'bg-primary' : 'bg-border',
      )}
    >
      <span
        className={cn(
          'inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform duration-200',
          checked ? 'translate-x-[22px]' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}
