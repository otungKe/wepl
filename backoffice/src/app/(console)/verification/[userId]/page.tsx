'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  Loader2, ArrowLeft, Check, X, Upload, FileWarning, UserCheck, UserMinus,
  StickyNote, ClipboardList,
} from 'lucide-react'
import { verification, type CaseDetail, type DocRef, type Decision, type TimelineEvent } from '@/lib/verification'
import { staffFirstName } from '@/lib/staff'
import { useCan, useOpsStore } from '@/store/ops'

type Tab = 'overview' | 'documents' | 'timeline' | 'notes'

export default function VerificationCase() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const me = useOpsStore((s) => s.me)
  const userId = String(params.userId)
  const [data, setData] = useState<CaseDetail | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [tab, setTab] = useState<Tab>('overview')
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'approve' | 'reject' | 'resubmit'>('approve')
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
  const docCount = ['id_front', 'id_back', 'selfie']
    .reduce((n, k) => n + (data.documents[k as keyof typeof data.documents]?.versions?.length ?? 0), 0)

  const TABS: { key: Tab; label: string; count?: number }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'documents', label: 'Documents', count: docCount },
    { key: 'timeline', label: 'Event log', count: data.timeline.length },
    { key: 'notes', label: 'Notes', count: data.notes.length },
  ]

  return (
    <div className="mx-auto max-w-6xl">
      <button onClick={() => router.push('/verification')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Verification Centre
      </button>

      {/* Case header */}
      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{String(a.given_names ?? '')} {String(a.surname ?? '')}</h1>
        <StatusChip status={data.status} />
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500 dark:bg-slate-800">{data.reference}</span>
        <span className="ml-auto flex items-center gap-2">
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

      {/* Meta strip */}
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-400">
        <span className="font-mono">{data.phone_number}</span>
        {data.case_opened_at && <span>Opened {new Date(data.case_opened_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</span>}
        {data.age_hours != null && <span>Submitted {Math.round(data.age_hours)}h ago</span>}
        {data.attempts > 1 && <span>Attempt <b className="text-slate-600 dark:text-slate-300">{data.attempts}</b></span>}
        {data.case_closed_at && <span>Closed {new Date(data.case_closed_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</span>}
        {data.assignee && <span>Working: <b className="text-slate-600 dark:text-slate-300">{staffFirstName(data.assignee)}</b></span>}
        {data.sla && <SlaChip sla={data.sla} />}
      </div>

      {/* Tabs */}
      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
            {t.label}
            {t.count != null && t.count > 0 && (
              <span className="rounded-full bg-slate-100 px-1.5 text-[10px] font-semibold text-slate-500 dark:bg-slate-800">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Main pane */}
        <div className="space-y-5 lg:col-span-2">
          {tab === 'overview' && <Overview data={data} />}
          {tab === 'documents' && <Documents data={data} />}
          {tab === 'timeline' && (
            <Card title="Event log">
              {data.timeline.length === 0
                ? <p className="text-sm text-slate-400">No events recorded.</p>
                : <ul className="space-y-2.5">{data.timeline.map((e) => <TimelineRow key={e.seq} e={e} />)}</ul>}
            </Card>
          )}
          {tab === 'notes' && (
            <Card title="Internal notes">
              <div className="mb-3 flex gap-1.5">
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
                    <li key={n.id} className="rounded-lg bg-slate-50 p-2.5 text-xs dark:bg-slate-800/60">
                      <p className="text-sm text-slate-700 dark:text-slate-200">{n.body}</p>
                      <p className="mt-1 text-[10px] text-slate-400">{staffFirstName(n.author) || n.author} · {new Date(n.at).toLocaleString()}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>

        {/* Right rail */}
        <div className="space-y-5">
          {canDecide ? (
            <Card title="Decision">
              {err && <p className="mb-2 text-sm text-red-500">{err}</p>}

              {/* Mode selector */}
              <div className="mb-3 grid grid-cols-3 gap-1.5">
                <ModeBtn active={mode === 'approve'} activeCls="border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
                  onClick={() => setMode('approve')} icon={<Check className="h-4 w-4" />} label="Approve" />
                <ModeBtn active={mode === 'reject'} activeCls="border-red-500 bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400"
                  onClick={() => setMode('reject')} icon={<X className="h-4 w-4" />} label="Reject" />
                <ModeBtn active={mode === 'resubmit'} activeCls="border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400"
                  onClick={() => setMode('resubmit')} icon={<Upload className="h-4 w-4" />} label="Re-submit" />
              </div>

              {mode === 'approve' && (
                <p className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
                  Grants full (Tier-1) access and notifies the applicant.
                </p>
              )}

              {mode === 'reject' && (
                <div className="mb-3">
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
                    className="w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                </div>
              )}

              {mode === 'resubmit' && (
                <div className="mb-3">
                  <p className="mb-1.5 text-xs font-medium text-slate-500">Ask the applicant to re-provide:</p>
                  <div className="grid grid-cols-2 gap-1">
                    {Object.entries(data.resubmittable_items).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-1.5 text-xs">
                        <input type="checkbox" checked={items.includes(key)}
                          onChange={(e) => setItems((s) => e.target.checked ? [...s, key] : s.filter((x) => x !== key))} />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <button
                disabled={busy
                  || (mode === 'reject' && (reasonCode === 'OTHER' || !reasonCode ? !reason.trim() : false))
                  || (mode === 'resubmit' && items.length === 0)}
                onClick={() => {
                  if (mode === 'approve') decide({ action: 'approve' })
                  else if (mode === 'reject') decide({ action: 'reject',
                    ...(reasonCode ? { reason_code: reasonCode } : {}),
                    ...(reason.trim() ? { reason: reason.trim() } : {}) })
                  else decide({ action: 'request_resubmission', items })
                }}
                className={`flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white disabled:opacity-50 ${
                  mode === 'approve' ? 'bg-emerald-600 hover:bg-emerald-500'
                  : mode === 'reject' ? 'bg-red-600 hover:bg-red-500'
                  : 'bg-blue-600 hover:bg-blue-500'}`}>
                Submit decision
              </button>
            </Card>
          ) : (
            <Card title="Decision"><p className="text-sm text-slate-500">You have read-only access to this case.</p></Card>
          )}

          <CaseSummary data={data} />
          <TasksAndEvents data={data} onViewLog={() => setTab('timeline')} />
        </div>
      </div>
    </div>
  )
}

/* ── Overview tab ─────────────────────────────────────────────────────── */

function Overview({ data }: { data: CaseDetail }) {
  const a = data.applicant
  const v = (x: unknown) => (x == null || x === '' ? '—' : String(x))
  return (
    <>
      <ProgressStepper data={data} />

      <Card title="Applicant">
        <Section label="Personal information">
          <Field k="Given names" v={v(a.given_names)} />
          <Field k="Surname" v={v(a.surname)} />
          <Field k="Date of birth" v={v(a.date_of_birth)} />
          <Field k="Email address" v={`${v(a.email)}${a.email_verified ? ' ✓' : ''}`} />
        </Section>
        <Section label="Identity">
          <Field k="National ID number" v={v(a.id_number)} mono />
          <Field k="KRA PIN" v={v(a.kra_pin)} mono />
        </Section>
        <Section label="Address information">
          <Field k="County" v={v(a.county)} />
          <Field k="Physical address" v={v(a.physical_address)} />
        </Section>
        <Section label="Financial profile" last>
          <Field k="Occupation" v={v(a.occupation)} />
          <Field k="Source of income" v={v(a.source_of_income)} />
          <Field k="Income band" v={v(a.expected_monthly_income)} />
        </Section>
      </Card>

      <Card title="Requested information">
        <RequestedInfo data={data} />
      </Card>

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
        <div className="mt-2 flex justify-between border-t border-slate-100 pt-2 text-sm dark:border-slate-800">
          <span className="text-slate-400">Duplicate check (email)</span>
          {data.checks.duplicate_email
            ? <span className="font-semibold text-red-600 dark:text-red-400">✗ used by another profile</span>
            : <span className="text-emerald-600 dark:text-emerald-400">✓ no matches</span>}
        </div>
        <ChecksBanner data={data} />
      </Card>
    </>
  )
}

function ChecksBanner({ data }: { data: CaseDetail }) {
  if (!data.checks.checked_at) {
    return (
      <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
        Automated checks run after the applicant confirms their email address.
      </p>
    )
  }
  const ocr = data.checks.ocr as Record<string, unknown>
  const attention = data.checks.duplicate_email || ocr?.mismatch === true
    || ocr?.id_number_match === false || ocr?.dob_match === false
  return attention ? (
    <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700 dark:bg-red-500/10 dark:text-red-400">
      One or more signals need attention — review the documents carefully before deciding.
    </p>
  ) : (
    <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
      Automated checks complete — manual review required.
    </p>
  )
}

/* ── Progress stepper ─────────────────────────────────────────────────── */

function ProgressStepper({ data }: { data: CaseDetail }) {
  const docsDone = (['id_front', 'id_back', 'selfie'] as const)
    .every((k) => (data.documents[k]?.versions?.length ?? 0) > 0 || data.documents[k]?.available)
  const decided = data.status !== 'pending'
  const steps = [
    { label: 'Account created', done: true },
    { label: 'Phone verified', done: data.phone_verified },
    { label: 'Profile info', done: true },
    { label: 'Documents', done: docsDone },
    { label: 'Checks', done: !!data.checks.checked_at },
    { label: data.status === 'approved' ? 'Approved' : data.status === 'rejected' ? 'Rejected' : 'Decision', done: decided },
  ]
  const current = steps.findIndex((s) => !s.done)
  return (
    <Card title="Onboarding progress">
      <div className="overflow-x-auto">
        <div className="flex min-w-[540px] items-start">
          {steps.map((s, i) => (
            <div key={s.label} className="flex flex-1 flex-col items-center">
              <div className="flex w-full items-center">
                <div className={`h-px flex-1 ${i === 0 ? 'invisible' : ''} ${steps[i - 1]?.done ? 'bg-blue-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
                <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                  s.done ? 'bg-emerald-500 text-white'
                  : i === current ? 'border-2 border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border border-slate-300 text-slate-400 dark:border-slate-600'}`}>
                  {s.done ? <Check className="h-3.5 w-3.5" /> : i + 1}
                </div>
                <div className={`h-px flex-1 ${i === steps.length - 1 ? 'invisible' : ''} ${s.done ? 'bg-blue-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
              </div>
              <p className={`mt-1.5 px-1 text-center text-[10px] leading-tight ${
                i === current ? 'font-semibold text-blue-600 dark:text-blue-400' : 'text-slate-500'}`}>
                {s.label}
              </p>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}

/* ── Requested information ────────────────────────────────────────────── */

function RequestedInfo({ data }: { data: CaseDetail }) {
  const a = data.applicant
  const received = (key: string): boolean => {
    if (key === 'id_front' || key === 'id_back' || key === 'selfie') {
      const d = data.documents[key as 'id_front' | 'id_back' | 'selfie']
      return (d?.versions?.length ?? 0) > 0 || !!d?.available
    }
    const map: Record<string, unknown> = {
      id_number: a.id_number, kra_pin: a.kra_pin, date_of_birth: a.date_of_birth,
      physical_address: a.physical_address, county: a.county, occupation: a.occupation,
      source_of_income: a.source_of_income, expected_monthly_income: a.expected_monthly_income,
      email: a.email,
    }
    const v = map[key]
    return v != null && v !== ''
  }
  return (
    <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
      {Object.entries(data.resubmittable_items).map(([key, label]) => {
        const rerequested = data.resubmission_requested.includes(key)
        return (
          <div key={key} className="flex items-center justify-between text-sm">
            <span className="text-slate-500">{label}</span>
            {rerequested
              ? <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">Re-requested</span>
              : received(key)
                ? <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">Received ✓</span>
                : <span className="text-xs text-slate-400">—</span>}
          </div>
        )
      })}
    </div>
  )
}

/* ── Case summary + SLA ───────────────────────────────────────────────── */

function CaseSummary({ data }: { data: CaseDetail }) {
  const a = data.applicant
  const v = (x: unknown) => (x == null || x === '' ? '—' : String(x))
  return (
    <Card title="Case summary">
      <dl className="space-y-1.5 text-sm">
        <SummaryRow k="Applicant" v={`${v(a.given_names)} ${v(a.surname)}`} />
        <SummaryRow k="Phone" v={data.phone_number} verified={data.phone_verified} mono />
        <SummaryRow k="Email" v={v(a.email)} verified={!!a.email_verified} />
        <SummaryRow k="Date of birth" v={v(a.date_of_birth)} />
        <SummaryRow k="County" v={v(a.county)} />
        <SummaryRow k="Income" v={v(a.expected_monthly_income)} />
      </dl>
    </Card>
  )
}
function SummaryRow({ k, v, verified, mono }: { k: string; v: string; verified?: boolean; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="shrink-0 text-slate-400">{k}</dt>
      <dd className={`min-w-0 truncate text-right text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>
        {v}{verified && <span className="ml-1 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">Verified</span>}
      </dd>
    </div>
  )
}

function ModeBtn({ active, activeCls, onClick, icon, label }: {
  active: boolean; activeCls: string; onClick: () => void; icon: React.ReactNode; label: string
}) {
  return (
    <button onClick={onClick}
      className={`flex flex-col items-center gap-1 rounded-lg border py-2 text-xs font-semibold ${
        active ? activeCls : 'border-slate-200 text-slate-500 hover:border-slate-300 dark:border-slate-700 dark:hover:border-slate-600'}`}>
      {icon}{label}
    </button>
  )
}

function SlaChip({ sla }: { sla: NonNullable<CaseDetail['sla']> }) {
  const label = sla.overdue
    ? `SLA overdue by ${Math.abs(Math.round(sla.remaining_hours))}h`
    : sla.remaining_hours < 1
      ? `SLA ${Math.max(1, Math.round(sla.remaining_hours * 60))}m remaining`
      : `SLA ${Math.round(sla.remaining_hours)}h remaining`
  const cls = sla.overdue ? 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400'
    : sla.remaining_hours < 6 ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400'
    : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`}>{label}</span>
}

function Section({ label, children, last }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className={last ? '' : 'mb-4 border-b border-slate-100 pb-4 dark:border-slate-800'}>
      <p className="mb-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300">{label}</p>
      <div className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">{children}</div>
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

/* ── Documents tab ────────────────────────────────────────────────────── */

const DOC_LABELS: Record<string, string> = { id_front: 'ID front', id_back: 'ID back', selfie: 'Selfie' }

function Documents({ data }: { data: CaseDetail }) {
  return (
    <>
      {(['id_front', 'id_back', 'selfie'] as const).map((key) => {
        const doc = data.documents[key]
        const versions = doc.versions ?? []
        return (
          <Card key={key} title={`${DOC_LABELS[key]} · ${versions.length} version${versions.length === 1 ? '' : 's'}`}>
            {versions.length === 0 ? (
              <p className="text-sm text-slate-400">Never provided.</p>
            ) : (
              <div className="space-y-2">
                {versions.map((ver, i) => (
                  <div key={ver.version} className="flex items-center gap-3 rounded-lg border border-slate-100 p-2 dark:border-slate-800">
                    {ver.url ? (
                      <a href={ver.url} target="_blank" rel="noreferrer" className="shrink-0 overflow-hidden rounded-md border border-slate-200 dark:border-slate-700">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={ver.url} alt={`${DOC_LABELS[key]} v${ver.version}`} className="h-16 w-24 object-cover" />
                      </a>
                    ) : (
                      <div className="flex h-16 w-24 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-300 dark:border-slate-700">
                        <FileWarning className="h-4 w-4 text-slate-400" />
                      </div>
                    )}
                    <div className="min-w-0 text-xs">
                      <p className="font-medium text-slate-700 dark:text-slate-200">
                        v{ver.version}{i === 0 && <span className="ml-1.5 rounded bg-blue-100 px-1 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-500/10 dark:text-blue-400">current</span>}
                      </p>
                      <p className="text-slate-400">{ver.source.replace('_', ' ')} · {new Date(ver.at).toLocaleString()}</p>
                      {ver.sha256 && <p className="truncate font-mono text-[10px] text-slate-400">sha256 {ver.sha256.slice(0, 16)}…</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )
      })}
    </>
  )
}

/* ── Tasks & events rail ──────────────────────────────────────────────── */

function TasksAndEvents({ data, onViewLog }: { data: CaseDetail; onViewLog: () => void }) {
  const tasks: string[] = []
  if (data.resubmission_requested.length > 0) {
    const labels = data.resubmission_requested.map((k) => data.resubmittable_items[k] ?? k)
    tasks.push(`Awaiting re-submission: ${labels.join(', ')}`)
  }
  if (data.status === 'pending' && !data.applicant.email_verified) tasks.push('Email not yet verified by the applicant')
  if (data.status === 'pending' && !data.assignee) tasks.push('Case is unassigned')

  return (
    <Card title="Tasks & events">
      {tasks.length === 0 ? (
        <p className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
          No open tasks at this moment.
        </p>
      ) : (
        <ul className="mb-3 space-y-1.5">
          {tasks.map((t, i) => (
            <li key={i} className="flex items-start gap-2 rounded-lg bg-amber-50 px-2.5 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
              <ClipboardList className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {t}
            </li>
          ))}
        </ul>
      )}
      <ul className="space-y-2.5">
        {data.timeline.slice(0, 4).map((e) => <TimelineRow key={e.seq} e={e} />)}
      </ul>
      {data.timeline.length > 4 && (
        <button onClick={onViewLog} className="mt-2.5 text-xs font-medium text-blue-600 hover:underline dark:text-blue-400">
          View full event log →
        </button>
      )}
    </Card>
  )
}

/* ── Shared bits ──────────────────────────────────────────────────────── */

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-slate-400">{title}</h2>
      {children}
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
  'case.assigned': 'Case assigned',
  'case.unassigned': 'Case released',
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

function TimelineRow({ e }: { e: TimelineEvent }) {
  const kindColor = e.actor_kind === 'staff' ? 'bg-blue-500'
    : e.actor_kind === 'customer' ? 'bg-emerald-500' : 'bg-slate-400'
  // Staff actors read by first name; customer phone numbers and system
  // provider labels stay as-is.
  const actor = e.actor_kind === 'staff' && e.actor.includes('@')
    ? staffFirstName(e.actor) : e.actor
  const detail = [
    typeof e.payload?.reason === 'string' && e.payload.reason ? `“${e.payload.reason}”` : null,
    typeof e.payload?.reason_code === 'string' ? String(e.payload.reason_code) : null,
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
        <span className="text-slate-400"> · {actor}</span>
        {detail && <span className="block truncate text-slate-400">{detail}</span>}
        <span className="block font-mono text-[10px] text-slate-400">
          #{e.seq} · {new Date(e.at).toLocaleString()}
        </span>
      </div>
    </li>
  )
}
