'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, ShieldCheck, AlertTriangle, MailCheck, MailX, Upload } from 'lucide-react'
import { verification, type QueueRow } from '@/lib/verification'

const TABS = [
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
]

function age(h: number | null) {
  if (h == null) return '—'
  if (h < 1) return `${Math.round(h * 60)}m`
  if (h < 48) return `${Math.round(h)}h`
  return `${Math.round(h / 24)}d`
}

export default function VerificationQueue() {
  const [tab, setTab] = useState('pending')
  const [rows, setRows] = useState<QueueRow[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    setStatus('loading')
    verification.queue(tab)
      .then((r) => { setRows(r.data.results); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [tab])

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Verification Centre</h1>
      </div>

      <div className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load the queue.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          Queue clear — nothing to review.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                <th className="px-4 py-2.5 text-left font-semibold">Applicant</th>
                <th className="px-4 py-2.5 text-left font-semibold">ID number</th>
                <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                <th className="px-4 py-2.5 text-left font-semibold">Signals</th>
                <th className="px-4 py-2.5 text-right font-semibold">Age</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.user_id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                  <td className="px-4 py-2.5">
                    <Link href={`/verification/${r.user_id}`} className="block">
                      <span className="font-medium text-slate-800 dark:text-slate-100">{r.name}</span>
                      <span className="block text-xs text-slate-400">{r.phone_number}</span>
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-600 dark:text-slate-300">{r.id_number || '—'}</td>
                  <td className="px-4 py-2.5"><StatusChip status={r.status} /></td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {r.email_verified
                        ? <Sig ok icon={<MailCheck className="h-3 w-3" />}>email</Sig>
                        : <Sig icon={<MailX className="h-3 w-3" />}>no email</Sig>}
                      {r.ocr_mismatch && <Sig warn icon={<AlertTriangle className="h-3 w-3" />}>OCR mismatch</Sig>}
                      {r.resubmission_pending && <Sig icon={<Upload className="h-3 w-3" />}>re-submit pending</Sig>}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-500">{age(r.age_hours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  const m: Record<string, string> = {
    pending: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    approved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
  }
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${m[status] ?? 'bg-slate-100 text-slate-600'}`}>{status}</span>
}

function Sig({ children, icon, ok, warn }: { children: React.ReactNode; icon: React.ReactNode; ok?: boolean; warn?: boolean }) {
  const c = ok ? 'text-emerald-600 dark:text-emerald-400' : warn ? 'text-red-600 dark:text-red-400' : 'text-slate-400'
  return <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${c}`}>{icon}{children}</span>
}
