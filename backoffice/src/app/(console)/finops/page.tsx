'use client'
// FinOps — the payments desk (OP-1). Two queues: stuck payouts (money going out
// that stalled, with recovery levers) and failed payouts (audit trail). Every
// lever routes through the server's PaymentOpsService and is step-up gated.
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Banknote, Loader2, RefreshCw, XCircle, AlertTriangle, Info, Send } from 'lucide-react'
import { finops, type FinopsQueues, type FinopsRow } from '@/lib/platform'
import { apiError } from '@/lib/ops'
import { useCan } from '@/store/ops'
import { useStepUp } from '@/components/StepUp'
import { TxState } from '@/components/TxState'

export default function FinopsPage() {
  const can = useCan()
  const stepUp = useStepUp()
  const canAct = can('finops.retry')
  const [minutes, setMinutes] = useState(30)
  const [data, setData] = useState<FinopsQueues | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [tab, setTab] = useState<'stuck' | 'failed'>('stuck')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [msg, setMsg] = useState('')
  const [failFor, setFailFor] = useState<FinopsRow | null>(null)
  const [reason, setReason] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    finops.queues(minutes).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [minutes])
  useEffect(() => { load() }, [load])

  const run = async (ft: FinopsRow, action: 'requery' | 'mark_failed' | 'retry_payout', why = '') => {
    setMsg('')
    let token: string
    try { token = await stepUp.request() } catch { return }
    setBusyId(ft.id)
    try {
      const r = await finops.action(ft.id, action, why, token)
      setMsg(`#${ft.id}: ${r.data.result.detail}`)
      setFailFor(null); setReason('')
      load()
    } catch (e) { setMsg(apiError(e, 'Action failed.')) }
    finally { setBusyId(null) }
  }

  return (
    <div className="mx-auto max-w-6xl">
      {stepUp.modal}
      {failFor && (
        <ReasonModal
          row={failFor} reason={reason} setReason={setReason}
          onCancel={() => { setFailFor(null); setReason('') }}
          onConfirm={() => run(failFor, 'mark_failed', reason.trim())}
        />
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Banknote className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Financial Operations</h1>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <span className="text-slate-400">Stuck after</span>
          <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 outline-none dark:border-slate-700 dark:bg-slate-900">
            {[0, 15, 30, 60, 180].map((m) => <option key={m} value={m}>{m === 0 ? 'any age' : `${m} min`}</option>)}
          </select>
          <button onClick={load} className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {data && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          <Stat label="Stuck payouts" value={data.counts.stuck_payouts} tone="warn" />
          <Stat label="Failed payouts" value={data.counts.failed_payouts} tone="bad" />
          <Stat label="Stuck pay-ins" value={data.counts.stuck_payins} tone="muted" hint="auto-recovering" />
        </div>
      )}

      {!canAct && (
        <p className="mb-4 flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
          <Info className="h-3.5 w-3.5" /> You can view the desk but not act on movements (needs finops.retry).
        </p>
      )}
      {msg && <p className="mb-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">{msg}</p>}

      <div className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
        <Tab active={tab === 'stuck'} onClick={() => setTab('stuck')} label={`Stuck payouts${data ? ` (${data.counts.stuck_payouts})` : ''}`} />
        <Tab active={tab === 'failed'} onClick={() => setTab('failed')} label={`Failed${data ? ` (${data.counts.failed_payouts})` : ''}`} />
      </div>

      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load the desk.</p>}

      {status === 'ready' && data && (
        <Queue
          rows={tab === 'stuck' ? data.stuck_payouts : data.failed_payouts}
          actionable={tab === 'stuck' && canAct}
          busyId={busyId}
          onRequery={(ft) => run(ft, 'requery')}
          onRetry={(ft) => run(ft, 'retry_payout')}
          onFail={(ft) => { setFailFor(ft); setReason('') }}
          emptyLabel={tab === 'stuck' ? 'No stuck payouts. The desk is clear.' : 'No failed payouts.'}
        />
      )}
    </div>
  )
}

