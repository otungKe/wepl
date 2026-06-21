import { InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes, forwardRef } from 'react'
import { cn } from '@/lib/utils'

const base =
  'w-full rounded-lg border bg-white px-3.5 text-base text-text placeholder:text-text-muted ' +
  'focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-colors disabled:opacity-60'

function Field({ label, error, hint, children }: { label?: string; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      {label && <span className="text-sm font-medium text-text-secondary">{label}</span>}
      {children}
      {error ? <span className="text-xs text-error">{error}</span>
        : hint ? <span className="text-xs text-text-muted">{hint}</span> : null}
    </label>
  )
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> { label?: string; error?: string; hint?: string }
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className, ...rest }, ref,
) {
  return (
    <Field label={label} error={error} hint={hint}>
      <input ref={ref} className={cn(base, 'h-11', error && 'border-error focus:border-error focus:ring-error/20', !error && 'border-border', className)} {...rest} />
    </Field>
  )
})

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> { label?: string; error?: string; hint?: string }
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, error, hint, className, ...rest }, ref,
) {
  return (
    <Field label={label} error={error} hint={hint}>
      <textarea ref={ref} className={cn(base, 'py-2.5 min-h-[90px] resize-y', error ? 'border-error' : 'border-border', className)} {...rest} />
    </Field>
  )
})

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> { label?: string; error?: string; hint?: string }
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, error, hint, className, children, ...rest }, ref,
) {
  return (
    <Field label={label} error={error} hint={hint}>
      <select ref={ref} className={cn(base, 'h-11 appearance-none bg-no-repeat', error ? 'border-error' : 'border-border', className)} {...rest}>
        {children}
      </select>
    </Field>
  )
})
