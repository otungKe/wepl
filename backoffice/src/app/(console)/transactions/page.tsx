'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, ArrowLeftRight, Search, Download } from 'lucide-react'
import { transactions, type TxRow } from '@/lib/platform'
import { downloadCsv } from '@/lib/ops'
import { useCan } from '@/store/ops'
import { TxState } from '@/components/TxState'

const STATES = ['all', 'PENDING', 'PROCESSING', 'SUCCESS', 'FAILED', 'REVERSED']

export default function TransactionsRegistry() {
  const can = useCan()
  const [state, setState] = useState('all')
  const [opType, setOpType] = useState('')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<TxRow[]>([])
  const [byState, setByState] = useState<Record<string, number>>({})
  const [opTypes, setOpTypes] = useState<{ value: string; label: string }[]>([])
  const [count, setCount] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => { const t = setTimeout(() => setQuery(q), 300); return () => clearTimeout(t) }, [q])

  useEffect(() => {
    setStatus('loading')
    transactions.list({ state, ...(opType ? { op_type: opType } : {}), ...(query ? { q: query } : {}) })
      .then((r) => {
        setRows(r.data.results); setCount(r.data.count)
        setByState(r.data.by_state); setOpTypes(r.data.op_types); setStatus('ready')
      })
      .catch(() => setStatus('error'))
  }, [state, opType, query])

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <ArrowLeftRight className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Transactions</h1>
        <span className="text-xs text-slate-400">{count} match{count === 1 ? '' : 'es'}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select value={opType} onChange={(e) => setOpType(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm outline-none dark:border-slate-700 dark:bg-slate-900">
            <option value="">All operation types</option>
            {opTypes.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-900">
            <Search className="h-4 w-4 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Phone, receipt, key or ID…"
              className="w-52 bg-transparent text-sm outline-none placeholder:text-slate-400" />
          </div>
          {can('reporting.export') && (
            <button
              onClick={() => downloadCsv('/ops/exports/transactions/',
                { state, ...(opType ? { op_type: opType } : {}), ...(query ? { q: query } : {}) })}
              title="Export the current filter as CSV"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
              <Download className="h-4 w-4" /> Export
            </button>
          )}
        </div>
      </div>

      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
        {STATES.map((s) => (
          <button key={s} onClick={() => setState(s)}
            className={`-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
              state === s ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                          : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
            {s === 'all' ? 'All' : s.toLowerCase()}
            {s !== 'all' && byState[s] != null && byState[s] > 0 && (
              <span className="rounded-full bg-slate-100 px-1.5 text-[10px] font-semibold text-slate-500 dark:bg-slate-800">{byState[s]}</span>
            )}
          </button>
        ))}
      </div>

      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load transactions.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          No movements match.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                <th className="px-4 py-2.5 text-left font-semibold">Movement</th>
                <th className="px-4 py-2.5 text-right font-semibold">Amount (KES)</th>
                <th className="px-4 py-2.5 text-left font-semibold">State</th>
                <th className="px-4 py-2.5 text-left font-semibold">Member</th>
                <th className="px-4 py-2.5 text-left font-semibold">Fund</th>
                <th className="px-4 py-2.5 text-left font-semibold">Receipt</th>
                <th className="px-4 py-2.5 text-right font-semibold">When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                  <td className="px-4 py-2.5">
                    <Link href={`/transactions/${r.id}`} className="block">
                      <span className="font-medium text-slate-800 dark:text-slate-100">
                        {r.op_type.replace(/_/g, ' ').toLowerCase()}
                      </span>
                      <span className="block font-mono text-[10px] text-slate-400">#{r.id}</span>
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">{r.amount}</td>
                  <td className="px-4 py-2.5"><TxState state={r.state} /></td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">{r.initiated_by}</td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">{r.fund ?? '—'}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-slate-400">{r.mpesa_receipt ?? '—'}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-[11px] tabular-nums text-slate-400">
                    {new Date(r.created_at).toLocaleString()}
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
