'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Coins, Smartphone, TrendingUp, Lock } from 'lucide-react'
import { shares, payments, apiError, type SharesFund } from '@/lib/api'
import { useTier } from '@/hooks/useTier'
import { PageHeader } from '@/components/app/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Avatar } from '@/components/ui/Avatar'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { formatMoney } from '@/lib/utils'
import { toast } from 'sonner'

export default function SharesPage() {
  const { communityId } = useParams<{ communityId: string }>()
  const router = useRouter()
  const { isVerified } = useTier()
  const [fund, setFund] = useState<SharesFund | null>(null)
  const [loading, setLoading] = useState(true)
  const [payOpen, setPayOpen] = useState(false)

  const load = useCallback(() => {
    shares.get(communityId).then(r => setFund(r.data)).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [communityId])
  useEffect(() => { load() }, [load])

  if (loading) return <PageLoader />
  if (!fund) return <EmptyState title="Shares fund not found" />

  return (
    <div>
      <PageHeader title="Shares fund" subtitle={fund.name} back
        action={isVerified
          ? <Button size="sm" onClick={() => setPayOpen(true)}><Smartphone size={15} /> Buy shares</Button>
          : <Button size="sm" variant="outline" title="Verify your identity to buy shares" onClick={() => router.push('/kyc')}><Lock size={15} /> Buy shares</Button>
        } />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <StatCard accent label="Total pool" value={formatMoney(fund.total_pool)} icon={Coins} />
        <StatCard label="Share price" value={formatMoney(fund.share_price)} />
        <StatCard label="Total shares" value={Number(fund.total_shares).toLocaleString()} icon={TrendingUp} />
      </div>

      <h2 className="mb-3 font-semibold text-text">Top holders</h2>
      {fund.holdings.length === 0 ? (
        <EmptyState icon={Coins} title="No shareholders yet" description="Buy shares to become the first holder." />
      ) : (
        <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
          {[...fund.holdings].sort((a, b) => Number(b.shares_count) - Number(a.shares_count)).map(h => (
            <div key={h.id} className="flex items-center gap-3 p-3.5">
              <Avatar name={h.name || h.phone_number} size={38} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-text">{h.name || h.phone_number}</p>
                <p className="text-xs text-text-muted">{Number(h.shares_count).toLocaleString()} shares · {h.ownership_pct}%</p>
              </div>
              <p className="font-semibold text-text">{formatMoney(h.total_contributed)}</p>
            </div>
          ))}
        </div>
      )}

      <BuyModal open={payOpen} onClose={() => setPayOpen(false)} communityId={Number(communityId)} />
    </div>
  )
}

function BuyModal({ open, onClose, communityId }: { open: boolean; onClose: () => void; communityId: number }) {
  const [amount, setAmount] = useState(''); const [loading, setLoading] = useState(false)
  async function pay() {
    const amt = Number(amount); if (!amt) return toast.error('Enter an amount')
    setLoading(true)
    try { await payments.stkPush({ payment_type: 'shares', community_id: communityId, amount: amt }); toast.success('Check your phone to authorize payment'); setAmount(''); onClose() }
    catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Buy shares">
      <div className="flex flex-col gap-4">
        <Input label="Amount (KES)" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} hint="Shares are allocated at the current share price." autoFocus />
        <Button onClick={pay} loading={loading} fullWidth><Smartphone size={16} /> Send STK push</Button>
      </div>
    </Modal>
  )
}
