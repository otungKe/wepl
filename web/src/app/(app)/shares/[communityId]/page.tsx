'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { shares as sharesApi } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { PageLoader } from '@/components/ui/Spinner'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { ArrowLeft, TrendingUp } from 'lucide-react'
import { formatMoney } from '@/lib/utils'
import { toast } from 'sonner'

interface SharesFund {
  balance?: string; share_price?: string; my_shares?: number; total_shares?: number
  top_holders?: { name: string; shares_count: number; percentage: number }[]
}

export default function SharesPage() {
  const { communityId } = useParams<{ communityId: string }>()
  const router          = useRouter()
  const [fund, setFund] = useState<SharesFund | null>(null)
  const [loading, setLoading] = useState(true)
  const [showBuy, setShowBuy] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await sharesApi.get(communityId)
      setFund(data)
    } catch { toast.error('Failed to load shares fund') }
    finally { setLoading(false) }
  }, [communityId])

  useEffect(() => { load() }, [load])

  if (loading) return <PageLoader />

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.back()} className="p-1.5 rounded-lg hover:bg-divider text-text-secondary">
          <ArrowLeft size={18} />
        </button>
        <TrendingUp size={22} className="text-primary" />
        <h1 className="text-2xl font-bold text-text">Shares Fund</h1>
        <Button size="sm" className="ml-auto" onClick={() => setShowBuy(true)}>Buy Shares</Button>
      </div>

      {fund && (
        <>
          <div className="grid grid-cols-2 gap-3 mb-6 sm:grid-cols-4">
            {[
              { label: 'Fund Value', value: formatMoney(fund.balance ?? 0) },
              { label: 'Share Price', value: formatMoney(fund.share_price ?? 0) },
              { label: 'My Shares', value: `${fund.my_shares ?? 0}` },
              { label: 'Total Shares', value: `${fund.total_shares ?? 0}` },
            ].map(({ label, value }) => (
              <div key={label} className="bg-white rounded-lg px-4 py-4 shadow-card">
                <p className="text-xs text-text-secondary mb-1">{label}</p>
                <p className="text-lg font-bold text-text">{value}</p>
              </div>
            ))}
          </div>

          {fund.top_holders && fund.top_holders.length > 0 && (
            <>
              <h2 className="text-lg font-semibold text-text mb-3">Top Holders</h2>
              <div className="space-y-2">
                {fund.top_holders.map((h, i) => (
                  <div key={i} className="flex items-center gap-3 bg-white rounded-lg px-4 py-3 shadow-card">
                    <span className="text-sm font-bold text-text-muted w-5">{i + 1}</span>
                    <div className="flex-1">
                      <p className="font-medium text-text">{h.name}</p>
                      <p className="text-xs text-text-muted">{h.shares_count} shares</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-primary">{h.percentage.toFixed(1)}%</p>
                      <div className="w-20 h-1.5 bg-divider rounded-full mt-1 overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${h.percentage}%` }} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      <Modal open={showBuy} onClose={() => setShowBuy(false)} title="Buy Shares">
        <BuyForm
          sharePrice={fund?.share_price}
          communityId={communityId}
          onSuccess={() => { setShowBuy(false); load() }}
        />
      </Modal>
    </div>
  )
}

function BuyForm({ sharePrice, communityId, onSuccess }: {
  sharePrice?: string; communityId: string; onSuccess: () => void
}) {
  const [qty, setQty]     = useState('1')
  const [loading, setLoading] = useState(false)
  const total = sharePrice ? Number(qty) * Number(sharePrice) : 0

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await sharesApi.buy(communityId, Number(qty))
      toast.success(`Purchased ${qty} shares!`)
      onSuccess()
    } catch { toast.error('Purchase failed') }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input label="Number of shares" type="number" min="1" value={qty} onChange={e => setQty(e.target.value)} autoFocus />
      {sharePrice && (
        <div className="bg-primary-pale rounded-lg px-4 py-3">
          <p className="text-sm text-text-secondary">
            {qty} shares × {formatMoney(sharePrice)} = <strong className="text-text">{formatMoney(total)}</strong>
          </p>
        </div>
      )}
      <div className="flex justify-end">
        <Button type="submit" loading={loading}>Buy Now</Button>
      </div>
    </form>
  )
}
