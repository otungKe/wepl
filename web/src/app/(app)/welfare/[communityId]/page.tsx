'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { welfare as welfareApi } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { ArrowLeft, HeartHandshake } from 'lucide-react'
import { formatMoney, formatDate } from '@/lib/utils'
import { toast } from 'sonner'

interface Claim {
  id: string; amount: string; reason: string; status: string; created_at: string; claimant_name?: string
}

export default function WelfarePage() {
  const { communityId } = useParams<{ communityId: string }>()
  const router          = useRouter()
  const [fund, setFund]     = useState<{ balance?: string; monthly_amount?: string } | null>(null)
  const [claims, setClaims] = useState<Claim[]>([])
  const [loading, setLoading] = useState(true)
  const [showClaim, setShowClaim] = useState(false)

  const load = useCallback(async () => {
    try {
      const [f, c] = await Promise.all([welfareApi.get(communityId), welfareApi.claims(communityId)])
      setFund(f.data)
      setClaims(c.data.results ?? c.data)
    } catch { toast.error('Failed to load welfare fund') }
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
        <HeartHandshake size={22} className="text-primary" />
        <h1 className="text-2xl font-bold text-text">Welfare Fund</h1>
        <Button size="sm" className="ml-auto" onClick={() => setShowClaim(true)}>Submit Claim</Button>
      </div>

      {/* Fund stats */}
      {fund && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="bg-primary-pale rounded-lg px-4 py-4">
            <p className="text-xs text-text-secondary mb-1">Fund Balance</p>
            <p className="text-xl font-bold text-primary">{formatMoney(fund.balance ?? 0)}</p>
          </div>
          <div className="bg-white rounded-lg px-4 py-4 shadow-card">
            <p className="text-xs text-text-secondary mb-1">Monthly Contribution</p>
            <p className="text-xl font-bold text-text">{formatMoney(fund.monthly_amount ?? 0)}</p>
          </div>
        </div>
      )}

      {/* Claims */}
      <h2 className="text-lg font-semibold text-text mb-3">Claims</h2>
      {claims.length === 0 ? (
        <EmptyState icon={HeartHandshake} title="No claims yet" description="Members can submit claims when they need support." />
      ) : (
        <div className="space-y-2">
          {claims.map(c => (
            <div key={c.id} className="bg-white rounded-lg px-4 py-4 shadow-card flex items-start gap-4">
              <div className="flex-1">
                <p className="font-medium text-text">{c.claimant_name ?? 'Member'}</p>
                <p className="text-sm text-text-secondary mt-0.5">{c.reason}</p>
                <p className="text-xs text-text-muted mt-1">{formatDate(c.created_at)}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="font-semibold text-text">{formatMoney(c.amount)}</p>
                <Badge
                  className="mt-1"
                  variant={c.status === 'APPROVED' ? 'approved' : c.status === 'REJECTED' ? 'rejected' : 'pending'}
                >
                  {c.status}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={showClaim} onClose={() => setShowClaim(false)} title="Submit Welfare Claim">
        <ClaimForm communityId={communityId} onSuccess={() => { setShowClaim(false); load() }} />
      </Modal>
    </div>
  )
}

function ClaimForm({ communityId, onSuccess }: { communityId: string; onSuccess: () => void }) {
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await welfareApi.submitClaim(communityId, { amount, reason })
      toast.success('Claim submitted for review')
      onSuccess()
    } catch { toast.error('Submission failed') }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input label="Amount requested (KES)" type="number" value={amount} onChange={e => setAmount(e.target.value)} autoFocus />
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium">Reason</label>
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Briefly explain the reason for this claim…"
          rows={3}
          className="rounded border border-border px-4 py-3 text-base text-text placeholder:text-text-muted focus:outline-none focus:border-primary resize-none"
        />
      </div>
      <div className="flex justify-end gap-3">
        <Button type="submit" loading={loading}>Submit Claim</Button>
      </div>
    </form>
  )
}
