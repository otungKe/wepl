'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, Check, X, FileWarning, ClipboardList } from 'lucide-react'
import { verification, type EddCase, type TimelineEvent } from '@/lib/verification'
import { staffFirstName } from '@/lib/staff'
import { useCan } from '@/store/ops'

const KIND_LABELS: Record<string, string> = {
  proof_of_funds: 'Proof of funds',
  bank_statement: 'Bank statement',
  invoice: 'Invoice',
  receipt: 'Receipt',
  supporting_doc: 'Supporting document',
}

export default function EddCasePage() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const caseId = String(params.caseId)
  const [data, setData] = useState<EddCase | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    verification.eddCase(caseId).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [caseId])
  useEffect(() => { load() }, [load])

  const decide = async (action: 'approve' | 'reject') => {
    setErr(''); setBusy(true)
    try {
      const r = await verification.eddDecide(caseId, { action, ...(reason.trim() ? { reason: reason.trim() } : {}) })
      setData(r.data); setReason('')
    } catch (e) {
      setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.')
    } finally { setBusy(false) }
  }

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this case.</p>

  const canDecide = can('verification.decide')
  const decided = data.state === 'approved' || data.state === 'rejected'
  const docEntries = Object.entries(data.documents)

  return (
    <div className="mx-auto max-w-6xl">
      <button onClick={() => router.push('/verification')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Verification Centre
      </button>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Transaction review — {data.name}</h1>
        <StateChip state={data.state} />
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500 dark:bg-slate-800">{data.reference}</span>
      </div>
      <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
        <span className="font-mono">{data.phone_number}</span>
        {data.opened_at && <span>Opened {new Date(data.opened_at).toLocaleString()}</span>}
        {data.closed_at && <span>Closed {new Date(data.closed_at).toLocaleString()}</span>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Held movement">
            <dl className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
              <Field k="Movement" v={(data.subject.op_type ?? '—').replace(/_/g, ' ').toLowerCase()} />
              <Field k="Amount" v={data.subject.amount ? `KES ${data.subject.amount}` : '—'} mono />
              <Field k="Direction" v={(data.subject.direction ?? '—').toLowerCase()} />
              <Field k="Hold status" v={(data.subject.status ?? '—').toLowerCase()} />
              {data.subject.recipient_phone && <Field k="Recipient" v={data.subject.recipient_phone} mono />}
            </dl>
            {data.subject.reason && (
              <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
                Held because: {data.subject.reason}
              </p>
            )}
          </Card>

          <Card title="Requested evidence">
            <div className="mb-3 flex flex-wrap gap-1.5">
              {data.requested_items.map((k) => (
                <span key={k} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {KIND_LABELS[k] ?? k}
                </span>
              ))}
            </div>
            {data.customer_note && (
              <p className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
                Customer note: “{data.customer_note}”
              </p>
            )}
            {docEntries.length === 0 ? (
              <p className="flex items-center gap-2 text-sm text-slate-400">
                <ClipboardList className="h-4 w-4" /> Nothing submitted yet — the member has been asked.
              </p>
            ) : docEntries.map(([kind, versions]) => (
              <div key={kind} className="mb-2">
                <p className="mb-1 text-xs font-medium text-slate-500">{KIND_LABELS[kind] ?? kind} · {versions.length} version{versions.length === 1 ? '' : 's'}</p>
                <div className="space-y-1.5">
                  {versions.map((v, i) => (
                    <div key={v.version} className="flex items-center gap-3 rounded-lg border border-slate-100 p-2 text-xs dark:border-slate-800">
                      {v.url ? (
                        <a href={v.url} target="_blank" rel="noreferrer" className="font-medium text-blue-600 hover:underline dark:text-blue-400">
                          Open v{v.version}
                        </a>
                      ) : (
                        <span className="flex items-center gap-1 text-slate-400"><FileWarning className="h-3.5 w-3.5" /> v{v.version} not in storage</span>
                      )}
                      {i === 0 && <span className="rounded bg-blue-100 px-1 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-500/10 dark:text-blue-400">current</span>}
                      <span className="text-slate-400">{new Date(v.at).toLocaleString()}</span>
                      {v.sha256 && <span className="truncate font-mono text-[10px] text-slate-400">sha256 {v.sha256.slice(0, 16)}…</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </Card>

          <Card title="Event log">
            {data.timeline.length === 0
              ? <p className="text-sm text-slate-400">No events recorded.</p>
              : <ul className="space-y-2.5">{data.timeline.map((e) => <Row key={e.seq} e={e} />)}</ul>}
          </Card>
        </div>

        <div className="space-y-5">
          {canDecide && decided ? (
            <Card title="Decision">
              <p className={`rounded-lg px-3 py-2 text-sm font-medium ${
                data.state === 'approved'
                  ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
                  : 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400'}`}>
                {data.state === 'approved' ? 'Cleared — the member can retry within 72 hours.' : 'Refused — the member has been notified.'}
              </p>
            </Card>
          ) : canDecide ? (
            <Card title="Decision">
              {err && <p className="mb-2 text-sm text-red-500">{err}</p>}
              <p className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
                Clearing issues a single-use allowance for this amount, valid 72 hours —
                the member retries the transaction themselves. Hard (deny) limits are never bypassed.
              </p>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                placeholder="Reason (required to refuse; optional note when clearing)"
                className="mb-2 w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
              <div className="grid grid-cols-2 gap-2">
                <button disabled={busy} onClick={() => decide('approve')}
                  className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60">
                  <Check className="h-4 w-4" /> Clear
                </button>
                <button disabled={busy || !reason.trim()} onClick={() => decide('reject')}
                  className="flex items-center justify-center gap-2 rounded-lg bg-red-600 py-2.5 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50">
                  <X className="h-4 w-4" /> Refuse
                </button>
              </div>
            </Card>
          ) : (
            <Card title="Decision"><p className="text-sm text-slate-500">You have read-only access to this case.</p></Card>
          )}
        </div>
      </div>
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-slate-400">{title}</h2>
      {children}
    </div>
  )
}
function Field({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[11px] text-slate-400">{k}</p>
      <p className={`text-sm text-slate-800 dark:text-slate-100 ${mono ? 'font-mono text-[13px]' : ''}`}>{v}</p>
    </div>
  )
}
function StateChip({ state }: { state: string }) {
  const m: Record<string, [string, string]> = {
    requires_info: ['awaiting documents', 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400'],
    submitted: ['ready for review', 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400'],
    approved: ['cleared', 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'],
    rejected: ['refused', 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400'],
  }
  const [label, cls] = m[state] ?? [state, 'bg-slate-100 text-slate-600']
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{label}</span>
}

const EVENT_LABELS: Record<string, string> = {
  'case.opened': 'Review opened (movement held)',
  'submission.received': 'Customer submitted evidence',
  'review.approved': 'Cleared',
  'review.rejected': 'Refused',
}

function Row({ e }: { e: TimelineEvent }) {
  const color = e.actor_kind === 'staff' ? 'bg-blue-500'
    : e.actor_kind === 'customer' ? 'bg-emerald-500' : 'bg-slate-400'
  const actor = e.actor_kind === 'staff' && e.actor.includes('@') ? staffFirstName(e.actor) : e.actor
  const detail = typeof e.payload?.reason === 'string' && e.payload.reason ? `“${e.payload.reason}”` : ''
  return (
    <li className="flex items-start gap-2.5 text-xs">
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${color}`} />
      <div className="min-w-0">
        <span className="font-medium text-slate-700 dark:text-slate-200">{EVENT_LABELS[e.type] ?? e.type}</span>
        <span className="text-slate-400"> · {actor}</span>
        {detail && <span className="block truncate text-slate-400">{detail}</span>}
        <span className="block font-mono text-[10px] text-slate-400">#{e.seq} · {new Date(e.at).toLocaleString()}</span>
      </div>
    </li>
  )
}
