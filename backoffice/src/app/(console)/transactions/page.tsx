'use client'
// Transactions — an inquiry, not a listing. Nothing loads until the operator
// searches; then only the movements matching their criteria (paginated). At
// ledger scale you query for what you need, you don't scroll the whole book.
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeftRight, Search, Loader2, Download } from 'lucide-react'
import { transactions, type TxRow, type TxFilters } from '@/lib/platform'
import { downloadCsv } from '@/lib/ops'
import { useCan } from '@/store/ops'
import { TxState } from '@/components/TxState'

const STATES = [
  { value: 'all', label: 'Any state' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'PROCESSING', label: 'Processing' },
  { value: 'SUCCESS', label: 'Success' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'REVERSED', label: 'Reversed' },
]

export default function TransactionsInquiry() {
  const can = useCan()
  // Form fields.
  const [state, setState] = useState('all')
  const [opType, setOpType] = useState('')
  const [q, setQ] = useState('')
  const [account, setAccount] = useState('')
  const [amtMin, setAmtMin] = useState('')
  const [amtMax, setAmtMax] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [opTypes, setOpTypes] = useState<{ value: string; label: string }[]>([])
  // Results.
  const [submitted, setSubmitted] = useState<TxFilters | null>(null)
  const [rows, setRows] = useState<TxRow[]>([])
  const [count, setCount] = useState(0)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [err, setErr] = useState('')

  // One cheap call on mount (no criteria → no query) just to populate the
  // operation-type dropdown; results stay idle.
  useEffect(() => {
    transactions.list({}).then((r) => setOpTypes(r.data.op_types)).catch(() => {})
  }, [])

  const buildParams = (): TxFilters => ({
    ...(state !== 'all' ? { state } : {}),
    ...(opType ? { op_type: opType } : {}),
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(account.trim() ? { account: account.trim() } : {}),
    ...(amtMin.trim() ? { min: amtMin.trim() } : {}),
    ...(amtMax.trim() ? { max: amtMax.trim() } : {}),
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  })

  const hasCriteria = state !== 'all' ||
    !!(opType || q.trim() || account.trim() || amtMin.trim() || amtMax.trim() || dateFrom || dateTo)

  const run = (params: TxFilters) => {
    setStatus('loading'); setErr('')
    transactions.list(params)
      .then((r) => { setRows(r.data.results); setCount(r.data.count); setStatus('ready') })
      .catch(() => setStatus('error'))
  }

  const onSearch = (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!hasCriteria) { setErr('Enter at least one search criterion.'); return }
    const p = buildParams()
    setSubmitted(p)
    run(p)
  }

  const onClear = () => {
    setState('all'); setOpType(''); setQ(''); setAccount(''); setAmtMin(''); setAmtMax('')
    setDateFrom(''); setDateTo(''); setSubmitted(null); setRows([]); setCount(0)
    setStatus('idle'); setErr('')
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex items-center gap-3">
        <ArrowLeftRight className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Transaction inquiry</h1>
      </div>

      {/* Inquiry form — the registry returns only what these ask for. */}
      <form onSubmit={onSearch} className="mb-5 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Account code">
            <input value={account} onChange={(e) => setAccount(e.target.value)}
              placeholder="1000, SL-CONTRIBUTION-18-U55…" className={`${inputCls} font-mono`} />
          </Field>
          <Field label="Search">
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Phone, receipt, WEPL-TXN ref…" className={inputCls} />
          </Field>
          <Field label="Operation type">
            <select value={opType} onChange={(e) => setOpType(e.target.value)} className={inputCls}>
              <option value="">Any type</option>
              {opTypes.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Field>
          <Field label="From date"><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={inputCls} /></Field>
          <Field label="To date"><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={inputCls} /></Field>
          <Field label="State">
            <select value={state} onChange={(e) => setState(e.target.value)} className={inputCls}>
              {STATES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="Min amount (KES)"><input inputMode="decimal" value={amtMin} onChange={(e) => setAmtMin(e.target.value)} placeholder="0" className={inputCls} /></Field>
          <Field label="Max amount (KES)"><input inputMode="decimal" value={amtMax} onChange={(e) => setAmtMax(e.target.value)} placeholder="∞" className={inputCls} /></Field>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <button type="submit" disabled={status === 'loading'}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {status === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Search
          </button>
          <button type="button" onClick={onClear}
            className="rounded-lg px-3.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
            Clear
          </button>
          {submitted && can('reporting.export') && (
            <button type="button" onClick={() => downloadCsv('/ops/exports/transactions/', submitted)}
              className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
              <Download className="h-4 w-4" /> Export results
            </button>
          )}
          {err && <span className="text-sm text-red-600 dark:text-red-400">{err}</span>}
        </div>
      </form>

      {status === 'idle' && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          Enter search criteria above and select <span className="font-medium">Search</span> to inquire.
        </div>
      )}
      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t run the inquiry.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          No movements match these criteria.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <>
          <div className="mb-2 text-xs text-slate-400">
            {count} match{count === 1 ? '' : 'es'}{rows.length < count ? ` · showing first ${rows.length}` : ''}
          </div>
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
                        <span className="font-medium text-slate-800 dark:text-slate-100">{r.op_type.replace(/_/g, ' ').toLowerCase()}</span>
                        <span className="block font-mono text-[10px] text-slate-400">{r.reference}</span>
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
        </>
      )}
    </div>
  )
}

const inputCls =
  'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</span>
      {children}
    </label>
  )
}
