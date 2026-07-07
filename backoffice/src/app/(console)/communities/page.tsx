'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, Building2, Search, Lock } from 'lucide-react'
import { platform, type CommunityRow } from '@/lib/platform'

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'suspended', label: 'Suspended' },
  { key: 'archived', label: 'Archived' },
]

export default function CommunitiesRegistry() {
  const [tab, setTab] = useState('all')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')     // debounced
  const [rows, setRows] = useState<CommunityRow[]>([])
  const [count, setCount] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t) }, [q])

  useEffect(() => {
    setStatus('loading')
    platform.communities({ status: tab, ...(query ? { q: query } : {}) })
      .then((r) => { setRows(r.data.results); setCount(r.data.count); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [tab, query])

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Building2 className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Communities</h1>
        <span className="text-xs text-slate-400">{count} match{count === 1 ? '' : 'es'}</span>
        <div className="ml-auto flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-900">
          <Search className="h-4 w-4 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Name, invite code or ID…"
            className="w-56 bg-transparent text-sm outline-none placeholder:text-slate-400" />
        </div>
      </div>

      <div className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load communities.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          No communities match.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                <th className="px-4 py-2.5 text-left font-semibold">Community</th>
                <th className="px-4 py-2.5 text-left font-semibold">Category</th>
                <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                <th className="px-4 py-2.5 text-right font-semibold">Members</th>
                <th className="px-4 py-2.5 text-left font-semibold">Owner</th>
                <th className="px-4 py-2.5 text-right font-semibold">Created</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                  <td className="px-4 py-2.5">
                    <Link href={`/communities/${r.id}`} className="flex items-center gap-1.5">
                      <span className="font-medium text-slate-800 dark:text-slate-100">{r.name}</span>
                      {r.is_private && <Lock className="h-3 w-3 text-slate-400" />}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-xs capitalize text-slate-500">{r.category}</td>
                  <td className="px-4 py-2.5"><StatusChip status={r.status} /></td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">{r.member_count ?? '—'}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{r.owner_phone}</td>
                  <td className="px-4 py-2.5 text-right text-xs text-slate-400">
                    {new Date(r.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  const m: Record<string, string> = {
    active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
    suspended: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
    archived: 'bg-slate-200 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300',
  }
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${m[status] ?? 'bg-slate-100 text-slate-600'}`}>{status}</span>
}
