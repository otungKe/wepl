'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  Loader2, ShieldCheck, AlertTriangle, MailCheck, MailX, Upload,
  Inbox, UserCheck, Users, CheckCircle2, Clock,
} from 'lucide-react'
import { verification, type QueueRow, type VerificationStats } from '@/lib/verification'
import { useOpsStore } from '@/store/ops'

const TABS = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'pending', label: 'Pending' },
  { key: 'mine', label: 'My cases' },
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

export default function VerificationCentre() {
  const [tab, setTab] = useState('dashboard')

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Verification Centre</h1>
      </div>

      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                            : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'dashboard' ? <Dashboard onOpenQueue={() => setTab('pending')} /> : <Queue tab={tab} />}
    </div>
  )
}

/* ── Dashboard ─────────────────────────────────────────────────────────── */

function Dashboard({ onOpenQueue }: { onOpenQueue: () => void }) {
  const me = useOpsStore((s) => s.me)
  const [stats, setStats] = useState<VerificationStats | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    verification.stats()
      .then((r) => { setStats(r.data); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])

  if (status === 'loading') return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !stats) return <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load the dashboard.</p>

  // First name only, capitalised — falls back to the email local-part's first
  // segment (harry.otung@… → Harry) when no display name is set.
  const raw = (me?.name?.trim() || me?.email || 'there').split(/[\s@._-]+/)[0] || 'there'
  const firstName = raw.charAt(0).toUpperCase() + raw.slice(1)
  const pct = stats.total_cases > 0 ? Math.round((stats.decided_total / stats.total_cases) * 100) : 0

  return (
    <div>
      <p className="mb-4 text-lg font-semibold">Hello {firstName}!</p>

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={<Inbox className="h-4 w-4" />} label="Pending review" value={stats.pending}
          accent={stats.pending > 0} onClick={onOpenQueue} />
        <Stat icon={<Upload className="h-4 w-4" />} label="Awaiting re-submission" value={stats.requires_info} />
        <Stat icon={<Users className="h-4 w-4" />} label="Unassigned" value={stats.unassigned_open} />
        <Stat icon={<UserCheck className="h-4 w-4" />} label="My open cases" value={stats.mine_open} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center lg:col-span-2 dark:border-slate-800 dark:bg-slate-900">
          {stats.pending === 0 ? (
            <>
              <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-500" />
              <p className="text-sm font-semibold">All done!</p>
              <p className="mt-1 text-xs text-slate-500">Nothing is waiting for review.</p>
            </>
          ) : (
            <>
              <Clock className="mx-auto mb-3 h-10 w-10 text-amber-500" />
              <p className="text-sm font-semibold">
                {stats.pending} case{stats.pending === 1 ? '' : 's'} waiting for review
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Oldest has been waiting {age(stats.oldest_pending_hours)}.
              </p>
              <button onClick={onOpenQueue}
                className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500">
                Open the queue
              </button>
            </>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-slate-400">Review progress</h2>
          <div className="mb-1.5 flex items-baseline justify-between text-sm">
            <span className="text-slate-500">Cases decided</span>
            <span className="font-mono tabular-nums">
              <b className="text-blue-600 dark:text-blue-400">{stats.decided_total}</b>
              <span className="text-slate-400">/{stats.total_cases}</span>
            </span>
          </div>
          <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div className="h-full rounded-full bg-blue-600 transition-all dark:bg-blue-500" style={{ width: `${pct}%` }} />
          </div>
          <dl className="space-y-1.5 text-xs">
            <div className="flex justify-between"><dt className="text-slate-400">Decided today</dt><dd className="font-mono tabular-nums">{stats.decided_today}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-400">Last 7 days</dt><dd className="font-mono tabular-nums">{stats.decided_7d}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-400">Approved</dt><dd className="font-mono tabular-nums text-emerald-600 dark:text-emerald-400">{stats.approved}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-400">Rejected</dt><dd className="font-mono tabular-nums text-red-600 dark:text-red-400">{stats.rejected}</dd></div>
          </dl>
        </div>
      </div>
    </div>
  )
}

function Stat({ icon, label, value, accent, onClick }: {
  icon: React.ReactNode; label: string; value: number; accent?: boolean; onClick?: () => void
}) {
  return (
    <button onClick={onClick} disabled={!onClick}
      className={`rounded-xl border p-3.5 text-left ${onClick ? 'cursor-pointer hover:border-blue-400 dark:hover:border-blue-500' : 'cursor-default'}
        border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900`}>
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
        {icon}{label}
      </div>
      <p className={`text-2xl font-semibold tabular-nums ${accent ? 'text-amber-600 dark:text-amber-400' : ''}`}>{value}</p>
    </button>
  )
}

/* ── Queue ─────────────────────────────────────────────────────────────── */

function Queue({ tab }: { tab: string }) {
  const [rows, setRows] = useState<QueueRow[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    setStatus('loading')
    const req = tab === 'mine' ? verification.queue('pending', 'me') : verification.queue(tab)
    req.then((r) => { setRows(r.data.results); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [tab])

  if (status === 'loading') return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error') return <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t load the queue.</p>
  if (rows.length === 0) return (
    <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
      Queue clear — nothing to review.
    </div>
  )

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
      <table className="w-full min-w-[760px] text-sm">
        <thead>
          <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
            <th className="px-4 py-2.5 text-left font-semibold">Applicant</th>
            <th className="px-4 py-2.5 text-left font-semibold">ID number</th>
            <th className="px-4 py-2.5 text-left font-semibold">Status</th>
            <th className="px-4 py-2.5 text-left font-semibold">Assignee</th>
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
              <td className="px-4 py-2.5 text-xs text-slate-500">
                {r.assignee ? r.assignee.split('@')[0] : <span className="text-slate-300 dark:text-slate-600">—</span>}
              </td>
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
