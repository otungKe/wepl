'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, Check, X, Upload, FileWarning, UserCheck, UserMinus, StickyNote } from 'lucide-react'
import { verification, type CaseDetail, type DocRef, type Decision, type TimelineEvent } from '@/lib/verification'
import { useCan, useOpsStore } from '@/store/ops'

export default function VerificationCase() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const userId = String(params.userId)
  const me = useOpsStore((s) => s.me)
  const [data, setData] = useState<CaseDetail | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [reasonCode, setReasonCode] = useState('')
  const [items, setItems] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    verification.case(userId).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [userId])
  useEffect(() => { load() }, [load])

  const fail = (e: unknown) =>
    setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.')

  const decide = async (body: Decision) => {
    setErr(''); setBusy(true)
    try { const r = await verification.decide(userId, body); setData(r.data); setReason(''); setReasonCode(''); setItems([]) }
    catch (e) { fail(e) }
    finally { setBusy(false) }
  }

  const assign = async (action: 'claim' | 'release') => {
    setErr(''); setBusy(true)
    try { const r = await verification.assign(userId, action); setData(r.data) }
    catch (e) { fail(e) }
    finally { setBusy(false) }
  }

  const addNote = async () => {
    if (!note.trim()) return
    setErr(''); setBusy(true)
    try { const r = await verification.note(userId, note.trim()); setData(r.data); setNote('') }
    catch (e) { fail(e) }
    finally { setBusy(false) }
  }

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this case.</p>

  const a = data.applicant
  const canDecide = can('verification.decide')

  return (
    <div className="mx-auto max-w-6xl">
      <button onClick={() => router.push('/verification')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Queue
      </button>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{String(a.given_names ?? '')} {String(a.surname ?? '')}</h1>
        <StatusChip status={data.status} />
        <span className="font-mono text-xs text-slate-400">{data.phone_number}</span>
        {data.age_hours != null && <span className="text-xs text-slate-400">· submitted {Math.round(data.age_hours)}h ago</span>}
        <span className="ml-auto flex items-center gap-2">
          {data.assignee && (
            <span className="text-xs text-slate-500">
              Working: <b className="text-slate-700 dark:text-slate-200">{data.assignee}</b>
            </span>
          )}
          {canDecide && data.status === 'pending' && (
            data.assignee === me?.email ? (
              <button disabled={busy} onClick={() => assign('release')}
                className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                <UserMinus className="h-3.5 w-3.5" /> Release
              </button>
            ) : !data.assignee ? (
              <button disabled={busy} onClick={() => assign('claim')}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500">
                <UserCheck className="h-3.5 w-3.5" /> Claim case
              </button>
            ) : null
          )}
        </span>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Documents + OCR */}
        <div className="space-y-5 lg:col-span-2">
          <Card title="Documents">
            <div className="grid gap-3 sm:grid-cols-3">
              <Doc label="ID front" doc={data.documents.id_front} />
              <Doc label="ID back" doc={data.documents.id_back} />
              <Doc label="Selfie" doc={data.documents.selfie} />
            </div>
          </Card>

          <Card title="Automated checks">
            <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
              <span>Checker: <b className="text-slate-700 dark:text-slate-200">{data.checks.provider || '—'}</b></span>
              <span>Result: <b className="text-slate-700 dark:text-slate-200">{data.checks.state || '—'}</b></span>
            </div>
            <OcrPanel ocr={data.checks.ocr} typed={{ id: String(a.id_number ?? ''), dob: String(a.date_of_birth ?? '') }} />
          </Card>

          {data.timeline.length > 0 && (
            <Card title="Case timeline">
              <ul className="space-y-2.5">
                {data.timeline.map((e) => <TimelineRow key={e.seq} e={e} />)}
              </ul>
            </Card>
          )}
        </div>

        {/* Applicant + decisions */}
        <div className="space-y-5">
          <Card title="Applicant">
            <dl className="space-y-1.5 text-sm">
              <Row k="ID number" v={String(a.id_number ?? '—')} mono />
              <Row k="KRA PIN" v={String(a.kra_pin ?? '—')} mono />
              <Row k="Date of birth" v={String(a.date_of_birth ?? '—')} />
              <Row k="Email" v={`${a.email ?? '—'}${a.email_verified ? ' ✓' : ''}`} />
              <Row k="County" v={String(a.county ?? '—')} />
              <Row k="Address" v={String(a.physical_address ?? '—')} />
              <Row k="Occupation" v={String(a.occupation ?? '—')} />
              <Row k="Income" v={String(a.expected_monthly_income ?? '—')} />
            </dl>
          </Card>

          {canDecide ? (
            <Card title="Decision">
              {err && <p className="mb-2 text-sm text-red-500">{err}</p>}
              <button disabled={busy} onClick={() => decide({ action: 'approve' })}
                className="mb-2 flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60">
                <Check className="h-4 w-4" /> Approve
              </button>

              <div className="mb-2 rounded-lg border border-slate-200 p-2.5 dark:border-slate-800">
                <select value={reasonCode} onChange={(e) => setReasonCode(e.target.value)}
                  className="mb-1.5 w-full rounded-md border border-slate-200 bg-transparent px-2 py-1.5 text-sm outline-none dark:border-slate-700 dark:bg-slate-900">
                  <option value="">Rejection reason…</option>
                  {data.rejection_reasons.map((r) => (
                    <option key={r.code} value={r.code}>{r.label}</option>
                  ))}
                </select>
                {reasonCode && reasonCode !== 'OTHER' && (
                  <p className="mb-1.5 rounded bg-slate-50 px-2 py-1.5 text-xs text-slate-500 dark:bg-slate-800/60">
                    Applicant sees: “{data.rejection_reasons.find((r) => r.code === reasonCode)?.customer_message}”
                  </p>
                )}
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                  placeholder={reasonCode === 'OTHER' ? 'Reason shown to the applicant (required)'
                    : reasonCode ? 'Internal detail (optional, not shown to the applicant)'
                    : 'Free-text reason shown to the applicant'}
                  className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-slate-400" />
                <button
                  disabled={busy || (reasonCode === 'OTHER' || !reasonCode ? !reason.trim() : false)}
                  onClick={() => decide({ action: 'reject',
                    ...(reasonCode ? { reason_code: reasonCode } : {}),
                    ...(reason.trim() ? { reason: reason.trim() } : {}) })}
                  className="mt-1 flex w-full items-center justify-center gap-2 rounded-md bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50">
                  <X className="h-4 w-4" /> Reject
                </button>
              </div>

              <div className="rounded-lg border border-slate-200 p-2.5 dark:border-slate-800">
                <p className="mb-1.5 text-xs font-medium text-slate-500">Request re-submission of:</p>
                <div className="mb-2 grid grid-cols-2 gap-1">
                  {Object.entries(data.resubmittable_items).map(([key, label]) => (
                    <label key={key} className="flex items-center gap-1.5 text-xs">
                      <input type="checkbox" checked={items.includes(key)}
                        onChange={(e) => setItems((s) => e.target.checked ? [...s, key] : s.filter((x) => x !== key))} />
                      {label}
                    </label>
                  ))}
                </div>
                <button disabled={busy || items.length === 0} onClick={() => decide({ action: 'request_resubmission', items })}
                  className="flex w-full items-center justify-center gap-2 rounded-md bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50">
                  <Upload className="h-4 w-4" /> Request re-submission
                </button>
              </div>
              {data.resubmission_requested.length > 0 && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  Outstanding: {data.resubmission_requested.join(', ')}
                </p>
              )}
            </Card>
          ) : (
            <Card title="Decision"><p className="text-sm text-slate-500">You have read-only access to this case.</p></Card>
          )}

          <Card title="Internal notes">
            <div className="mb-2 flex gap-1.5">
              <input value={note} onChange={(e) => setNote(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addNote() }}
                placeholder="Add a note (staff only)…"
                className="min-w-0 flex-1 rounded-md border border-slate-200 bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
              <button disabled={busy || !note.trim()} onClick={addNote}
                className="rounded-md bg-slate-800 px-2.5 text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-700 dark:hover:bg-slate-600">
                <StickyNote className="h-4 w-4" />
              </button>
            </div>
            {data.notes.length === 0 ? (
              <p className="text-xs text-slate-400">No notes yet.</p>
            ) : (
              <ul className="space-y-2">
                {data.notes.map((n) => (
                  <li key={n.id} className="rounded-lg bg-slate-50 p-2 text-xs dark:bg-slate-800/60">
                    <p className="text-slate-700 dark:text-slate-200">{n.body}</p>
                    <p className="mt-1 text-[10px] text-slate-400">{n.author} · {new Date(n.at).toLocaleString()}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
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
function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-400">{k}</dt>
      <dd className={`text-right text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>{v}</dd>
    </div>
  )
}
function StatusChip({ status }: { status: string }) {
  const m: Record<string, string> = {
    pending: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    approved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
  }
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${m[status] ?? 'bg-slate-100 text-slate-600'}`}>{status}</span>
}
function Doc({ label, doc }: { label: string; doc: DocRef }) {
  const versions = doc.versions ?? []
  const prior = versions.filter((v) => v.url).slice(1) // newest first; [0] is current
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">
        {label}
        {versions.length > 1 && (
          <span className="ml-1.5 rounded bg-slate-100 px-1 py-0.5 font-mono text-[10px] text-slate-500 dark:bg-slate-800">
            v{versions[0].version}
          </span>
        )}
      </p>
      {doc.available && doc.url ? (
        <a href={doc.url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={doc.url} alt={label} className="h-32 w-full object-cover" />
        </a>
      ) : (
        <div className="flex h-32 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-300 text-center text-[11px] text-slate-400 dark:border-slate-700">
          <FileWarning className="h-5 w-5" /> not in storage
        </div>
      )}
      {prior.length > 0 && (
        <p className="mt-1 text-[11px] text-slate-400">
          Earlier:{' '}
          {prior.map((v, i) => (
            <a key={v.version} href={v.url!} target="_blank" rel="noreferrer"
              className="text-blue-600 hover:underline dark:text-blue-400">
              {i > 0 && ', '}v{v.version}
            </a>
          ))}
        </p>
      )}
    </div>
  )
}

const EVENT_LABELS: Record<string, string> = {
  'case.opened': 'Case opened',
  'case.backfilled': 'Case opened (migrated)',
  'submission.received': 'KYC submitted',
  'email.verified': 'Email verified',
  'checks.completed': 'Automated checks completed',
  'review.approved': 'Approved',
  'review.rejected': 'Rejected',
  'review.info_requested': 'Re-submission requested',
  'case.resubmit': 'Re-submitted',
}

function TimelineRow({ e }: { e: TimelineEvent }) {
  const kindColor = e.actor_kind === 'staff' ? 'bg-blue-500'
    : e.actor_kind === 'customer' ? 'bg-emerald-500' : 'bg-slate-400'
  const detail = [
    typeof e.payload?.reason === 'string' && e.payload.reason ? `“${e.payload.reason}”` : null,
    Array.isArray(e.payload?.items) && e.payload.items.length ? `items: ${(e.payload.items as string[]).join(', ')}` : null,
    typeof e.payload?.kind === 'string' ? e.payload.kind.replace(/_/g, ' ') : null,
  ].filter(Boolean).join(' · ')
  return (
    <li className="flex items-start gap-2.5 text-xs">
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${kindColor}`} />
      <div className="min-w-0">
        <span className="font-medium text-slate-700 dark:text-slate-200">
          {EVENT_LABELS[e.type] ?? e.type}
        </span>
        <span className="text-slate-400"> · {e.actor}</span>
        {detail && <span className="block truncate text-slate-400">{detail}</span>}
        <span className="block font-mono text-[10px] text-slate-400">
          #{e.seq} · {new Date(e.at).toLocaleString()}
        </span>
      </div>
    </li>
  )
}
function OcrPanel({ ocr, typed }: { ocr: Record<string, unknown>; typed: { id: string; dob: string } }) {
  if (!ocr || Object.keys(ocr).length === 0) return <p className="text-sm text-slate-400">No OCR result — verify the documents manually.</p>
  const flag = (m: unknown) => m === true ? <span className="text-emerald-600 dark:text-emerald-400">✓ matches</span>
    : m === false ? <span className="font-semibold text-red-600 dark:text-red-400">✗ MISMATCH</span>
    : <span className="text-slate-400">— not read</span>
  return (
    <dl className="space-y-1 text-sm">
      <div className="flex justify-between"><dt className="text-slate-400">Kenyan ID detected</dt>
        <dd>{ocr.detected ? <span className="text-emerald-600 dark:text-emerald-400">yes</span> : <span className="text-red-600 dark:text-red-400">no</span>}</dd></div>
      <div className="flex justify-between"><dt className="text-slate-400">ID number ({typed.id})</dt><dd>{flag((ocr as Record<string, unknown>).id_number_match)}</dd></div>
      <div className="flex justify-between"><dt className="text-slate-400">Date of birth</dt><dd>{flag((ocr as Record<string, unknown>).dob_match)}</dd></div>
    </dl>
  )
}