function Queue({ rows, actionable, busyId, onRequery, onRetry, onFail, emptyLabel }: {
  rows: FinopsRow[]; actionable: boolean; busyId: number | null
  onRequery: (ft: FinopsRow) => void; onRetry: (ft: FinopsRow) => void
  onFail: (ft: FinopsRow) => void; emptyLabel: string
}) {
  if (rows.length === 0)
    return <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">{emptyLabel}</div>
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
      <table className="w-full min-w-[760px] text-sm">
        <thead>
          <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
            <th className="px-4 py-2.5 text-left font-semibold">Payout</th>
            <th className="px-4 py-2.5 text-right font-semibold">Amount (KES)</th>
            <th className="px-4 py-2.5 text-left font-semibold">State</th>
            <th className="px-4 py-2.5 text-left font-semibold">To</th>
            <th className="px-4 py-2.5 text-right font-semibold">Age</th>
            {actionable && <th className="px-4 py-2.5 text-right font-semibold">Levers</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
              <td className="px-4 py-2.5">
                <Link href={`/transactions/${r.id}`} className="block">
                  <span className="font-medium text-slate-800 dark:text-slate-100">{r.op_type.replace(/_/g, ' ').toLowerCase()}</span>
                  <span className="block font-mono text-[10px] text-slate-400">#{r.id}</span>
                </Link>
                {r.failure_reason && <span className="mt-0.5 block text-[11px] text-red-500">{r.failure_reason}</span>}
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">{r.amount}</td>
              <td className="px-4 py-2.5"><TxState state={r.state} /></td>
              <td className="px-4 py-2.5 font-mono text-[11px] text-slate-500">{r.recipient_phone || '—'}</td>
              <td className="px-4 py-2.5 text-right text-[11px] text-slate-400">{ago(r.created_at)}</td>
              {actionable && (
                <td className="px-4 py-2.5">
                  <div className="flex justify-end gap-1.5">
                    {r.conversation_id ? (
                      <button disabled={busyId === r.id} onClick={() => onRequery(r)}
                        title="Ask the rail for this payout's true state"
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                        {busyId === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Requery
                      </button>
                    ) : (
                      <button disabled={busyId === r.id} onClick={() => onRetry(r)}
                        title="Re-dispatch — this payout never reached the rail"
                        className="inline-flex items-center gap-1 rounded-lg border border-blue-200 px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-500/30 dark:text-blue-400 dark:hover:bg-blue-500/10">
                        {busyId === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Re-send
                      </button>
                    )}
                    <button disabled={busyId === r.id} onClick={() => onFail(r)}
                      className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-500/30 dark:text-red-400 dark:hover:bg-red-500/10">
                      <XCircle className="h-3.5 w-3.5" /> Fail
                    </button>
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ReasonModal({ row, reason, setReason, onCancel, onConfirm }: {
  row: FinopsRow; reason: string; setReason: (v: string) => void; onCancel: () => void; onConfirm: () => void
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-500" />
          <h2 className="text-base font-semibold">Mark payout #{row.id} failed</h2>
        </div>
        <p className="mb-3 text-sm text-slate-500">
          The rail will be re-queried first — if it actually succeeded, the payout is finalised instead. Reserved funds are restored on failure. State the reason:
        </p>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} autoFocus
          placeholder="e.g. Rail confirms the B2C never left the float; member re-paid manually."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950" />
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-lg px-3.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">Cancel</button>
          <button onClick={onConfirm} disabled={reason.trim().length < 4}
            className="rounded-lg bg-red-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50">Continue</button>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, tone, hint }: { label: string; value: number; tone: 'warn' | 'bad' | 'muted'; hint?: string }) {
  const tones = {
    warn: 'text-amber-600 dark:text-amber-400',
    bad: 'text-red-600 dark:text-red-400',
    muted: 'text-slate-500 dark:text-slate-400',
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tones[tone]}`}>{value}</p>
      {hint && <p className="text-[10px] text-slate-400">{hint}</p>}
    </div>
  )
}

function Tab({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button onClick={onClick}
      className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
        active ? 'border-blue-600 text-blue-600 dark:text-blue-400'
               : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
      {label}
    </button>
  )
}

function ago(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 60) return `${mins}m`
  const h = Math.floor(mins / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}
