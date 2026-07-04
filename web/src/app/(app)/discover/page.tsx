'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Compass, Search, Users, Lock, Megaphone } from 'lucide-react'
import { communities, contributions, apiError, type Community, type Contribution } from '@/lib/api'
import { useTier } from '@/hooks/useTier'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatMoney } from '@/lib/utils'
import { toast } from 'sonner'

export default function DiscoverPage() {
  const router = useRouter()
  const [items, setItems] = useState<Community[]>([])
  const [campaigns, setCampaigns] = useState<Contribution[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [pending, setPending] = useState<number | null>(null)
  const { isVerified } = useTier()

  async function load(query = '') {
    setLoading(true)
    try {
      const [comm, camp] = await Promise.all([
        communities.discover(query || undefined),
        contributions.open().catch(() => [] as Contribution[]),
      ])
      setItems(comm)
      setCampaigns(camp.filter(c => c.is_campaign))
    } catch (err) { toast.error(apiError(err)) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  useEffect(() => {
    const t = setTimeout(() => load(q), 350)
    return () => clearTimeout(t)
  }, [q])

  async function join(c: Community) {
    setPending(c.id)
    try {
      if (c.join_policy === 'open') { await communities.join(c.id); toast.success(`Joined ${c.name}`); router.push(`/community/${c.id}`) }
      else { await communities.requestJoin(c.id); toast.success('Request sent') }
      load(q)
    } catch (err) { toast.error(apiError(err)) } finally { setPending(null) }
  }

  // Campaigns are filtered client-side by the same query (title match).
  const ql = q.trim().toLowerCase()
  const visibleCampaigns = ql ? campaigns.filter(c => c.title.toLowerCase().includes(ql)) : campaigns

  return (
    <div>
      <PageHeader title="Discover" subtitle="Find public communities and campaigns" />
      <div className="relative mb-5">
        <Search size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search communities and campaigns"
          className="h-11 w-full rounded-lg border border-border bg-surface pl-10 pr-3 text-base focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20" />
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
      ) : items.length === 0 && visibleCampaigns.length === 0 ? (
        <EmptyState icon={Compass} title="Nothing to discover" description="There are no public communities or campaigns matching your search." />
      ) : (
        <div className="space-y-6">
          {/* Communities */}
          {items.length > 0 && (
            <section>
              <div className="mb-3 flex items-center gap-2">
                <Users size={16} className="text-primary" />
                <h2 className="text-sm font-semibold text-text">Communities</h2>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {items.map(c => (
                  <div key={c.id} className="flex items-center gap-3 rounded-lg border border-border bg-surface p-4">
                    <Avatar name={c.name} src={c.community_photo} size={44} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-text">{c.name}</p>
                      <p className="flex items-center gap-1 text-sm text-text-muted"><Users size={13} /> {c.member_count}</p>
                    </div>
                    {c.is_member ? (
                      <Button size="sm" variant="outline" onClick={() => router.push(`/community/${c.id}`)}>Open</Button>
                    ) : c.join_request_status === 'PENDING' ? (
                      <Button size="sm" variant="ghost" disabled>Requested</Button>
                    ) : !isVerified ? (
                      // Tier 0: joining requires KYC — nudge to verification (mirrors mobile).
                      <Button size="sm" variant="outline" title="Verify your identity to join" onClick={() => router.push('/kyc')}>
                        <Lock size={13} /> Join
                      </Button>
                    ) : (
                      <Button size="sm" loading={pending === c.id} onClick={() => join(c)}>
                        {c.join_policy === 'open' ? 'Join' : 'Request'}
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Public campaigns */}
          {visibleCampaigns.length > 0 && (
            <section>
              <div className="mb-3 flex items-center gap-2">
                <Megaphone size={16} className="text-accent" />
                <h2 className="text-sm font-semibold text-text">Public campaigns</h2>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {visibleCampaigns.map(c => {
                  const pct = Number(c.target_amount) > 0
                    ? Math.min(Math.round((Number(c.current_amount) / Number(c.target_amount)) * 100), 100) : null
                  return (
                    <div key={c.id} className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-accent-pale text-accent"><Megaphone size={18} /></div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-semibold text-text">{c.title}</p>
                          <p className="truncate text-sm text-text-muted">
                            {formatMoney(c.current_amount)}{Number(c.target_amount) > 0 ? ` of ${formatMoney(c.target_amount ?? '0')}` : ' raised'}
                          </p>
                        </div>
                        {isVerified
                          ? <Button size="sm" onClick={() => router.push(`/contribution/${c.id}`)}>Support</Button>
                          : <Button size="sm" variant="outline" title="Verify your identity to support" onClick={() => router.push('/kyc')}><Lock size={13} /> Support</Button>}
                      </div>
                      {pct !== null && (
                        <div className="h-1.5 overflow-hidden rounded-full bg-divider">
                          <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
