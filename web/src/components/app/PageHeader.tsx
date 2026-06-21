'use client'
import { useRouter } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'

interface PageHeaderProps {
  title: string
  subtitle?: string
  back?: boolean | string
  action?: React.ReactNode
}

export function PageHeader({ title, subtitle, back, action }: PageHeaderProps) {
  const router = useRouter()
  return (
    <div className="mb-5">
      {back && (
        <button
          onClick={() => (typeof back === 'string' ? router.push(back) : router.back())}
          className="mb-3 inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text"
        >
          <ArrowLeft size={16} /> Back
        </button>
      )}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-bold text-text">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-text-muted">{subtitle}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    </div>
  )
}
