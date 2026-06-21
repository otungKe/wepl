'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Bell, CheckCheck, Trash2 } from 'lucide-react'
import { notificationsApi, apiError, type Notification } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatRelative, cn } from '@/lib/utils'
import { toast } from 'sonner'

export default function NotificationsPage() {
  const router = useRouter()
  const [items, setItems] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try { setItems(await notificationsApi.list()) }
    catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function open(n: Notification) {
    if (!n.is_read) { notificationsApi.markRead(n.id).catch(() => {}); setItems(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x)) }
    if (n.conversation_id) router.push(`/conversation/${n.conversation_id}`)
    else if (n.contribution_id) router.push(`/contribution/${n.contribution_id}`)
    else if (n.community_id) router.push(`/community/${n.community_id}`)
  }
  async function markAll() {
    try { await notificationsApi.markAllRead(); setItems(prev => prev.map(x => ({ ...x, is_read: true }))); toast.success('All marked as read') }
    catch (e) { toast.error(apiError(e)) }
  }
  async function remove(id: number, e: React.MouseEvent) {
    e.stopPropagation()
    setItems(prev => prev.filter(x => x.id !== id))
    notificationsApi.remove(id).catch(() => {})
  }

  const unread = items.filter(i => !i.is_read).length

  return (
    <div>
      <PageHeader title="Notifications" subtitle={unread ? `${unread} unread` : 'You’re all caught up'}
        action={unread > 0 ? <Button size="sm" variant="outline" onClick={markAll}><CheckCheck size={15} /> Mark all read</Button> : undefined} />

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : items.length === 0 ? (
        <EmptyState icon={Bell} title="No notifications" description="Activity from your communities will show up here." />
      ) : (
        <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
          {items.map(n => (
            <button key={n.id} onClick={() => open(n)} className={cn('flex w-full items-start gap-3 p-4 text-left hover:bg-divider/50', !n.is_read && 'bg-primary-pale/40')}>
              <div className={cn('mt-1 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-transparent' : 'bg-accent')} />
              <div className="min-w-0 flex-1">
                <p className={cn('text-sm', n.is_read ? 'font-medium text-text' : 'font-semibold text-text')}>{n.title}</p>
                <p className="text-sm text-text-secondary">{n.message}</p>
                <p className="mt-0.5 text-xs text-text-muted">{formatRelative(n.created_at)}</p>
              </div>
              <span onClick={(e) => remove(n.id, e)} className="rounded-lg p-1.5 text-text-muted hover:bg-divider hover:text-error"><Trash2 size={15} /></span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
