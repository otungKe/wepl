'use client'
import { useParams } from 'next/navigation'
import { Construction } from 'lucide-react'
import { NAV_BY_SLUG } from '@/lib/opsNav'

// Catch-all for every /admin/<module> route not yet built. Keeps the IA whole
// while modules land phase by phase — the sidebar link resolves to a clear
// "in build" state instead of a 404.
export default function ModulePlaceholder() {
  const params = useParams()
  const slug = Array.isArray(params.slug) ? params.slug : [params.slug].filter(Boolean)
  const root = (slug[0] as string) ?? ''
  const item = NAV_BY_SLUG[root]
  const title = item?.label ?? (root ? root[0].toUpperCase() + root.slice(1) : 'Module')

  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white/50 px-6 py-16 text-center dark:border-slate-700 dark:bg-slate-900/40">
      <Construction className="h-9 w-9 text-slate-400" />
      <h1 className="mt-3 text-lg font-semibold text-slate-700 dark:text-slate-200">{title}</h1>
      <p className="mt-1 max-w-md text-sm text-slate-500">
        This workspace is part of the Back Office redesign and ships in
        {item?.phase ? ` ${item.phase}` : ' an upcoming phase'}. The navigation, permissions and
        deep-links are already wired — the module&apos;s queues and detail views arrive next.
      </p>
      {slug.length > 1 && (
        <p className="mt-3 font-mono text-xs text-slate-400">/{slug.join('/')}</p>
      )}
    </div>
  )
}
