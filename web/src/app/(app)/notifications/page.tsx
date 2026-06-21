'use client'
import { useEffect, useState, useCallback } from 'react'
import { notificationsApi } from '@/lib/api'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Bell, Check } from 'lucide-react'
import { formatRelative } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface Notification {
  id: string; title: string; body: string; is_read: boolean; created_at: string; notification_type?: string
}

export default function NotificationsPage() {
  const [items, setItems]     = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const { data } = await notificationsApi.list()
      setItems(data.results ?? data)
    } catch { toast.error('Failed to load notifications') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  async function markRead(id: string) {
    try {
      await notificationsApi.markRead(id)
      setItems(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
    } catch { }
  }

  const unread = items.filter(n => !n.is_read)

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-text">Notifications</h1>
        {unread.length > 0 && (
          <button
            onClick={async () => {
              await Promise.all(unread.map(n => notificationsApi.markRead(n.id)))
              setItems(prev => prev.map(n => ({ ...n, is_read: true })))
            }}
            className="text-sm text-primary hover:underline flex items-center gap-1"
          >
            <Check size={14} /> Mark all read
          </button>
        )}
      </div>

      {loading ? <PageLoader /> : items.length === 0 ? (
        <EmptyState icon={Bell} title="No notifications" description="You're all caught up." />
      ) : (
        <div className="space-y-1">
          {items.map(n => (
            <div
              key={n.id}
              onClick={() => !n.is_read && markRead(n.id)}
              className={cn(
                'flex items-start gap-3 px-4 py-4 rounded-lg cursor-pointer transition-colors',
                n.is_read ? 'bg-white' : 'bg-primary-pale hover:bg-primary-pale/80'
              )}
            >
              <div className={cn(
                'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0',
                n.is_read ? 'bg-divider' : 'bg-primary'
              )}>
                <Bell size={16} className={n.is_read ? 'text-text-muted' : 'text-white'} />
              </div>
              <div className="flex-1 min-w-0">
                <p className={cn('text-sm font-medium', n.is_read ? 'text-text-secondary' : 'text-text')}>{n.title}</p>
                <p className="text-sm text-text-secondary mt-0.5">{n.body}</p>
                <p className="text-xs text-text-muted mt-1">{formatRelative(n.created_at)}</p>
              </div>
              {!n.is_read && (
                <div className="w-2 h-2 rounded-full bg-primary flex-shrink-0 mt-2" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
