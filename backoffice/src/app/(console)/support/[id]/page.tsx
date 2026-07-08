'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, Paperclip, CheckCircle2 } from 'lucide-react'
import { support, type SupportDetail } from '@/lib/platform'
import { useCan } from '@/store/ops'

export default function SupportRequestPage() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const id = String(params.id)
  const [data, setData] = useState<SupportDetail | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    support.detail(id).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [id])
  useEffect(() => { load() }, [load])

  const resolve = async () => {
    setErr(''); setBusy(true)
    try { const r = await support.resolve(id, note.trim()); setData(r.data); setNote('') }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.') }
    finally { setBusy(false) }
  }

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this request.</p>

  const canAct = can('support.act')

  return (
    <div className="mx-auto max-w-4xl">
      <button onClick={() => router.push('/support')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Support desk
      </button>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{data.title}</h1>
        <StatusChip status={data.status} />
      </div>
      <div className="mb-5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
        <Link href={`/users/${data.user_id}`} className="text-blue-600 hover:underline dark:text-blue-400">
          {data.user_name || data.phone_number}
        </Link>
        <span className="font-mono">{data.phone_number}</span>
        <span className="capitalize">{data.kind.replace(/_/g, ' ')}</span>
        <span>Raised {new Date(data.created_at).toLocaleString()}</span>
      </div>

      <div className="space-y-5">
        <Card title="What was asked">
          <p className="text-sm text-slate-700 dark:text-slate-200">{data.detail}</p>
        </Card>

        <Card title="Member's answer">
          {data.status === 'open' ? (
            <p className="text-sm text-slate-400">Awaiting the member&apos;s response.</p>
          ) : (
            <>
              {data.response_note && (
                <p className="mb-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700 dark:bg-slate-800/60 dark:text-slate-200">
                  “{data.response_note}”
                </p>
              )}
              {data.document_url ? (
                <a href={data.document_url} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:underline dark:text-blue-400">
                  <Paperclip className="h-4 w-4" /> Open attached document
                </a>
              ) : data.has_document ? (
                <p className="text-xs text-slate-400">A document was attached but is not in storage.</p>
              ) : !data.response_note ? (
                <p className="text-sm text-slate-400">Answered without a note or document.</p>
              ) : null}
              {data.responded_at && (
                <p className="mt-2 text-[11px] text-slate-400">Answered {new Date(data.responded_at).toLocaleString()}</p>
              )}
            </>
          )}
        </Card>

        {data.status === 'resolved' ? (
          <Card title="Resolution">
            <p className="flex items-center gap-2 text-sm font-medium text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-4 w-4" /> Resolved
              {data.resolved_at && <span className="font-normal text-slate-400">· {new Date(data.resolved_at).toLocaleString()}</span>}
            </p>
            {data.review_note && (
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">“{data.review_note}”</p>
            )}
          </Card>
        ) : canAct ? (
          <Card title="Resolve">
            {err && <p className="mb-2 text-sm text-red-500">{err}</p>}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              placeholder="Feedback shown to the member (optional)"
              className="mb-2 w-full resize-none rounded-md border border-slate-200 px-2.5 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
            <button disabled={busy} onClick={resolve}
              className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60">
              <CheckCircle2 className="h-4 w-4" /> Mark resolved &amp; notify member
            </button>
          </Card>
        ) : (
          <Card title="Resolve"><p className="text-sm text-slate-500">You have read-only access to this request.</p></Card>
        )}
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
function StatusChip({ status }: { status: string }) {
  const m: Record<string, [string, string]> = {
    open: ['awaiting member', 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400'],
    submitted: ['answered — review', 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400'],
    resolved: ['resolved', 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'],
  }
  const [label, cls] = m[status] ?? [status, 'bg-slate-100 text-slate-600']
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{label}</span>
}
