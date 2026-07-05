'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, Check, X, Upload, FileWarning } from 'lucide-react'
import { verification, type CaseDetail, type DocRef, type Decision } from '@/lib/verification'
import { useCan } from '@/store/ops'

export default function VerificationCase() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const userId = String(params.userId)
  const [data, setData] = useState<CaseDetail | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [items, setItems] = useState<string[]>([])
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    verification.case(userId).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [userId])
  useEffect(() => { load() }, [load])

  const decide = async (body: Decision) => {
    setErr(''); setBusy(true)
    try { const r = await verification.decide(userId, body); setData(r.data); setReason(''); setItems([]) }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.') }
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

          {data.history.length > 0 && (
            <Card title="History">
              <ul className="space-y-2">
                {data.history.map((h, i) => (
                  <li key={i} className="flex items-start gap-3 text-xs">
                    <span className="mt-0.5 font-mono text-slate-400">{new Date(h.at).toLocaleString()}</span>
                    <span><b className="text-slate-700 dark:text-slate-200">{h.action.replace('ops.', '')}</b> · {h.by}</span>
                  </li>
                ))}
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
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                  placeholder="Rejection reason (required to reject)"
                  className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-slate-400" />
                <button disabled={busy || !reason.trim()} onClick={() => decide({ action: 'reject', reason: reason.trim() })}
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
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">{label}</p>
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
