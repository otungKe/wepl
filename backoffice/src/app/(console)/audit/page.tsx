'use client'
import { useEffect, useState } from 'react'
import { Loader2, ScrollText, ChevronDown, ChevronRight, Download } from 'lucide-react'
import { platform, type AuditRow } from '@/lib/platform'
import { downloadCsv } from '@/lib/ops'
import { useCan } from '@/store/ops'
import { staffFirstName } from '@/lib/staff'

export default function AuditLog() {
  const can = useCan()
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const [filters, setFilters] = useState<{ action: string; actor: string }>({ action: '', actor: '' })
  const [rows, setRows] = useState<AuditRow[]>([])
  const [count, setCount] = useState(0)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [open, setOpen] = useState<number | null>(null)

  useEffect(() => {
    const t = setTimeout(() => { setFilters({ action, actor }); setOffset(0) }, 300)
    return () => clearTimeout(t)
  }, [action, actor])

  useEffect(() => {
    setStatus('loading')
    platform.audit({
      ...(filters.action ? { action: filters.action } : {}),
      ...(filters.actor ? { actor: filters.actor } : {}),
      offset, limit: 50,
    })
      .then((r) => { setRows(r.data.results); setCount(r.data.count); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [filters, offset])

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <ScrollText className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Audit log</h1>
        <span className="text-xs text-slate-400">{count} event{count === 1 ? '' : 's'} · append-only</span>
        {can('audit.export') && (
          <button
            onClick={() => downloadCsv('/ops/exports/audit/',
              { ...(filters.action ? { action: filters.action } : {}), ...(filters.actor ? { actor: filters.actor } : {}) })}
            title="Export the current filter as CSV"
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
            <Download className="h-4 w-4" /> Export
          </button>
        )}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <input value={action} onChange={(e) => setAction(e.target.value)}
          placeholder="Action prefix, e.g. community. or ops.verification."
          className="w-72 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-900" />
        <input value={actor} onChange={(e) => setActor(e.target.value)}
          placeholder="Actor contains…"
          className="w-56 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-900" />
      </div>

      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load the audit log.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          No events match.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                <th className="w-6 px-2 py-2.5" />
                <th className="px-3 py-2.5 text-left font-semibold">Action</th>
                <th className="px-3 py-2.5 text-left font-semibold">Actor</th>
                <th className="px-3 py-2.5 text-left font-semibold">Target</th>
                <th className="px-3 py-2.5 text-right font-semibold">When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <RowPair key={r.id} r={r} open={open === r.id}
                  onToggle={() => setOpen(open === r.id ? null : r.id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {status === 'ready' && count > 50 && (
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}
            className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium disabled:opacity-40 dark:border-slate-700">← Newer</button>
          <span>{offset + 1}–{Math.min(offset + 50, count)} of {count}</span>
          <button disabled={offset + 50 >= count} onClick={() => setOffset(offset + 50)}
            className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium disabled:opacity-40 dark:border-slate-700">Older →</button>
        </div>
      )}
    </div>
  )
}

function RowPair({ r, open, onToggle }: { r: AuditRow; open: boolean; onToggle: () => void }) {
  const hasMeta = r.metadata && Object.keys(r.metadata).length > 0
  return (
    <>
      <tr onClick={onToggle}
        className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
        <td className="px-2 py-2 text-slate-400">
          {hasMeta ? (open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />) : null}
        </td>
        <td className="px-3 py-2 font-mono text-xs text-slate-700 dark:text-slate-200">{r.action}</td>
        <td className="px-3 py-2 text-xs text-slate-500">
          {r.actor.includes('@') ? staffFirstName(r.actor) : r.actor}
        </td>
        <td className="px-3 py-2 font-mono text-[11px] text-slate-400">
          {r.target_type ? `${r.target_type}:${r.target_id}` : '—'}
        </td>
        <td className="px-3 py-2 text-right font-mono text-[11px] tabular-nums text-slate-400">
          {new Date(r.at).toLocaleString()}
        </td>
      </tr>
      {open && hasMeta && (
        <tr className="border-t border-slate-100 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/60">
          <td />
          <td colSpan={4} className="px-3 py-2">
            <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-[11px] text-slate-500">
              {JSON.stringify(r.metadata, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}
