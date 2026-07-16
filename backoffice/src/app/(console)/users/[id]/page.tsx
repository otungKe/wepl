'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import {
  Loader2, ArrowLeft, ShieldCheck, UserX, UserCheck, Download,
  MonitorSmartphone, LogOut, KeyRound, Pencil, StickyNote, PhoneCall, Ban, ShieldOff,
  Fingerprint, MapPin, Mail, ArrowDownLeft, ArrowUpRight, Wallet, Check,
} from 'lucide-react'
import { opsUsers, RESTRICTION_KINDS, type User360 } from '@/lib/platform'
import { downloadCsv } from '@/lib/ops'
import { staffFirstName } from '@/lib/staff'
import { useCan } from '@/store/ops'
import { useStepUp } from '@/components/StepUp'

export default function User360Page() {
  const params = useParams()
  const router = useRouter()
  const can = useCan()
  const stepUp = useStepUp()
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
    setErr('')
    let token: string
    try { token = await stepUp.request() }
    catch { return }   // operator cancelled the step-up prompt
    setBusy(true)
    try { await opsUsers.status(id, action, reason.trim(), token); setReason(''); load() }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.') }
    finally { setBusy(false) }
  }

  // ── Support actions ────────────────────────────────────────────────────────
  const [flash, setFlash] = useState('')
  const [newName, setNewName] = useState('')
  const [note, setNote] = useState('')
  const [newPhone, setNewPhone] = useState('')
  const [phoneReason, setPhoneReason] = useState('')

  const apiErr = (e: unknown) =>
    (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Action failed.'

  const run = async (fn: () => Promise<unknown>, done: string) => {
    setErr(''); setFlash(''); setBusy(true)
    try { await fn(); setFlash(done); load() }
    catch (e) { setErr(apiErr(e)) }
    finally { setBusy(false) }
  }

  const revokeSession = async (sid: string, device: string) => {
    if (!window.confirm(`Sign out “${device || 'this device'}”?`)) return
    let token: string
    try { token = await stepUp.request() } catch { return }
    await run(() => opsUsers.revokeSession(id, sid, '', token), 'Device signed out.')
  }

  const revokeAll = async () => {
    if (!window.confirm('Sign this member out of EVERY device? They will need to log in again.')) return
    let token: string
    try { token = await stepUp.request() } catch { return }
    await run(() => opsUsers.revokeAllSessions(id, 'ops: revoke all', token), 'All devices signed out.')
  }

  const unlockPin = () => run(() => opsUsers.unlockPin(id), 'PIN lockout cleared.')

  const correctName = () => {
    if (!newName.trim()) return
    return run(async () => { await opsUsers.correctName(id, newName.trim()); setNewName('') },
               'Name corrected.')
  }

  const addNote = () => {
    if (!note.trim()) return
    return run(async () => { await opsUsers.addNote(id, note.trim()); setNote('') }, 'Note added.')
  }

  const requestPhoneChange = async () => {
    if (!newPhone.trim() || !phoneReason.trim()) return
    let token: string
    try { token = await stepUp.request() } catch { return }
    await run(async () => {
      await opsUsers.requestPhoneChange(id, newPhone.trim(), phoneReason.trim(), token)
      setNewPhone(''); setPhoneReason('')
    }, 'Phone change requested — pending a second operator in Approvals.')
  }

  // Contact / address amendment (identity core stays KYC-governed).
  const [editContact, setEditContact] = useState(false)
  const [cEmail, setCEmail] = useState('')
  const [cAddr, setCAddr] = useState('')
  const [cOcc, setCOcc] = useState('')

  const startEditContact = () => {
    if (!data) return
    setCEmail(data.contact.email); setCAddr(data.contact.physical_address); setCOcc(data.contact.occupation)
    setEditContact(true)
  }
  const saveContact = async () => {
    if (!data) return
    const changes: Record<string, string> = {}
    if (cEmail !== data.contact.email) changes.email = cEmail
    if (cAddr !== data.contact.physical_address) changes.physical_address = cAddr
    if (cOcc !== data.contact.occupation) changes.occupation = cOcc
    if (Object.keys(changes).length === 0) { setEditContact(false); return }
    await run(async () => { await opsUsers.updateContact(id, changes); setEditContact(false) }, 'Contact details updated.')
  }

  const [restKind, setRestKind] = useState('freeze')
  const [restReason, setRestReason] = useState('')
  const [restExpiry, setRestExpiry] = useState('')

  const applyRestriction = async () => {
    if (!restReason.trim()) return
    let token: string
    try { token = await stepUp.request() } catch { return }
    await run(async () => {
      await opsUsers.applyRestriction(id, restKind, restReason.trim(),
        restExpiry ? new Date(restExpiry).toISOString() : null, token)
      setRestReason(''); setRestExpiry('')
    }, 'Restriction applied.')
  }

  const liftRestriction = async (rid: number) => {
    if (!window.confirm('Lift this restriction?')) return
    let token: string
    try { token = await stepUp.request() } catch { return }
    await run(() => opsUsers.liftRestriction(id, rid, '', token), 'Restriction lifted.')
  }

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this member.</p>

  const i = data.identity
  const canManage = can('users.manage')

  return (
    <div className="mx-auto max-w-6xl">
      {stepUp.modal}
      <button onClick={() => router.push('/users')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Members
      </button>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{i.name || i.phone_number}</h1>
        <StatusPill status={data.account_status} />
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500 dark:bg-slate-800">Tier {i.tier}</span>
      </div>
      <div className="mb-5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
        <span className="font-mono">{i.phone_number}</span>
        {i.member_number && <span className="font-mono text-slate-500 dark:text-slate-300">{i.member_number}</span>}
        <span>Joined {new Date(i.joined).toLocaleDateString(undefined, { dateStyle: 'medium' })}</span>
        {i.last_seen && <span>Last seen {new Date(i.last_seen).toLocaleString()}</span>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Identity">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-sm sm:grid-cols-3">
              <Field label="Legal name" value={[i.given_names, i.surname].filter(Boolean).join(' ') || i.name || '—'} />
              <Field label="National ID" value={i.id_number || '—'} mono />
              <Field label="KRA PIN" value={i.kra_pin || '—'} mono />
              <Field label="Date of birth" value={i.date_of_birth ? new Date(i.date_of_birth).toLocaleDateString(undefined, { dateStyle: 'medium' }) : '—'} />
              <Field label="Nationality" value={i.nationality || '—'} />
              <Field label="Member no." value={i.member_number || '—'} mono />
            </div>
            <p className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-400">
              <Fingerprint className="h-3 w-3" /> Verified identity — changes go through KYC re-verification, not here.
            </p>
          </Card>

          <Card title="Recent money activity">
            {data.recent_activity.length === 0
              ? <p className="text-sm text-slate-400">No money movements on record.</p>
              : (
                <div className="space-y-1">
                  {data.recent_activity.map((a) => {
                    const out = a.direction === 'PAYOUT'
                    return (
                      <Link key={a.id} href={`/transactions/${a.id}`}
                        className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/60">
                        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${out ? 'bg-red-100 text-red-600 dark:bg-red-500/10 dark:text-red-400' : 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400'}`}>
                          {out ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownLeft className="h-3.5 w-3.5" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-slate-700 dark:text-slate-200">
                            {a.op_type.replace(/_/g, ' ').toLowerCase()}
                            {a.counterparty_name ? <span className="text-slate-400"> · {a.counterparty_name}</span> : ''}
                          </p>
                          <p className="font-mono text-[10px] text-slate-400">{a.reference} · {new Date(a.created_at).toLocaleString()}</p>
                        </div>
                        <div className="text-right">
                          <p className={`font-mono text-sm tabular-nums ${out ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                            {out ? '−' : '+'}{a.amount}
                          </p>
                          <p className="text-[10px] uppercase tracking-wide text-slate-400">{a.state.toLowerCase()}</p>
                        </div>
                      </Link>
                    )
                  })}
                </div>
              )}
          </Card>

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
            <div className="mt-2 flex items-center justify-between">
              <p className="text-[11px] text-slate-400">
                Balances are derived ledger projections — read-only here, always.
              </p>
              {can('ledger.export') && (
                <button
                  onClick={() => downloadCsv(`/ops/users/${id}/statement/`, {}, `statement-u${id}.csv`)}
                  title="Download this member's sub-ledger statement as CSV"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                  <Download className="h-3.5 w-3.5" /> Statement
                </button>
              )}
            </div>
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
          {flash && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">{flash}</p>}

          <Card title="Contact & address">
            {!data.contact.has_kyc ? (
              <p className="text-sm text-slate-400">No KYC profile yet — contact details are captured at verification.</p>
            ) : !editContact ? (
              <>
                <dl className="space-y-2 text-sm">
                  <ContactRow icon={PhoneCall} label="Phone" value={data.contact.phone_number} mono />
                  <ContactRow icon={Mail} label="Email"
                    value={data.contact.email || '—'}
                    badge={data.contact.email ? (data.contact.email_verified ? 'verified' : 'unverified') : undefined} />
                  <ContactRow icon={MapPin} label="Address" value={data.contact.physical_address || '—'} />
                  <ContactRow icon={MapPin} label="County" value={data.contact.county || '—'} />
                  <ContactRow icon={Wallet} label="Occupation" value={data.contact.occupation || '—'} />
                </dl>
                {canManage && (
                  <button onClick={startEditContact}
                    className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                    <Pencil className="h-3.5 w-3.5" /> Edit contact & address
                  </button>
                )}
                <p className="mt-2 text-[10px] text-slate-400">Phone changes go through the maker-checked flow below.</p>
              </>
            ) : (
              <div className="space-y-2">
                <LabelledInput label="Email" type="email" value={cEmail} onChange={setCEmail} />
                <LabelledInput label="Physical address" value={cAddr} onChange={setCAddr} />
                <LabelledInput label="Occupation" value={cOcc} onChange={setCOcc} />
                <div className="flex gap-2 pt-1">
                  <button disabled={busy} onClick={saveContact}
                    className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-slate-800 py-2 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900">
                    <Check className="h-3.5 w-3.5" /> Save
                  </button>
                  <button onClick={() => setEditContact(false)}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                    Cancel
                  </button>
                </div>
                <p className="text-[10px] text-slate-400">Changing the email marks it unverified until re-confirmed.</p>
              </div>
            )}
          </Card>

          <Card title={`Devices · ${data.sessions.active}`}>
            {data.sessions.pin_locked && (
              <div className="mb-3 flex items-center justify-between rounded-lg bg-amber-50 px-3 py-2 dark:bg-amber-500/10">
                <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
                  <KeyRound className="h-3.5 w-3.5" /> PIN locked out
                </span>
                {canManage && (
                  <button disabled={busy} onClick={unlockPin}
                    className="rounded-md bg-amber-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-amber-500 disabled:opacity-50">
                    Unlock
                  </button>
                )}
              </div>
            )}
            {data.sessions.devices.length === 0 ? (
              <p className="text-sm text-slate-400">No active sessions.</p>
            ) : (
              <div className="space-y-1.5">
                {data.sessions.devices.map((d) => (
                  <div key={d.sid} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
                    <MonitorSmartphone className="h-4 w-4 shrink-0 text-slate-400" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-slate-700 dark:text-slate-200">{d.device_label || 'Unknown device'}</p>
                      <p className="font-mono text-[10px] text-slate-400">
                        {d.ip_address ? `${d.ip_address} · ` : ''}{new Date(d.last_seen).toLocaleString()}
                      </p>
                    </div>
                    {canManage && (
                      <button disabled={busy} onClick={() => revokeSession(d.sid, d.device_label)}
                        title="Sign out this device"
                        className="rounded-md p-1 text-slate-400 hover:bg-slate-200 hover:text-red-600 disabled:opacity-50 dark:hover:bg-slate-700">
                        <LogOut className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
            {canManage && data.sessions.active > 0 && (
              <button disabled={busy} onClick={revokeAll}
                className="mt-2 w-full rounded-lg border border-red-200 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-500/30 dark:hover:bg-red-500/10">
                Sign out all devices
              </button>
            )}
          </Card>

          <Card title="Restrictions">
            {data.restrictions.filter((r) => r.is_effective).length === 0
              ? <p className="text-sm text-slate-400">No active restrictions.</p>
              : (
                <div className="space-y-1.5">
                  {data.restrictions.filter((r) => r.is_effective).map((r) => (
                    <div key={r.id} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-500/30 dark:bg-amber-500/10">
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
                          <ShieldOff className="h-3.5 w-3.5" /> {r.kind_label}
                        </span>
                        {canManage && (
                          <button disabled={busy} onClick={() => liftRestriction(r.id)}
                            className="text-[11px] font-semibold text-slate-500 hover:text-emerald-600 disabled:opacity-50">
                            Lift
                          </button>
                        )}
                      </div>
                      <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{r.reason}</p>
                      <p className="text-[10px] text-slate-400">
                        by {r.applied_by ? staffFirstName(r.applied_by.replace('ops:', '')) : 'ops'}
                        {r.expires_at ? ` · until ${new Date(r.expires_at).toLocaleDateString()}` : ' · no expiry'}
                      </p>
                    </div>
                  ))}
                </div>
              )}

            {canManage && (
              <div className="mt-3 space-y-2 border-t border-slate-100 pt-3 dark:border-slate-800">
                <select value={restKind} onChange={(e) => setRestKind(e.target.value)}
                  className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none dark:border-slate-700 dark:bg-slate-900">
                  {RESTRICTION_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select>
                <input value={restReason} onChange={(e) => setRestReason(e.target.value)} placeholder="Reason (required)"
                  className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                <label className="flex items-center gap-2 text-[11px] text-slate-500">
                  Expires (optional)
                  <input type="date" value={restExpiry} onChange={(e) => setRestExpiry(e.target.value)}
                    className="flex-1 rounded-md border border-slate-200 px-2 py-1 text-xs outline-none dark:border-slate-700 dark:bg-slate-900" />
                </label>
                <button disabled={busy || !restReason.trim()} onClick={applyRestriction}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-600 py-2 text-xs font-semibold text-white hover:bg-amber-500 disabled:opacity-50">
                  <Ban className="h-3.5 w-3.5" /> Apply restriction
                </button>
              </div>
            )}
          </Card>

          {canManage && (
            <Card title="Support actions">
              <div className="space-y-3">
                <div>
                  <label className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500"><Pencil className="h-3 w-3" /> Correct display name</label>
                  <div className="flex gap-1.5">
                    <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={i.name || 'New name'}
                      className="min-w-0 flex-1 rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                    <button disabled={busy || !newName.trim()} onClick={correctName}
                      className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-200 dark:text-slate-900">
                      Save
                    </button>
                  </div>
                </div>
                <div>
                  <label className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500"><PhoneCall className="h-3 w-3" /> Change phone number (maker-checked)</label>
                  <input value={newPhone} onChange={(e) => setNewPhone(e.target.value)} placeholder="2547XXXXXXXX"
                    className="mb-1.5 w-full rounded-md border border-slate-200 px-2 py-1.5 font-mono text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                  <input value={phoneReason} onChange={(e) => setPhoneReason(e.target.value)} placeholder="Reason (identity verified how?)"
                    className="mb-1.5 w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
                  <button disabled={busy || !newPhone.trim() || !phoneReason.trim()} onClick={requestPhoneChange}
                    className="w-full rounded-lg bg-blue-600 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50">
                    Request change — needs a second operator
                  </button>
                  <p className="mt-1 text-[10px] text-slate-400">Executes only after approval; every session is signed out on change.</p>
                </div>
              </div>
            </Card>
          )}

          <Card title="Add note">
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              placeholder="Support note — lands on the member's audit trail"
              className="mb-2 w-full resize-none rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700" />
            <button disabled={busy || !note.trim()} onClick={addNote}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
              <StickyNote className="h-3.5 w-3.5" /> Save note
            </button>
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

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className={`text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>{value}</p>
    </div>
  )
}

function ContactRow({ icon: Icon, label, value, mono, badge }: {
  icon: typeof Mail; label: string; value: string; mono?: boolean; badge?: string
}) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-slate-400">{label}</p>
        <p className={`flex items-center gap-1.5 text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>
          <span className="truncate">{value}</span>
          {badge && (
            <span className={`shrink-0 rounded px-1 py-0.5 text-[9px] font-bold uppercase ${badge === 'verified' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400'}`}>{badge}</span>
          )}
        </p>
      </div>
    </div>
  )
}

function LabelledInput({ label, value, onChange, type = 'text' }: {
  label: string; value: string; onChange: (v: string) => void; type?: string
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-semibold text-slate-500">{label}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-900" />
    </label>
  )
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    active:    'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
    restricted:'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    suspended: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
    dormant:   'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
    closed:    'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
  }
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[status] || map.dormant}`}>{status}</span>
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
