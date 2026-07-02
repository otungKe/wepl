import { InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes, forwardRef } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

const base =
  'w-full rounded-lg border bg-surface px-3.5 text-base text-text placeholder:text-text-muted ' +
  'focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-colors disabled:opacity-60'

// Error styling shared by input/textarea/select so the error focus ring never drifts.
const errorRing = 'border-error focus:border-error focus:ring-error/20'

function Field({
  label, error, hint, required, children,
}: { label?: string; error?: string; hint?: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      {label && (
        <span className="text-sm font-medium text-text-secondary">
          {label}{required && <span className="text-error" aria-hidden="true"> *</span>}
        </span>
      )}
      {children}
      {error ? <span className="text-xs text-error">{error}</span>
        : hint ? <span className="text-xs text-text-muted">{hint}</span> : null}
    </label>
  )
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> { label?: string; error?: string; hint?: string }
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className, required, ...rest }, ref,
) {
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      <input
        ref={ref}
        required={required}
        aria-invalid={error ? true : undefined}
        className={cn(base, 'h-11', error ? errorRing : 'border-border', className)}
        {...rest}
      />
    </Field>
  )
})

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> { label?: string; error?: string; hint?: string }
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, error, hint, className, required, ...rest }, ref,
) {
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      <textarea
        ref={ref}
        required={required}
        aria-invalid={error ? true : undefined}
        className={cn(base, 'py-2.5 min-h-[90px] resize-y', error ? errorRing : 'border-border', className)}
        {...rest}
      />
    </Field>
  )
})

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> { label?: string; error?: string; hint?: string }
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, error, hint, className, required, children, ...rest }, ref,
) {
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      <div className="relative">
        <select
          ref={ref}
          required={required}
          aria-invalid={error ? true : undefined}
          className={cn(base, 'h-11 appearance-none pr-9', error ? errorRing : 'border-border', className)}
          {...rest}
        >
          {children}
        </select>
        <ChevronDown
          size={16}
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted"
        />
      </div>
    </Field>
  )
})
