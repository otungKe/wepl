'use client'
import { Building2, ArrowLeft } from 'lucide-react'

interface AuthShellProps {
  title: string
  subtitle?: string
  onBack?: () => void
  backLabel?: string
  children: React.ReactNode
  footer?: React.ReactNode
}

export function AuthShell({ title, subtitle, onBack, backLabel, children, footer }: AuthShellProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-primary-bg px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary">
            <Building2 size={24} className="text-white" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none text-text">WEPL</p>
            <p className="text-xs text-text-muted">Community finance</p>
          </div>
        </div>

        {onBack && (
          <button onClick={onBack} className="mb-5 inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text">
            <ArrowLeft size={16} /> {backLabel ?? 'Back'}
          </button>
        )}

        <h1 className="text-2xl font-bold text-text">{title}</h1>
        {subtitle && <p className="mt-1 mb-6 text-text-secondary">{subtitle}</p>}
        <div className={subtitle ? '' : 'mt-6'}>{children}</div>

        {footer && <div className="mt-6 text-center text-sm text-text-secondary">{footer}</div>}
      </div>
    </div>
  )
}
