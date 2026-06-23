'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Clock, CheckCircle2, Compass } from 'lucide-react'
import { communities, apiError, type MyJoinRequest } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Avatar } from '@/components/ui/Avatar'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatRelative } from '@/lib/utils'
import { toast } from 'sonner'

export default function RequestsPage() {
  const router = useRouter()
  const [items, setItems] = useState<MyJoinRequest[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    communities.myRequests().then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <PageHeader title="Pending requests" subtitle="Community join requests awaiting an admin's review" />

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : items.length === 0 ? (
        <EmptyState icon={CheckCircle2} title="No pending requests" description="All your community join requests have been resolved."
          action={<Button onClick={() => router.push('/discover')}><Compass size={16} /> Browse communities</Button>} />
      ) : (
        <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
          {items.map(r => (
            <Link key={r.id} href={`/community/${r.community_id}`} className="flex items-center gap-3 p-4 hover:bg-divider/50">
              <Avatar name={r.community_name} src={r.community_photo} size={44} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-text">{r.community_name}</p>
                <p className="truncate text-sm text-text-muted">{r.member_count} member{r.member_count !== 1 ? 's' : ''} · {formatRelative(r.created_at)}</p>
              </div>
              <Badge tone="warning"><Clock size={11} /> Pending</Badge>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
