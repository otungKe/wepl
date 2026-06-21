import { cn } from '@/lib/utils'
import { type ButtonHTMLAttributes, forwardRef } from 'react'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = 'primary', size = 'md', loading, className, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-2 font-semibold rounded transition-opacity',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
        'disabled:opacity-60 disabled:cursor-not-allowed',
        {
          'bg-primary text-white hover:bg-primary-dark active:bg-primary-dark':
            variant === 'primary',
          'bg-white text-text border border-border hover:bg-primary-pale':
            variant === 'secondary',
          'text-text-secondary hover:bg-divider':
            variant === 'ghost',
          'bg-error text-white hover:opacity-90':
            variant === 'danger',
        },
        {
          'text-sm px-3 py-1.5': size === 'sm',
          'text-base px-5 py-3':  size === 'md',
          'text-lg px-6 py-4':    size === 'lg',
        },
        className
      )}
      {...props}
    >
      {loading && (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      )}
      {children}
    </button>
  )
)
Button.displayName = 'Button'
