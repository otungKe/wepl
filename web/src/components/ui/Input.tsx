import { cn } from '@/lib/utils'
import { forwardRef, type InputHTMLAttributes } from 'react'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
}

export const Input = forwardRef<HTMLInputElement, Props>(
  ({ label, error, hint, className, ...props }, ref) => (
    <div className="flex flex-col gap-1.5">
      {label && <label className="text-sm font-medium text-text">{label}</label>}
      <input
        ref={ref}
        className={cn(
          'w-full rounded border border-border px-4 py-3.5 text-base text-text',
          'placeholder:text-text-muted bg-white',
          'focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30',
          'transition-colors',
          error && 'border-error focus:border-error focus:ring-error/30',
          className
        )}
        {...props}
      />
      {error && <span className="text-sm text-error">{error}</span>}
      {!error && hint && <span className="text-sm text-text-muted">{hint}</span>}
    </div>
  )
)
Input.displayName = 'Input'
