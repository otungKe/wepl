'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Receipt, Users, Banknote, FileEdit, Plus, Smartphone, Check, X, CreditCard, ArrowUpCircle, ArrowDownCircle, CalendarClock, Lock, ShoppingCart, Split } from 'lucide-react'
import {
  contributions, payments, apiError,
  type Contribution, type Transaction, type Participant, type DisbursementRequest, type ContributionAmendment,
  type PoolActionRequest,
} from '@/lib/api'
import { useTier } from '@/hooks/useTier'
import { useAuthStore } from '@/store/auth'
import { PageHeader } from '@/components/app/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { Button } from '@/components/ui/Button'
import { Input, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Avatar } from '@/components/ui/Avatar'
import { Badge, statusTone } from '@/components/ui/Badge'
import { StatCard } from '@/components/ui/StatCard'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton, PageLoader } from '@/components/ui/Spinner'
import { formatMoney, formatDate, formatRelative } from '@/lib/utils'
import { toast } from 'sonner'

export default function ContributionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { isVerified } = useTier()
  const [c, setC] = useState<Contribution | null>(null)
  const [tab, setTab] = useState('transactions')
  const [loading, setLoading] = useState(true)
  const [payOpen, setPayOpen] = useState(false)

  const load = useCallback(() => {
    contributions.get(id).then(r => setC(r.data)).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [id])
  useEffect(() => { load() }, [load])

  if (loading) return <PageLoader />
  if (!c) return <EmptyState title="Contribution not found" />

  return (
    <div>
      <PageHeader title={c.title} subtitle={c.description || `${c.frequency} contribution`} back
        action={isVerified
          ? <Button size="sm" onClick={() => setPayOpen(true)}><Smartphone size={15} /> Contribute</Button>
          : <Button size="sm" variant="outline" title="Verify your identity to contribute" onClick={() => router.push('/kyc')}><Lock size={15} /> Contribute</Button>
        } />

      {/* Pool balance — physical card style */}
      <div className="mb-4 overflow-hidden rounded-xl bg-primary px-6 py-5">
        <div className="flex items-center justify-between">
          <p className="text-sm text-white/60 font-medium">Pool Balance</p>
          <CreditCard size={18} className="text-white/30" />
        </div>
        <p className="mt-1.5 text-3xl font-bold text-white tabular-nums">{formatMoney(c.current_amount)}</p>
        {c.target_amount && Number(c.target_amount) > 0 && (
          <>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/20">
              <div className="h-full rounded-full bg-white/80 transition-all"
                style={{ width: `${Math.min((Number(c.current_amount) / Number(c.target_amount)) * 100, 100)}%` }} />
            </div>
            <p className="mt-1.5 text-xs text-white/60">
              {Math.round((Number(c.current_amount) / Number(c.target_amount)) * 100)}% of {formatMoney(c.target_amount ?? '0')}
            </p>
          </>
        )}
        <div className="mt-4 flex items-center justify-between">
          <p className="text-xs text-white/50">{c.participant_count} member{c.participant_count !== 1 ? 's' : ''}</p>
          <div className="flex gap-2">
            <span className="rounded-full bg-white/15 px-2.5 py-1 text-[10px] font-semibold text-white">
              {c.frequency.charAt(0).toUpperCase() + c.frequency.slice(1)}
            </span>
            {c.end_date && (
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-[10px] font-semibold text-white">
                Until {c.end_date}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Secondary stats */}
      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <StatCard label="Your balance" value={formatMoney(c.user_balance ?? '0')} />
        <StatCard label="Members" value={String(c.participant_count)} icon={Users} />
      </div>

      {c.my_rosca_slot && (
        <div className="mb-5 rounded-lg border border-accent/30 bg-accent-pale p-4">
          <p className="text-sm font-semibold text-accent">Your ROSCA payout slot</p>
          <p className="mt-1 text-sm text-text-secondary">
            Position #{c.my_rosca_slot.slot_order} · {c.my_rosca_slot.has_received ? 'Received' : 'Pending'}
            {c.my_rosca_slot.payout_amount ? ` · ${formatMoney(c.my_rosca_slot.payout_amount)}` : ''}
          </p>
        </div>
      )}

      <Tabs active={tab} onChange={setTab} className="mb-4" tabs={[
        { key: 'transactions', label: 'Transactions' },
        { key: 'members', label: 'Members' },
        { key: 'disbursements', label: 'Disbursements' },
        ...(c.is_admin ? [{ key: 'pool', label: 'Pool' }] : []),
        { key: 'amendments', label: 'Amendments' },
      ]} />

      {tab === 'transactions' && <TransactionsTab id={id} />}
      {tab === 'members' && <MembersTab id={id} />}
      {tab === 'disbursements' && <DisbursementsTab id={id} isAdmin={c.is_admin} />}
      {tab === 'pool' && c.is_admin && <PoolTab id={id} />}
      {tab === 'amendments' && <AmendmentsTab id={id} />}

      <ContributeModal open={payOpen} onClose={() => setPayOpen(false)} contributionId={Number(id)} />
    </div>
  )
}

function ContributeModal({ open, onClose, contributionId }: { open: boolean; onClose: () => void; contributionId: number }) {
  const [amount, setAmount] = useState('')
  const [phone, setPhone] = useState('')
  const [loading, setLoading] = useState(false)

  async function pay() {
    const amt = Number(amount)
    if (!amt || amt <= 0) return toast.error('Enter a valid amount')
    setLoading(true)
    try {
      await payments.stkPush({ payment_type: 'contribution', contribution_id: contributionId, amount: amt, phone_number: phone || undefined })
      toast.success('Check your phone to authorize the M-PESA payment')
      onClose(); setAmount(''); setPhone('')
    } catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Contribute via M-PESA">
      <div className="flex flex-col gap-4">
        <Input label="Amount (KES)" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} placeholder="1000" autoFocus />
        <Input label="Phone (optional)" type="tel" value={phone} onChange={e => setPhone(e.target.value)} placeholder="Defaults to your number" hint="An STK push will be sent to this number." />
        <Button onClick={pay} loading={loading} fullWidth><Smartphone size={16} /> Send STK push</Button>
      </div>
    </Modal>
  )
}

