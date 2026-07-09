'use client'
// Approvals — the maker-checker inbox (OP-3 Part 2). A checker reviews pending
// dual-control requests and approves (which executes the flagged action,
// attributed to both operators) or rejects. Deciding is step-up gated and a
// request can never be approved by the operator who raised it.
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { CheckSquare, Loader2, Check, X, Clock } from 'lucide-react'
import { approvals, type ApprovalRow } from '@/lib/platform'
import { apiError } from '@/lib/ops'
import { useCan } from '@/store/ops'
import { useStepUp } from '@/components/StepUp'

const TABS = ['pending', 'approved', 'rejected', 'all']

export default function ApprovalsPage() {
  const can = useCan()
  const stepUp = useStepUp()
  const canDecide = can('approvals.decide')
  const [tab, setTab] = useState('pending')
  const [rows, setRows] = useState<ApprovalRow[]>([])
  const [pending, setPending] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [msg, setMsg] = useState('')
  const [rejectFor, setRejectFor] = useState<ApprovalRow | null>(null)
  const [note, setNote] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    approvals.list(tab).then((r) => {
      setRows(r.data.results); setPending(r.data.counts.pending); setStatus('ready')
    }).catch(() => setStatus('error'))
  }, [tab])
  useEffect(() => { load() }, [load])

  const decide = async (a: ApprovalRow, decision: 'approve' | 'reject', why = '') => {
    setMsg('')
    let token: string
    try { token = await stepUp.request() } catch { return }
    setBusyId(a.id)
    try {
      const r = await approvals.decide(a.id, decision, why, token)
      setMsg(`#${a.id} ${r.data.status.toLowerCase()}.`)
      setRejectFor(null); setNote(''); load()
    } catch (e) { setMsg(apiError(e, 'Decision failed.')) }
    finally { setBusyId(null) }
  }

  return (
    <div className="mx-auto max-w-5xl">
      {stepUp.modal}
      {rejectFor && (
        <NoteModal
          row={rejectFor} note={note} setNote={setNote}
          onCancel={() => { setRejectFor(null); setNote('') }}
          onConfirm={() => decide(rejectFor, 'reject', note.trim())}
        />
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <CheckSquare className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Approvals</h1>
        {pending > 0 && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">{pending} pending</span>}
      </div>

      {!canDecide && (
        <p className="mb-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
          You can view the queue but not decide (needs approvals.decide).
        </p>
      )}
      {msg && <p className="mb-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">{msg}</p>}

      <div className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium capitalize ${
              tab === t ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                        : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
            {t}
          </button>
        ))}
      </div>

      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load approvals.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          Nothing here.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <ul className="space-y-3">
          {rows.map((a) => (
            <li key={a.id} className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-800 dark:text-slate-100">{a.summary || a.action}</span>
                    <Status status={a.status} />
                  </div>
                  <p className="mt-1 text-sm text-slate-500">{a.reason}</p>
                  <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-slate-400">
                    <span>by <b className="text-slate-500 dark:text-slate-300">{a.requested_by}</b></span>
                    <span>{new Date(a.requested_at).toLocaleString()}</span>
                    {a.target_type === 'financial_transaction' && a.target_id && (
                      <Link href={`/transactions/${a.target_id}`} className="text-blue-600 hover:underline dark:text-blue-400">movement #{a.target_id}</Link>
                    )}
                    {a.status === 'PENDING' && <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> expires {new Date(a.expires_at).toLocaleString()}</span>}
                    {a.decided_by && <span>decided by <b className="text-slate-500 dark:text-slate-300">{a.decided_by}</b></span>}
                  </div>
                  {a.decision_note && <p className="mt-1 text-xs italic text-slate-400">“{a.decision_note}”</p>}
                </div>
                {canDecide && a.status === 'PENDING' && (
                  <div className="flex gap-1.5">
                    <button disabled={busyId === a.id} onClick={() => decide(a, 'approve')}
                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                      {busyId === a.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Approve
                    </button>
                    <button disabled={busyId === a.id} onClick={() => setRejectFor(a)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                      <X className="h-3.5 w-3.5" /> Reject
                    </button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function NoteModal({ row, note, setNote, onCancel, onConfirm }: {
  row: ApprovalRow; note: string; setNote: (v: string) => void; onCancel: () => void; onConfirm: () => void
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-base font-semibold">Reject request #{row.id}</h2>
        <p className="mb-3 text-sm text-slate-500">{row.summary || row.action}. Add a note (optional):</p>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} autoFocus
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950" />
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-lg px-3.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">Cancel</button>
          <button onClick={onConfirm} className="rounded-lg bg-red-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-red-700">Reject</button>
        </div>
      </div>
    </div>
  )
}

function Status({ status }: { status: string }) {
  const map: Record<string, string> = {
    PENDING: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',
    APPROVED: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400',
    REJECTED: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
    EXPIRED: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
    FAILED: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
  }
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${map[status] ?? map.REJECTED}`}>{status.toLowerCase()}</span>
}
