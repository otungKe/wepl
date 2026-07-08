'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, ShieldCheck, UserX, UserCheck } from 'lucide-react'
import { opsUsers, type User360 } from '@/lib/platform'
import { staffFirstName } from '@/lib/staff'
import { useCan } from '@/store/ops'

export default function User360Page() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const id = String(params.id)
  const [data, setData] = useState<User360 | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    setStatus('loading')
    opsUsers.user360(id).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [id])
  useEffect(() => { load() }, [load])

  const setAccount = async (action: 'deactivate' | 'reactivate') => {
    setErr(''); setBusy(true)
    try { await opsUsers.status(id, action, reason.trim()); setReason(''); load() }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.') }
    finally { setBusy(false) }
  }

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this member.</p>

  const i = data.identity
  const canManage = can('users.manage')

  return (
    <div className="mx-auto max-w-6xl">
      <button onClick={() => router.push('/users')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Members
      </button>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{i.name || i.phone_number}</h1>
        {i.is_active
          ? <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">active</span>
          : <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-500/10 dark:text-red-400">deactivated</span>}
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500 dark:bg-slate-800">Tier {i.tier}</span>
      </div>
      <div className="mb-5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
        <span className="font-mono">{i.phone_number}</span>
        <span>Joined {new Date(i.joined).toLocaleDateString(undefined, { dateStyle: 'medium' })}</span>
        {i.last_seen && <span>Last seen {new Date(i.last_seen).toLocaleString()}</span>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Verification">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 text-sm">
              <span>KYC: <b className="capitalize">{data.verification.kyc_status.replace('_', ' ')}</b></span>
              {data.verification.email_verified != null && (
                <span>Email {data.verification.email_verified ? 'verified ✓' : 'unverified'}</span>
              )}
              {data.verification.case && (
                <Link href={`/verification/${i.id}`} className="flex items-center gap-1 text-blue-600 hover:underline dark:text-blue-400">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {data.verification.case.reference} · {data.verification.case.state}
                </Link>
              )}
            </div>
            {(data.verification.resubmission_requested?.length ?? 0) > 0 && (
              <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                Awaiting re-submission: {data.verification.resubmission_requested!.join(', ')}
              </p>
            )}
            {data.verification.open_requests > 0 && (
              <p className="mt-2 text-xs text-slate-500">{data.verification.open_requests} open verification request(s).</p>
            )}
          </Card>

          <Card title="Member Financial 360">
            <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Total position (KES)" value={data.financial.total_position} />
              <Stat label="Open advances" value={data.financial.open_advances} />
              <Stat label="Open holds" value={data.financial.open_holds} alert={data.financial.open_holds > 0} />
              <Stat label="Active clearances" value={data.financial.active_overrides} />
            </div>
            {data.financial.positions.length > 0 && (
              <div className="space-y-1">
                {data.financial.positions.map((pos) => (
                  <div key={pos.contribution_id} className="flex justify-between rounded-lg bg-slate-50 px-3 py-1.5 text-sm dark:bg-slate-800/60">
                    <span className="text-slate-600 dark:text-slate-300">{pos.name}</span>
                    <span className="font-mono text-xs tabular-nums">{pos.balance}</span>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-2 text-[11px] text-slate-400">
              Balances are derived ledger projections — read-only here, always.
            </p>
          </Card>

          <Card title={`Communities · ${data.communities.length}`}>
            {data.communities.length === 0 ? (
              <p className="text-sm text-slate-400">Not a member of any community.</p>
            ) : (
              <div className="space-y-1">
                {data.communities.map((c) => (
                  <Link key={c.id} href={`/communities/${c.id}`}
                    className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-1.5 text-sm hover:bg-slate-100 dark:bg-slate-800/60 dark:hover:bg-slate-800">
                    <span className="text-slate-700 dark:text-slate-200">{c.name}</span>
                    <span className="flex items-center gap-2 text-xs text-slate-400">
                      <span className="capitalize">{c.role}</span>
                      {c.community_status !== 'active' && (
                        <span className="font-semibold text-red-500">{c.community_status}</span>
                      )}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </Card>

          <Card title="Recent activity (audit)">
            {data.audit_trail.length === 0
              ? <p className="text-sm text-slate-400">No recorded events.</p>
              : (
                <ul className="space-y-2.5">
                  {data.audit_trail.map((e, idx) => (
                    <li key={idx} className="flex items-start gap-2.5 text-xs">
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
          <Card title="Sessions">
            <dl className="space-y-1.5 text-sm">
              <Row k="Active sessions" v={String(data.sessions.active)} />
              <Row k="Latest device" v={data.sessions.latest_device || '—'} />
              <Row k="Device last seen" v={data.sessions.latest_seen ? new Date(data.sessions.latest_seen).toLocaleString() : '—'} />
            </dl>
          </Card>

          {canManage ? (
            <Card title="Account">
              {err && <p className="mb-2 text-sm text-red-500">{err}</p>}
              {i.is_active ? (
                <>
                  <p className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/60">
                    Deactivation blocks login and revokes every active session immediately.
                    Their community memberships and financial records are untouched.
                  </p>
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                    placeholder="Reason (required — goes on the audit trail)"
                    className="mb-2 w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                  <button disabled={busy || !reason.trim()} onClick={() => setAccount('deactivate')}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 py-2.5 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50">
                    <UserX className="h-4 w-4" /> Deactivate account
                  </button>
                </>
              ) : (
                <>
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                    placeholder="Note for the audit trail (optional)"
                    className="mb-2 w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                  <button disabled={busy} onClick={() => setAccount('reactivate')}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60">
                    <UserCheck className="h-4 w-4" /> Reactivate account
                  </button>
                </>
              )}
            </Card>
          ) : (
            <Card title="Account"><p className="text-sm text-slate-500">You have read-only access to this member.</p></Card>
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
function Stat({ label, value, alert }: { label: string; value: number | string; alert?: boolean }) {
  return (
    <div>
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className={`font-mono text-lg tabular-nums ${alert ? 'text-amber-600 dark:text-amber-400' : 'text-slate-800 dark:text-slate-100'}`}>{value}</p>
    </div>
  )
}
function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-400">{k}</dt>
      <dd className="text-right text-slate-700 dark:text-slate-200">{v}</dd>
    </div>
  )
}
