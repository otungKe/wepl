'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { Receipt, Users, Banknote, FileEdit, Plus, Smartphone, Check, X } from 'lucide-react'
import {
  contributions, payments, apiError,
  type Contribution, type Transaction, type Participant, type DisbursementRequest, type ContributionAmendment,
} from '@/lib/api'
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
        action={<Button size="sm" onClick={() => setPayOpen(true)}><Smartphone size={15} /> Contribute</Button>} />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <StatCard accent label="Pool balance" value={formatMoney(c.current_amount)} icon={Banknote} />
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
        { key: 'amendments', label: 'Amendments' },
      ]} />

      {tab === 'transactions' && <TransactionsTab id={id} />}
      {tab === 'members' && <MembersTab id={id} />}
      {tab === 'disbursements' && <DisbursementsTab id={id} isAdmin={c.is_admin} />}
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
      toast.success('Check your phone to authorize the M-Pesa payment')
      onClose(); setAmount(''); setPhone('')
    } catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Contribute via M-Pesa">
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
      <div className="mb-3 flex justify-end"><Button size="sm" onClick={() => setOpen(true)}><Plus size={15} /> Request payout</Button></div>
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
