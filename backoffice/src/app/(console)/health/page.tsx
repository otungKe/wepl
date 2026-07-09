'use client'
// System Health (OP-2) — the async nervous system at a glance: the outbox (with
// a dead-letter browser + requeue), worker heartbeats, and Celery queue depths.
import { useCallback, useEffect, useState } from 'react'
import { HeartPulse, Loader2, RefreshCw, RotateCcw, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { health, type HealthOverview, type OutboxRow } from '@/lib/platform'
import { apiError } from '@/lib/ops'
import { useCan } from '@/store/ops'

export default function HealthPage() {
  const can = useCan()
  const canAct = can('health.act')
  const [data, setData] = useState<HealthOverview | null>(null)
  const [dead, setDead] = useState<OutboxRow[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    Promise.all([health.overview(), health.outbox('DEAD')])
      .then(([o, d]) => { setData(o.data); setDead(d.data.results); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])
  useEffect(() => { load() }, [load])

  const requeue = async (id: number) => {
    setMsg(''); setBusyId(id)
    try { await health.requeue(id); setMsg(`Event #${id} requeued.`); load() }
    catch (e) { setMsg(apiError(e, 'Requeue failed.')) }
    finally { setBusyId(null) }
  }

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load system health.</p>

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-4 flex items-center gap-3">
        <HeartPulse className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">System Health</h1>
        <button onClick={load} className="ml-auto rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {msg && <p className="mb-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">{msg}</p>}

      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Outbox pending" value={data.outbox.pending} tone={data.outbox.pending > 50 ? 'warn' : 'ok'} />
        <Stat label="Dead letters" value={data.outbox.dead} tone={data.outbox.dead > 0 ? 'bad' : 'ok'} />
        <Stat label="Oldest pending"
          value={data.outbox.oldest_pending_seconds == null ? '—' : `${Math.round(data.outbox.oldest_pending_seconds / 60)}m`}
          tone={(data.outbox.oldest_pending_seconds ?? 0) > 600 ? 'warn' : 'ok'} />
      </div>

      <Section title="Worker heartbeats">
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {data.heartbeats.map((h) => (
            <div key={h.task} className="flex items-center gap-3 py-2 text-sm">
              {h.stale ? <AlertTriangle className="h-4 w-4 text-amber-500" />
                : h.never_seen ? <span className="h-2 w-2 rounded-full bg-slate-300" />
                : <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
              <span className="font-mono text-xs text-slate-700 dark:text-slate-200">{h.task.split('.').pop()}</span>
              <span className="ml-auto text-xs text-slate-400">
                {h.never_seen ? 'no heartbeat yet'
                  : h.stale ? `stale — ${fmtAge(h.age_seconds)} ago`
                  : `seen ${fmtAge(h.age_seconds)} ago`}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Queue depths">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Object.entries(data.queues).map(([q, depth]) => (
            <div key={q} className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
              <p className="text-[11px] uppercase tracking-wide text-slate-400">{q}</p>
              <p className="font-mono text-lg tabular-nums text-slate-700 dark:text-slate-200">{depth == null ? '—' : depth}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title={`Dead-lettered events${dead.length ? ` (${dead.length})` : ''}`}>
        {dead.length === 0 ? (
          <p className="py-4 text-sm text-slate-400">No dead letters. The relay is clean.</p>
        ) : (
          <ul className="space-y-2">
            {dead.map((e) => (
              <li key={e.id} className="rounded-lg border border-slate-100 p-3 dark:border-slate-800">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-800 dark:text-slate-100">{e.event_type}</span>
                  <span className="font-mono text-[10px] text-slate-400">#{e.id} · {e.attempts} attempts</span>
                  {canAct && (
                    <button disabled={busyId === e.id} onClick={() => requeue(e.id)}
                      className="ml-auto inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                      {busyId === e.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />} Requeue
                    </button>
                  )}
                </div>
                {e.last_error && <p className="mt-1 font-mono text-[11px] text-red-500">{e.last_error}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-slate-400">{title}</h2>
      {children}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone: 'ok' | 'warn' | 'bad' }) {
  const tones = {
    ok: 'text-slate-700 dark:text-slate-200',
    warn: 'text-amber-600 dark:text-amber-400',
    bad: 'text-red-600 dark:text-red-400',
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tones[tone]}`}>{value}</p>
    </div>
  )
}

function fmtAge(secs: number | null): string {
  if (secs == null) return '—'
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.round(secs / 60)}m`
  return `${Math.round(secs / 3600)}h`
}
