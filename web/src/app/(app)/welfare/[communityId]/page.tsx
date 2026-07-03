'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { HeartHandshake, Plus, Check, X, Smartphone, Lock } from 'lucide-react'
import { welfare, payments, apiError, type WelfareFund, type WelfareClaim } from '@/lib/api'
import { useTier } from '@/hooks/useTier'
import { PageHeader } from '@/components/app/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { Button } from '@/components/ui/Button'
import { Input, Textarea } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Badge, statusTone } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader, Skeleton } from '@/components/ui/Spinner'
import { formatMoney, formatDate } from '@/lib/utils'
import { toast } from 'sonner'

export default function WelfarePage() {
  const { communityId } = useParams<{ communityId: string }>()
  const router = useRouter()
  const { isVerified } = useTier()
  const [fund, setFund] = useState<WelfareFund | null>(null)
  const [claims, setClaims] = useState<WelfareClaim[]>([])
  const [loading, setLoading] = useState(true)
  const [claimOpen, setClaimOpen] = useState(false)
  const [payOpen, setPayOpen] = useState(false)
  const [busy, setBusy] = useState<number | null>(null)

  const load = useCallback(() => {
    Promise.all([welfare.get(communityId), welfare.claims(communityId)])
      .then(([f, c]) => { setFund(f.data); setClaims(c) })
      .catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [communityId])
  useEffect(() => { load() }, [load])

  async function vote(claimId: number, action: 'approve' | 'reject') {
    setBusy(claimId)
    try { await welfare.voteClaim(claimId, action); toast.success('Vote recorded'); load() }
    catch (e) { toast.error(apiError(e)) } finally { setBusy(null) }
  }

  if (loading) return <PageLoader />
  if (!fund) return <EmptyState title="Welfare fund not found" />

  return (
    <div>
      <PageHeader title="Welfare fund" subtitle={fund.name} back
        action={isVerified
          ? <Button size="sm" onClick={() => setPayOpen(true)}><Smartphone size={15} /> Contribute</Button>
          : <Button size="sm" variant="outline" title="Verify your identity to contribute" onClick={() => router.push('/kyc')}><Lock size={15} /> Contribute</Button>
        } />

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <StatCard accent label="Fund balance" value={formatMoney(fund.balance)} icon={HeartHandshake} />
        <StatCard label="Monthly contribution" value={formatMoney(fund.monthly_contribution)} />
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-text">Claims</h2>
        <Button size="sm" variant="outline" onClick={() => setClaimOpen(true)}><Plus size={15} /> Submit claim</Button>
      </div>

      {claims.length === 0 ? (
        <EmptyState icon={HeartHandshake} title="No claims yet" description="Members can request support from the fund." />
      ) : (
        <div className="space-y-3">
          {claims.map(cl => (
            <div key={cl.id} className="rounded-lg border border-border bg-surface p-4">
              <div className="flex items-center justify-between">
                <p className="text-lg font-bold text-text">{formatMoney(cl.amount_requested)}</p>
                <Badge tone={statusTone(cl.status)}>{cl.status}</Badge>
              </div>
              <p className="mt-1 text-sm text-text-secondary">{cl.reason}</p>
              <p className="mt-1 text-xs text-text-muted">{cl.claimant_phone} · {formatDate(cl.created_at)} · {cl.approve_count} approvals</p>
              {cl.status === 'PENDING' && fund.is_admin && (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" loading={busy === cl.id} onClick={() => vote(cl.id, 'approve')}><Check size={15} /> Approve</Button>
                  <Button size="sm" variant="outline" onClick={() => vote(cl.id, 'reject')}><X size={15} /> Reject</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <ClaimModal open={claimOpen} onClose={() => setClaimOpen(false)} communityId={communityId} onDone={load} />
      <ContributeModal open={payOpen} onClose={() => setPayOpen(false)} communityId={Number(communityId)} />
    </div>
  )
}

function ClaimModal({ open, onClose, communityId, onDone }: { open: boolean; onClose: () => void; communityId: string; onDone: () => void }) {
  const [amount, setAmount] = useState(''); const [reason, setReason] = useState(''); const [saving, setSaving] = useState(false)
  async function submit() {
    if (!amount || !reason.trim()) return toast.error('Enter amount and reason')
    setSaving(true)
    try { await welfare.submitClaim(communityId, { amount_requested: Number(amount), reason }); toast.success('Claim submitted'); setAmount(''); setReason(''); onClose(); onDone() }
    catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Submit a claim">
      <div className="flex flex-col gap-4">
        <Input label="Amount (KES)" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} autoFocus />
        <Textarea label="Reason" value={reason} onChange={e => setReason(e.target.value)} placeholder="Describe your situation" />
        <Button onClick={submit} loading={saving} fullWidth>Submit claim</Button>
      </div>
    </Modal>
  )
}

function ContributeModal({ open, onClose, communityId }: { open: boolean; onClose: () => void; communityId: number }) {
  const [amount, setAmount] = useState(''); const [loading, setLoading] = useState(false)
  async function pay() {
    const amt = Number(amount); if (!amt) return toast.error('Enter an amount')
    setLoading(true)
    try { await payments.stkPush({ payment_type: 'welfare', community_id: communityId, amount: amt }); toast.success('Check your phone to authorize payment'); setAmount(''); onClose() }
    catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Contribute to welfare">
      <div className="flex flex-col gap-4">
        <Input label="Amount (KES)" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} autoFocus />
        <Button onClick={pay} loading={loading} fullWidth><Smartphone size={16} /> Send STK push</Button>
      </div>
    </Modal>
  )
}
