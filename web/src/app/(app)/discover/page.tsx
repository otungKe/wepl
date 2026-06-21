'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Compass, Search, Users } from 'lucide-react'
import { communities, apiError, type Community } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { toast } from 'sonner'

export default function DiscoverPage() {
  const router = useRouter()
  const [items, setItems] = useState<Community[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [pending, setPending] = useState<number | null>(null)

  async function load(query = '') {
    setLoading(true)
    try { setItems(await communities.discover(query || undefined)) }
    catch (err) { toast.error(apiError(err)) }
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

  return (
    <div>
      <PageHeader title="Discover" subtitle="Find public communities to join" />
      <div className="relative mb-4">
        <Search size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search public communities"
          className="h-11 w-full rounded-lg border border-border bg-white pl-10 pr-3 text-base focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20" />
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
      ) : items.length === 0 ? (
        <EmptyState icon={Compass} title="Nothing to discover" description="There are no public communities matching your search." />
      ) : (
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
              ) : (
                <Button size="sm" loading={pending === c.id} onClick={() => join(c)}>
                  {c.join_policy === 'open' ? 'Join' : 'Request'}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
