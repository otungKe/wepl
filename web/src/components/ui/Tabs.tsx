'use client'
import { cn } from '@/lib/utils'

interface TabsProps {
  tabs: { key: string; label: string; badge?: number }[]
  active: string
  onChange: (key: string) => void
  className?: string
}

export function Tabs({ tabs, active, onChange, className }: TabsProps) {
  return (
    <div className={cn('flex gap-1 overflow-x-auto border-b border-border no-scrollbar', className)}>
      {tabs.map(t => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            'relative whitespace-nowrap px-4 py-2.5 text-sm font-semibold transition-colors',
            active === t.key ? 'text-primary' : 'text-text-muted hover:text-text-secondary',
          )}
        >
          <span className="inline-flex items-center gap-1.5">
            {t.label}
            {t.badge ? <span className="rounded-full bg-accent px-1.5 text-xs text-white">{t.badge}</span> : null}
          </span>
          {active === t.key && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-primary" />}
        </button>
      ))}
    </div>
  )
}
