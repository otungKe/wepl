'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, Users2, Search } from 'lucide-react'
import { opsUsers, type UserRow } from '@/lib/platform'

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'deactivated', label: 'Deactivated' },
]

export default function UsersRegistry() {
  const [tab, setTab] = useState('all')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<UserRow[]>([])
  const [count, setCount] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t) }, [q])

  useEffect(() => {
    setStatus('loading')
    opsUsers.list({ state: tab, ...(query ? { q: query } : {}) })
      .then((r) => { setRows(r.data.results); setCount(r.data.count); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [tab, query])

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Users2 className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Members</h1>
        <span className="text-xs text-slate-400">{count} match{count === 1 ? '' : 'es'}</span>
        <div className="ml-auto flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-900">
          <Search className="h-4 w-4 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Phone, name, member no. or ID…"
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
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load members.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          No members match.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                <th className="px-4 py-2.5 text-left font-semibold">Member</th>
                <th className="px-4 py-2.5 text-left font-semibold">KYC</th>
                <th className="px-4 py-2.5 text-left font-semibold">Tier</th>
                <th className="px-4 py-2.5 text-left font-semibold">Account</th>
                <th className="px-4 py-2.5 text-right font-semibold">Joined</th>
                <th className="px-4 py-2.5 text-right font-semibold">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                  <td className="px-4 py-2.5">
                    <Link href={`/users/${r.id}`} className="block">
                      <span className="font-medium text-slate-800 dark:text-slate-100">{r.name || '—'}</span>
                      <span className="block font-mono text-xs text-slate-400">
                        {r.phone_number}{r.member_number ? ` · ${r.member_number}` : ''}
                      </span>
                    </Link>
                  </td>
                  <td className="px-4 py-2.5"><KycChip status={r.kyc_status} /></td>
                  <td className="px-4 py-2.5 font-mono text-xs">T{r.tier}</td>
                  <td className="px-4 py-2.5">
                    {r.is_active
                      ? <span className="text-xs text-emerald-600 dark:text-emerald-400">active</span>
                      : <span className="text-xs font-semibold text-red-600 dark:text-red-400">deactivated</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-slate-400">
                    {new Date(r.joined).toLocaleDateString(undefined, { dateStyle: 'medium' })}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-slate-400">
                    {r.last_seen ? new Date(r.last_seen).toLocaleDateString(undefined, { dateStyle: 'medium' }) : '—'}
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

function KycChip({ status }: { status: string }) {
  const m: Record<string, string> = {
    approved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
    pending: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
    not_submitted: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
  }
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${m[status] ?? 'bg-slate-100 text-slate-600'}`}>{status.replace('_', ' ')}</span>
}
