import { ButtonHTMLAttributes, forwardRef } from 'react'
import { cn } from '@/lib/utils'
import { Spinner } from './Spinner'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  fullWidth?: boolean
}

const variants: Record<Variant, string> = {
  primary:   'bg-primary text-white hover:bg-primary-dark shadow-sm',
  secondary: 'bg-accent text-white hover:bg-accent/90 shadow-sm',
  ghost:     'bg-transparent text-text-secondary hover:bg-divider',
  outline:   'bg-surface text-text border border-border hover:bg-divider',
  danger:    'bg-error text-white hover:bg-error/90 shadow-sm',
}

const sizes: Record<Size, string> = {
  sm: 'h-9 px-3 text-sm rounded-lg gap-1.5',
  md: 'h-11 px-4 text-base rounded-lg gap-2',
  lg: 'h-12 px-6 text-base rounded-lg gap-2',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading, fullWidth, className, children, disabled, ...rest }, ref,
) {
  const onLight = variant === 'outline' || variant === 'ghost'
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center font-semibold transition-colors select-none',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
        'disabled:opacity-50 disabled:pointer-events-none',
        variants[variant], sizes[size], fullWidth && 'w-full', className,
      )}
      {...rest}
    >
      {loading && <Spinner size={size === 'sm' ? 14 : 18} className={onLight ? 'text-primary' : 'text-white'} />}
      {children}
    </button>
  )
})
