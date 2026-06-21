'use client'
import { cn } from '@/lib/utils'

interface Tab {
  id: string
  label: string
}

interface Props {
  tabs: Tab[]
  active: string
  onChange: (id: string) => void
  className?: string
}

export function Tabs({ tabs, active, onChange, className }: Props) {
  return (
    <div className={cn('flex border-b border-divider', className)}>
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            'px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap',
            active === tab.id
              ? 'text-primary border-b-2 border-primary -mb-px'
              : 'text-text-secondary hover:text-text'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
