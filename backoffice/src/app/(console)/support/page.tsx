'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, LifeBuoy, Search, Plus, Paperclip, X } from 'lucide-react'
import { support, type SupportRow } from '@/lib/platform'
import { useCan } from '@/store/ops'

const TABS = [
  { key: 'open', label: 'Open' },
  { key: 'submitted', label: 'Answered' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'all', label: 'All' },
]

export default function SupportDesk() {
  const can = useCan()
  const [tab, setTab] = useState('open')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<SupportRow[]>([])
  const [kinds, setKinds] = useState<{ value: string; label: string }[]>([])
  const [count, setCount] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [showRaise, setShowRaise] = useState(false)

  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t) }, [q])

  const load = useCallback(() => {
    setStatus('loading')
    support.list({ status: tab, ...(query ? { q: query } : {}) })
      .then((r) => { setRows(r.data.results); setCount(r.data.count); setKinds(r.data.kinds); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [tab, query])
  useEffect(() => { load() }, [load])

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <LifeBuoy className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Support — requests &amp; documents</h1>
        <span className="text-xs text-slate-400">{count} match{count === 1 ? '' : 'es'}</span>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-900">
            <Search className="h-4 w-4 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Phone, name or title…"
              className="w-48 bg-transparent text-sm outline-none placeholder:text-slate-400" />
          </div>
          {can('support.act') && (
            <button onClick={() => setShowRaise(!showRaise)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500">
              {showRaise ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              {showRaise ? 'Close' : 'Raise request'}
            </button>
          )}
        </div>
      </div>

      {showRaise && <RaiseForm kinds={kinds} onDone={() => { setShowRaise(false); load() }} />}

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
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load requests.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          Nothing here — the desk is clear.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                <th className="px-4 py-2.5 text-left font-semibold">Member</th>
                <th className="px-4 py-2.5 text-left font-semibold">Request</th>
                <th className="px-4 py-2.5 text-left font-semibold">Kind</th>
                <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                <th className="px-4 py-2.5 text-right font-semibold">Raised</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                  <td className="px-4 py-2.5">
                    <Link href={`/support/${r.id}`} className="block">
                      <span className="font-medium text-slate-800 dark:text-slate-100">{r.user_name || '—'}</span>
                      <span className="block font-mono text-xs text-slate-400">{r.phone_number}</span>
                    </Link>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="flex items-center gap-1.5 text-slate-700 dark:text-slate-200">
                      {r.title}
                      {r.has_document && <Paperclip className="h-3 w-3 text-slate-400" />}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">{r.kind.replace(/_/g, ' ')}</td>
                  <td className="px-4 py-2.5"><StatusChip status={r.status} /></td>
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

function RaiseForm({ kinds, onDone }: { kinds: { value: string; label: string }[]; onDone: () => void }) {
  const [phone, setPhone] = useState('')
  const [kind, setKind] = useState('address_proof')
  const [title, setTitle] = useState('')
  const [detail, setDetail] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const submit = async () => {
    setErr(''); setBusy(true)
    try { await support.raise({ phone_number: phone.trim(), kind, title: title.trim(), detail: detail.trim() }); onDone() }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to raise the request.') }
    finally { setBusy(false) }
  }

  return (
    <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50/40 p-4 dark:border-blue-500/30 dark:bg-blue-500/5">
      <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-slate-400">Raise a request</h2>
      {err && <p className="mb-2 text-sm text-red-500">{err}</p>}
      <div className="grid gap-2 sm:grid-cols-2">
        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Member phone number"
          className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 font-mono text-sm outline-none dark:border-slate-700 dark:bg-slate-900" />
        <select value={kind} onChange={(e) => setKind(e.target.value)}
          className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm outline-none dark:border-slate-700 dark:bg-slate-900">
          {kinds.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
        </select>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title shown to the member"
          className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none sm:col-span-2 dark:border-slate-700 dark:bg-slate-900" />
        <textarea value={detail} onChange={(e) => setDetail(e.target.value)} rows={2}
          placeholder="What the member is being asked to provide"
          className="resize-none rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none sm:col-span-2 dark:border-slate-700 dark:bg-slate-900" />
      </div>
      <button disabled={busy || !phone.trim() || !title.trim() || !detail.trim()} onClick={submit}
        className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50">
        Send to member
      </button>
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  const m: Record<string, [string, string]> = {
    open: ['awaiting member', 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400'],
    submitted: ['answered — review', 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400'],
    resolved: ['resolved', 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'],
  }
  const [label, cls] = m[status] ?? [status, 'bg-slate-100 text-slate-600']
  return <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`}>{label}</span>
}
