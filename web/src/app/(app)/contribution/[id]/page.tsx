'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { contributions as contribApi, payments } from '@/lib/api'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Tabs } from '@/components/ui/Tabs'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { ArrowLeft, DollarSign, Users, ArrowUpCircle, GitMerge, RefreshCw, Send, Check, X } from 'lucide-react'
import { toast } from 'sonner'
import { formatMoney, formatDate, formatRelative } from '@/lib/utils'
import { cn } from '@/lib/utils'

const TABS = [
  { id: 'transactions',  label: 'Transactions' },
  { id: 'members',       label: 'Members' },
  { id: 'disbursements', label: 'Disbursements' },
  { id: 'amendments',   label: 'Amendments' },
]

const TX_TYPE_STYLES: Record<string, { label: string; color: string }> = {
  CONTRIBUTION: { label: 'Contribution', color: 'text-primary' },
  WITHDRAWAL:   { label: 'Withdrawal',   color: 'text-error' },
  ADVANCE:      { label: 'Advance',      color: 'text-accent' },
  REPAYMENT:    { label: 'Repayment',    color: 'text-primary' },
}

export default function ContributionPage() {
  const { id }  = useParams<{ id: string }>()
  const router  = useRouter()
  const [contrib, setContrib]           = useState<Record<string,unknown> | null>(null)
  const [transactions, setTransactions] = useState<TxItem[]>([])
  const [members, setMembers]           = useState<MemItem[]>([])
  const [disbursements, setDisbursements] = useState<DisbItem[]>([])
  const [amendments, setAmendments]     = useState<AmendItem[]>([])
  const [activeTab, setActiveTab]       = useState('transactions')
  const [loading, setLoading]           = useState(true)
  const [showContribute, setShowContribute] = useState(false)
  const [showPayout, setShowPayout]     = useState(false)

  const load = useCallback(async () => {
    try {
      const [c, txs, mems, disbs, amends] = await Promise.all([
        contribApi.get(id),
        contribApi.transactions(id),
        contribApi.members(id),
        contribApi.disbursements(id),
        contribApi.amendments(id),
      ])
      setContrib(c.data)
      setTransactions(txs.data.results ?? txs.data)
      setMembers(mems.data.results ?? mems.data)
      setDisbursements(disbs.data.results ?? disbs.data)
      setAmendments(amends.data.results ?? amends.data)
    } catch {
      toast.error('Failed to load contribution')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  if (loading) return <PageLoader />
  if (!contrib) return null

  const c = contrib as {
    title: string; description?: string; frequency: string; amount_type: string;
    fixed_amount?: string; voting_threshold: string; total_balance?: string;
    member_count?: number; my_balance?: string; my_rosca_slot?: RoscaSlot
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-divider px-6 py-4 sticky top-0 z-10">
        <div className="flex items-center gap-3 mb-4">
          <button onClick={() => router.back()} className="p-1.5 rounded-lg hover:bg-divider text-text-secondary">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="font-semibold text-text text-lg">{c.title}</h1>
            <p className="text-sm text-text-secondary">{c.description}</p>
          </div>
          <div className="ml-auto flex gap-2">
            <Button size="sm" onClick={() => setShowContribute(true)}>
              <Send size={14} /> Contribute
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setShowPayout(true)}>
              <ArrowUpCircle size={14} /> Request Payout
            </Button>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Pool Balance" value={formatMoney(c.total_balance ?? 0)} />
          <StatCard label="My Balance" value={formatMoney(c.my_balance ?? 0)} />
          <StatCard
            label="Frequency"
            value={`${c.frequency.charAt(0).toUpperCase() + c.frequency.slice(1)} · ${c.amount_type === 'fixed' && c.fixed_amount ? `KES ${Number(c.fixed_amount).toLocaleString()}` : 'Open'}`}
          />
        </div>

        {/* ROSCA slot if exists */}
        {c.my_rosca_slot && <RoscaBanner slot={c.my_rosca_slot} />}
      </div>

      {/* Tabs */}
      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} className="bg-white px-4 sticky top-[161px] z-10" />

      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'transactions' && <TransactionsList txs={transactions} />}
        {activeTab === 'members' && <MembersList members={members} />}
        {activeTab === 'disbursements' && <DisbursementsList disbs={disbursements} contribId={id} onVote={load} />}
        {activeTab === 'amendments' && <AmendmentsList amends={amendments} />}
      </div>

      {/* Contribute modal */}
      <Modal open={showContribute} onClose={() => setShowContribute(false)} title="Make a Contribution">
        <ContributeForm
          contribId={id}
          amountType={c.amount_type}
          fixedAmount={c.fixed_amount}
          onSuccess={() => { setShowContribute(false); load() }}
        />
      </Modal>

      {/* Payout modal */}
      <Modal open={showPayout} onClose={() => setShowPayout(false)} title="Request Payout">
        <PayoutForm contribId={id} onSuccess={() => { setShowPayout(false); load() }} />
      </Modal>
    </div>
  )
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-primary-pale rounded-lg px-4 py-3">
      <p className="text-xs text-text-secondary mb-0.5">{label}</p>
      <p className="font-semibold text-text text-sm">{value}</p>
    </div>
  )
}

