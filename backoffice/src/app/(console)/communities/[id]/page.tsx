'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, Lock, PauseCircle, PlayCircle, ShieldAlert } from 'lucide-react'
import { platform, type CommunityFile } from '@/lib/platform'
import { staffFirstName } from '@/lib/staff'
import { useCan } from '@/store/ops'
import { useStepUp } from '@/components/StepUp'

export default function CommunityFilePage() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const stepUp = useStepUp()
  const id = String(params.id)
  const [data, setData] = useState<CommunityFile | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    platform.community(id).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [id])
  useEffect(() => { load() }, [load])

  const lifecycle = async (action: 'suspend' | 'unsuspend') => {
    setErr('')
    let token: string
    try { token = await stepUp.request() }
    catch { return }   // operator cancelled the step-up prompt
    setBusy(true)
    try { await platform.communityLifecycle(id, action, reason.trim(), token); setReason(''); load() }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.') }
    finally { setBusy(false) }
  }

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this community.</p>

  const canManage = can('communities.manage')

  return (
    <div className="mx-auto max-w-6xl">
      {stepUp.modal}
      <button onClick={() => router.push('/communities')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Communities
      </button>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{data.name}</h1>
        {data.is_private && <Lock className="h-4 w-4 text-slate-400" />}
        <StatusChip status={data.status} />
        <span className="text-xs capitalize text-slate-400">{data.category}</span>
      </div>
      <div className="mb-5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
        <span>Owner: <b className="text-slate-600 dark:text-slate-300">{data.owner_name || '—'}</b> <span className="font-mono">{data.owner_phone}</span></span>
        {data.location && <span>{data.location}</span>}
        <span>Created {new Date(data.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</span>
        {data.tenant && <span>Tenant: {data.tenant}</span>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Membership">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <Stat label="Active" value={data.members.active} />
              <Stat label="Admins" value={data.members.admins} />
              <Stat label="Treasurers" value={data.members.treasurers} />
              <Stat label="Banned" value={data.members.banned} />
              <Stat label="Cap" value={data.members.max ?? '∞'} />
            </div>
            {data.pending_join_requests > 0 && (
              <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                {data.pending_join_requests} join request(s) awaiting community-admin review.
              </p>
            )}
          </Card>

          <Card title="Financial footprint">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Contribution pools" value={data.finance.contributions} />
              <Stat label="Welfare funds" value={data.finance.welfare_funds} />
              <Stat label="Shares funds" value={data.finance.shares_funds} />
              <div>
                <p className="text-[11px] text-slate-400">Financial history</p>
                <p className={`text-sm font-semibold ${data.finance.has_financial_history
                  ? 'text-slate-800 dark:text-slate-100' : 'text-slate-400'}`}>
                  {data.finance.has_financial_history ? 'money has moved' : 'none'}
                </p>
              </div>
            </div>
            {data.finance.has_financial_history && (
              <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
                This community can never be hard-deleted — its records back posted ledger entries.
              </p>
            )}
          </Card>

          <Card title="Governance settings">
            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {Object.entries(data.settings).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 text-sm">
                  <dt className="text-slate-400">{k.replace(/_/g, ' ')}</dt>
                  <dd className="text-right font-medium text-slate-700 dark:text-slate-200">{String(v)}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="Audit trail">
            {data.audit_trail.length === 0
              ? <p className="text-sm text-slate-400">No recorded actions.</p>
              : (
                <ul className="space-y-2.5">
                  {data.audit_trail.map((e, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-xs">
                      <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-slate-400" />
                      <div className="min-w-0">
                        <span className="font-medium text-slate-700 dark:text-slate-200">{e.action}</span>
                        <span className="text-slate-400"> · {e.actor.includes('@') ? staffFirstName(e.actor) : e.actor}</span>
                        <span className="block font-mono text-[10px] text-slate-400">{new Date(e.at).toLocaleString()}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
          </Card>
        </div>

        <div className="space-y-5">
          {canManage ? (
            <Card title="Lifecycle">
              {err && <p className="mb-2 text-sm text-red-500">{err}</p>}
              {data.status === 'suspended' ? (
                <>
                  <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700 dark:bg-red-500/10 dark:text-red-400">
                    <ShieldAlert className="mr-1 inline h-3.5 w-3.5" />
                    Suspended — joins, money-object creation and new conversations are frozen.
                  </p>
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                    placeholder="Note for the audit trail (optional)"
                    className="mb-2 w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                  <button disabled={busy} onClick={() => lifecycle('unsuspend')}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60">
                    <PlayCircle className="h-4 w-4" /> Lift suspension
                  </button>
                </>
              ) : data.status === 'archived' ? (
                <p className="text-sm text-slate-500">
                  Archived by its owner — records stay readable; only the owner can restore it.
                </p>
              ) : (
                <>
                  <p className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
                    Suspension freezes joins, contributions, claims, advances, payouts and new
                    conversations while records stay readable. Use for fraud investigations,
                    compliance reviews, or court orders.
                  </p>
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                    placeholder="Reason (required — goes on the audit trail)"
                    className="mb-2 w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                  <button disabled={busy || !reason.trim()} onClick={() => lifecycle('suspend')}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 py-2.5 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50">
                    <PauseCircle className="h-4 w-4" /> Suspend community
                  </button>
                </>
              )}
            </Card>
          ) : (
            <Card title="Lifecycle"><p className="text-sm text-slate-500">You have read-only access to this community.</p></Card>
          )}

          {data.description && (
            <Card title="About">
              <p className="text-sm text-slate-600 dark:text-slate-300">{data.description}</p>
            </Card>
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
function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="font-mono text-lg tabular-nums text-slate-800 dark:text-slate-100">{value}</p>
    </div>
  )
}
function StatusChip({ status }: { status: string }) {
  const m: Record<string, string> = {
    active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
    suspended: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
    archived: 'bg-slate-200 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300',
  }
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${m[status] ?? 'bg-slate-100 text-slate-600'}`}>{status}</span>
}