function TransactionsTab({ id }: { id: string }) {
  const [items, setItems] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { contributions.transactions(id).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false)) }, [id])
  if (loading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
  if (items.length === 0) return <EmptyState icon={Receipt} title="No transactions yet" description="Contributions will appear here once members start paying in." />
  return (
    <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
      {items.map(t => (
        <div key={t.id} className="flex items-center gap-3 p-3.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-pale text-primary"><Banknote size={16} /></div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-text">{t.name || t.phone_number}</p>
            <p className="text-xs text-text-muted">{formatRelative(t.created_at)} · {t.transaction_type.toLowerCase()}</p>
          </div>
          <p className="font-semibold text-primary">{formatMoney(t.amount)}</p>
        </div>
      ))}
    </div>
  )
}

function MembersTab({ id }: { id: string }) {
  const [items, setItems] = useState<Participant[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { contributions.participants(id).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false)) }, [id])
  if (loading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
  if (items.length === 0) return <EmptyState icon={Users} title="No members yet" />
  return (
    <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
      {items.map(m => (
        <div key={m.id} className="flex items-center gap-3 p-3.5">
          <Avatar name={m.name || m.phone_number} size={38} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-text">{m.name || m.phone_number}</p>
            {m.progress_pct != null && (
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-divider">
                <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(m.progress_pct, 100)}%` }} />
              </div>
            )}
          </div>
          <p className="font-semibold text-text">{formatMoney(m.balance)}</p>
        </div>
      ))}
    </div>
  )
}

function DisbursementsTab({ id, isAdmin }: { id: string; isAdmin: boolean }) {
  const [items, setItems] = useState<DisbursementRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<number | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    contributions.disbursements(id).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [id])
  useEffect(() => { load() }, [load])

  async function vote(reqId: number, v: 'APPROVE' | 'REJECT') {
    setBusy(reqId)
    try { await contributions.voteDisbursement(reqId, v); toast.success('Vote recorded'); load() }
    catch (e) { toast.error(apiError(e)) } finally { setBusy(null) }
  }

  if (loading) return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>

  return (
    <div>
      {/* Payout options grid */}
      <div className={`mb-5 grid gap-3 ${isAdmin ? 'grid-cols-2' : 'grid-cols-1'}`}>
        <button
          onClick={() => setOpen(true)}
          className="flex flex-col items-start gap-2 rounded-lg border border-border bg-surface p-4 text-left transition-colors hover:border-primary/40 hover:bg-primary-bg/40"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-pale text-primary">
            <ArrowUpCircle size={18} />
          </div>
          <div>
            <p className="text-sm font-semibold text-text">Request Payout</p>
            <p className="text-xs text-text-muted">Submit for group approval</p>
          </div>
        </button>
        {isAdmin && (
          <div className="flex flex-col items-start gap-2 rounded-lg border border-border bg-surface p-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-success/10 text-success">
              <CalendarClock size={18} />
            </div>
            <div>
              <p className="text-sm font-semibold text-text">Standing Order</p>
              <p className="text-xs text-text-muted">Auto-payout configuration</p>
            </div>
          </div>
        )}
      </div>

      <p className="mb-3 text-xs font-semibold text-text-muted">REQUESTS</p>
      {items.length === 0 ? (
        <EmptyState icon={Banknote} title="No disbursement requests" description="Request a payout from the pool — members vote to approve it." />
      ) : (
        <div className="space-y-3">
          {items.map(d => (
            <div key={d.id} className="rounded-lg border border-border bg-surface p-4">
              <div className="flex items-center justify-between">
                <p className="text-lg font-bold text-text">{formatMoney(d.amount)}</p>
                <Badge tone={statusTone(d.status)}>{d.status}</Badge>
              </div>
              <p className="mt-1 text-sm text-text-secondary">{d.reason}</p>
              <p className="mt-1 text-xs text-text-muted">To {d.recipient_phone} · {d.approve_count}/{d.required_approvals} approvals</p>
              {d.status === 'PENDING' && (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" loading={busy === d.id} onClick={() => vote(d.id, 'APPROVE')}><Check size={15} /> Approve</Button>
                  <Button size="sm" variant="outline" onClick={() => vote(d.id, 'REJECT')}><X size={15} /> Reject</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <RequestPayoutModal open={open} onClose={() => setOpen(false)} id={id} onDone={load} />
    </div>
  )
}

function RequestPayoutModal({ open, onClose, id, onDone }: { open: boolean; onClose: () => void; id: string; onDone: () => void }) {
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [phone, setPhone] = useState('')
  const [saving, setSaving] = useState(false)
  async function submit() {
    if (!amount || !reason.trim()) return toast.error('Enter an amount and reason')
    setSaving(true)
    try { await contributions.createDisbursement(id, { amount: Number(amount), reason, recipient_phone: phone || undefined }); toast.success('Request submitted'); setAmount(''); setReason(''); setPhone(''); onClose(); onDone() }
    catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Request a payout">
      <div className="flex flex-col gap-4">
        <Input label="Amount (KES)" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} autoFocus />
        <Textarea label="Reason" value={reason} onChange={e => setReason(e.target.value)} placeholder="What is this payout for?" />
        <Input label="Recipient phone (optional)" type="tel" value={phone} onChange={e => setPhone(e.target.value)} hint="Defaults to you." />
        <Button onClick={submit} loading={saving} fullWidth>Submit request</Button>
      </div>
    </Modal>
  )
}

type PoolSheet = null | 'income' | 'expense' | 'distribute'

function PoolTab({ id }: { id: string }) {
  const myId = useAuthStore(s => s.user?.id)
  const [items, setItems] = useState<PoolActionRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [sheet, setSheet] = useState<PoolSheet>(null)
  const [busy, setBusy] = useState<number | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    contributions.poolActions(id).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [id])
  useEffect(() => { load() }, [load])

  async function decide(fn: Promise<unknown>, reqId: number, done: string) {
    setBusy(reqId)
    try { await fn; toast.success(done); load() }
    catch (e) { toast.error(apiError(e)) } finally { setBusy(null) }
  }

  if (loading) return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>

  const cards: { key: PoolSheet; icon: typeof ArrowDownCircle; title: string; hint: string }[] = [
    { key: 'income',     icon: ArrowDownCircle, title: 'Record income',       hint: 'External / business proceeds' },
    { key: 'expense',    icon: ShoppingCart,    title: 'Propose expense',      hint: 'Spend pool — needs a 2nd admin' },
    { key: 'distribute', icon: Split,           title: 'Propose distribution', hint: 'Share surplus — needs a 2nd admin' },
  ]

  return (
    <div>
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        {cards.map(({ key, icon: Icon, title, hint }) => (
          <button key={key} onClick={() => setSheet(key)}
            className="flex flex-col items-start gap-2 rounded-lg border border-border bg-surface p-4 text-left transition-colors hover:border-primary/40 hover:bg-primary-bg/40">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-pale text-primary"><Icon size={18} /></div>
            <div>
              <p className="text-sm font-semibold text-text">{title}</p>
              <p className="text-xs text-text-muted">{hint}</p>
            </div>
          </button>
        ))}
      </div>

      <p className="mb-3 text-xs font-semibold text-text-muted">COLLECTIVE-FUND ACTIVITY</p>
      {items.length === 0 ? (
        <EmptyState icon={Banknote} title="No pool actions yet" description="Record income, or propose an expense or distribution for a second admin to approve." />
      ) : (
        <div className="space-y-3">
          {items.map(a => {
            const mine = myId != null && a.requested_by === myId
            return (
              <div key={a.id} className="rounded-lg border border-border bg-surface p-4">
                <div className="flex items-center justify-between">
                  <p className="text-lg font-bold text-text">{formatMoney(a.amount)}</p>
                  <Badge tone={statusTone(a.status)}>{a.status}</Badge>
                </div>
                <p className="mt-1 text-sm text-text-secondary">
                  {a.action === 'EXPENSE' ? 'Pool expense' : 'Surplus distribution'} · {a.apportion === 'pro_rata' ? 'pro-rata' : 'per-capita'}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  by {a.requested_by_name}{a.status === 'PENDING' ? ` · ${a.approval_count} approval(s)` : ''}{a.memo ? ` · ${a.memo}` : ''}
                </p>
                {a.status === 'PENDING' && (
                  <div className="mt-3 flex gap-2">
                    {mine ? (
                      <Button size="sm" variant="outline" loading={busy === a.id}
                        onClick={() => decide(contributions.cancelPoolAction(a.id), a.id, 'Withdrawn')}>Withdraw</Button>
                    ) : (
                      <>
                        <Button size="sm" loading={busy === a.id}
                          onClick={() => decide(contributions.approvePoolAction(a.id), a.id, 'Approved')}><Check size={15} /> Approve</Button>
                        <Button size="sm" variant="outline"
                          onClick={() => decide(contributions.rejectPoolAction(a.id), a.id, 'Rejected')}><X size={15} /> Reject</Button>
                      </>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      <PoolActionModal sheet={sheet} onClose={() => setSheet(null)} id={id} onDone={load} />
    </div>
  )
}

function PoolActionModal({ sheet, onClose, id, onDone }: {
  sheet: PoolSheet; onClose: () => void; id: string; onDone: () => void
}) {
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [apportion, setApportion] = useState<'pro_rata' | 'per_capita'>('pro_rata')
  const [loading, setLoading] = useState(false)

  useEffect(() => { if (sheet) { setAmount(''); setNote(''); setApportion('pro_rata') } }, [sheet])

  const title = sheet === 'income' ? 'Record income' : sheet === 'expense' ? 'Propose expense' : 'Propose distribution'

  async function submit() {
    if (!amount.trim()) return
    setLoading(true)
    try {
      if (sheet === 'income') { await contributions.recordExternalIncome(id, { amount, source: note }); toast.success('Income recorded') }
      else if (sheet === 'expense') { await contributions.requestPoolExpense(id, { amount, apportion, reason: note }); toast.success('Proposed — awaiting a 2nd admin') }
      else if (sheet === 'distribute') { await contributions.requestDistribution(id, { amount, apportion, reason: note }); toast.success('Proposed — awaiting a 2nd admin') }
      onClose(); onDone()
    } catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
  }

  return (
    <Modal open={sheet !== null} onClose={onClose} title={title}>
      <div className="space-y-3">
        <Input label="Amount (KES)" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} />
        {sheet !== 'income' && (
          <div className="flex gap-2">
            {(['pro_rata', 'per_capita'] as const).map(m => (
              <button key={m} onClick={() => setApportion(m)}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${apportion === m ? 'border-primary bg-primary-pale text-primary' : 'border-border text-text-secondary hover:bg-primary-bg/40'}`}>
                {m === 'pro_rata' ? 'Pro-rata' : 'Per-capita'}
              </button>
            ))}
          </div>
        )}
        <Input label={sheet === 'income' ? 'Source (optional)' : 'Reason (optional)'} value={note} onChange={e => setNote(e.target.value)} />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button loading={loading} disabled={!amount.trim()} onClick={submit}>{sheet === 'income' ? 'Record' : 'Propose'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function AmendmentsTab({ id }: { id: string }) {
  const [items, setItems] = useState<ContributionAmendment[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<number | null>(null)
  const load = useCallback(() => {
    setLoading(true)
    contributions.amendments(id).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [id])
  useEffect(() => { load() }, [load])

  async function vote(aid: number, v: 'APPROVE' | 'REJECT') {
    setBusy(aid)
    try { await contributions.voteAmendment(aid, v); toast.success('Vote recorded'); load() }
    catch (e) { toast.error(apiError(e)) } finally { setBusy(null) }
  }

  if (loading) return <div className="space-y-2">{Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
  if (items.length === 0) return <EmptyState icon={FileEdit} title="No amendments" description="Proposed rule changes will appear here for voting." />

  return (
    <div className="space-y-3">
      {items.map(a => (
        <div key={a.id} className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-text">Proposed by {a.proposed_by_name || a.proposed_by_phone}</p>
            <Badge tone={statusTone(a.status)}>{a.status}</Badge>
          </div>
          <div className="mt-2 space-y-1">
            {a.changes_display.map((ch, i) => (
              <p key={i} className="text-sm text-text-secondary"><span className="font-medium">{ch.field}:</span> {ch.from} → {ch.to}</p>
            ))}
          </div>
          {a.reason && <p className="mt-2 text-sm text-text-muted">{a.reason}</p>}
          <p className="mt-1 text-xs text-text-muted">{a.approve_count}/{a.required_approvals} approvals · {formatDate(a.created_at)}</p>
          {a.status === 'PENDING' && (
            <div className="mt-3 flex gap-2">
              <Button size="sm" loading={busy === a.id} onClick={() => vote(a.id, 'APPROVE')}><Check size={15} /> Approve</Button>
              <Button size="sm" variant="outline" onClick={() => vote(a.id, 'REJECT')}><X size={15} /> Reject</Button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