// ── ROSCA banner ──────────────────────────────────────────────────────────────
interface RoscaSlot { slot_order: number; cycle_number: number; has_received: boolean; payout_amount?: string }
function RoscaBanner({ slot }: { slot: RoscaSlot }) {
  return (
    <div className={cn('mt-3 rounded-lg px-4 py-3 flex items-center gap-3',
      slot.has_received ? 'bg-divider' : 'bg-accent-pale')}>
      <RefreshCw size={16} className={slot.has_received ? 'text-text-muted' : 'text-accent'} />
      <p className="text-sm">
        {slot.has_received
          ? `ROSCA slot #${slot.slot_order} — payout already received this cycle.`
          : <>ROSCA slot <strong>#{slot.slot_order}</strong> · Cycle {slot.cycle_number}
            {slot.payout_amount && <> — payout <strong>{formatMoney(slot.payout_amount)}</strong></>}
          </>
        }
      </p>
    </div>
  )
}

// ── Transactions ──────────────────────────────────────────────────────────────
interface TxItem {
  id: string; name: string; phone_number: string; amount: string;
  transaction_type: string; note?: string; mpesa_receipt?: string; created_at: string
}

function TransactionsList({ txs }: { txs: TxItem[] }) {
  if (!txs.length) return <EmptyState icon={DollarSign} title="No transactions yet" />
  return (
    <div className="space-y-2">
      {txs.map(tx => {
        const t = TX_TYPE_STYLES[tx.transaction_type] ?? { label: tx.transaction_type, color: 'text-text' }
        const sign = ['WITHDRAWAL', 'ADVANCE'].includes(tx.transaction_type) ? '-' : '+'
        return (
          <div key={tx.id} className="flex items-center gap-3 bg-white rounded-lg px-4 py-3.5 shadow-card">
            <div className="w-9 h-9 rounded-full bg-primary-pale flex items-center justify-center flex-shrink-0">
              <DollarSign size={16} className="text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-text text-sm">{tx.name}</p>
              <p className="text-xs text-text-muted">{t.label} · {tx.mpesa_receipt ?? tx.phone_number}</p>
              {tx.note && <p className="text-xs text-text-secondary mt-0.5 italic">{tx.note}</p>}
            </div>
            <div className="text-right shrink-0">
              <p className={cn('font-semibold text-sm', t.color)}>{sign}{formatMoney(tx.amount)}</p>
              <p className="text-xs text-text-muted">{formatRelative(tx.created_at)}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Members ───────────────────────────────────────────────────────────────────
interface MemItem { id: string; name: string; phone_number: string; balance?: string; profile_photo?: string }
function MembersList({ members }: { members: MemItem[] }) {
  if (!members.length) return <EmptyState icon={Users} title="No members yet" />
  return (
    <div className="space-y-1">
      {members.map(m => (
        <div key={m.id} className="flex items-center gap-3 bg-white rounded-lg px-4 py-3">
          <Avatar name={m.name} src={m.profile_photo} size="md" />
          <div className="flex-1 min-w-0">
            <p className="font-medium text-text">{m.name}</p>
            <p className="text-sm text-text-muted">{m.phone_number}</p>
          </div>
          {m.balance !== undefined && (
            <p className="text-sm font-semibold text-text">{formatMoney(m.balance)}</p>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Disbursements ─────────────────────────────────────────────────────────────
interface DisbItem {
  id: string; amount: string; recipient_name?: string; status: string;
  approve_count?: number; reject_count?: number; created_at: string; note?: string
}

const DISB_STATUS: Record<string, { variant: 'approved'|'pending'|'rejected'|'default'; label: string }> = {
  PENDING:  { variant: 'pending',  label: 'Pending' },
  APPROVED: { variant: 'approved', label: 'Approved' },
  REJECTED: { variant: 'rejected', label: 'Rejected' },
  EXECUTED: { variant: 'approved', label: 'Executed' },
}

function DisbursementsList({ disbs, contribId, onVote }: { disbs: DisbItem[]; contribId: string; onVote: () => void }) {
  const [voting, setVoting] = useState<string | null>(null)

  async function vote(disbId: string, v: 'APPROVE' | 'REJECT') {
    setVoting(disbId + v)
    try {
      await contribApi.voteDisbursement(contribId, disbId, v)
      toast.success(v === 'APPROVE' ? 'Approved!' : 'Rejected')
      onVote()
    } catch { toast.error('Vote failed') }
    finally { setVoting(null) }
  }

  if (!disbs.length) return <EmptyState icon={GitMerge} title="No disbursements yet" />
  return (
    <div className="space-y-3">
      {disbs.map(d => {
        const st = DISB_STATUS[d.status] ?? { variant: 'default' as const, label: d.status }
        return (
          <div key={d.id} className="bg-white rounded-lg p-4 shadow-card">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <p className="font-semibold text-text">{formatMoney(d.amount)}</p>
                {d.recipient_name && <p className="text-sm text-text-secondary">{d.recipient_name}</p>}
                {d.note && <p className="text-sm text-text-muted italic mt-1">{d.note}</p>}
              </div>
              <Badge variant={st.variant}>{st.label}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <p className="text-xs text-text-muted">{formatDate(d.created_at)} · ✓ {d.approve_count ?? 0} ✗ {d.reject_count ?? 0}</p>
              {d.status === 'PENDING' && (
                <div className="flex gap-2">
                  <Button
                    size="sm" variant="secondary"
                    loading={voting === d.id + 'REJECT'}
                    onClick={() => vote(d.id, 'REJECT')}
                  >
                    <X size={13} /> Reject
                  </Button>
                  <Button
                    size="sm"
                    loading={voting === d.id + 'APPROVE'}
                    onClick={() => vote(d.id, 'APPROVE')}
                  >
                    <Check size={13} /> Approve
                  </Button>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Amendments ────────────────────────────────────────────────────────────────
interface AmendItem { id: string; field: string; new_value: string; status: string; created_at: string }
function AmendmentsList({ amends }: { amends: AmendItem[] }) {
  if (!amends.length) return <EmptyState icon={GitMerge} title="No amendments proposed" />
  return (
    <div className="space-y-2">
      {amends.map(a => (
        <div key={a.id} className="flex items-center gap-3 bg-white rounded-lg px-4 py-3 shadow-card">
          <div className="flex-1">
            <p className="font-medium text-text capitalize">{a.field.replace(/_/g, ' ')}</p>
            <p className="text-sm text-text-secondary">→ {a.new_value}</p>
          </div>
          <div className="text-right">
            <Badge variant={a.status === 'APPROVED' ? 'approved' : a.status === 'REJECTED' ? 'rejected' : 'pending'}>
              {a.status}
            </Badge>
            <p className="text-xs text-text-muted mt-1">{formatDate(a.created_at)}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Forms ─────────────────────────────────────────────────────────────────────
function ContributeForm({ contribId, amountType, fixedAmount, onSuccess }: {
  contribId: string; amountType: string; fixedAmount?: string; onSuccess: () => void
}) {
  const [phone, setPhone]   = useState('')
  const [amount, setAmount] = useState(fixedAmount ?? '')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await payments.stkPush({ phone_number: phone, amount, contribution: contribId })
      toast.success('STK push sent — check your phone to complete payment.')
      onSuccess()
    } catch { toast.error('Payment initiation failed') }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input label="M-Pesa phone number" type="tel" placeholder="+254 7XX XXX XXX" value={phone} onChange={e => setPhone(e.target.value)} autoFocus />
      {amountType !== 'fixed' && (
        <Input label="Amount (KES)" type="number" value={amount} onChange={e => setAmount(e.target.value)} />
      )}
      {amountType === 'fixed' && fixedAmount && (
        <p className="text-sm text-text-secondary">Amount: <strong className="text-text">{formatMoney(fixedAmount)}</strong></p>
      )}
      <div className="flex justify-end gap-3">
        <Button type="submit" loading={loading}>Send STK Push</Button>
      </div>
    </form>
  )
}

function PayoutForm({ contribId, onSuccess }: { contribId: string; onSuccess: () => void }) {
  const [amount, setAmount] = useState('')
  const [note, setNote]     = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await contribApi.requestPayout(contribId, { amount, note })
      toast.success('Payout request submitted for approval')
      onSuccess()
    } catch { toast.error('Request failed') }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input label="Amount (KES)" type="number" value={amount} onChange={e => setAmount(e.target.value)} autoFocus />
      <Input label="Note (optional)" value={note} onChange={e => setNote(e.target.value)} placeholder="Reason for withdrawal" />
      <div className="flex justify-end gap-3">
        <Button type="submit" loading={loading}>Submit Request</Button>
      </div>
    </form>
  )
}
