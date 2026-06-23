'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Bell, CheckCheck, Trash2, Check, X } from 'lucide-react'
import {
  notificationsApi, communities, contributions, welfare,
  apiError, type Notification,
} from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatRelative, cn } from '@/lib/utils'
import { toast } from 'sonner'

type ActionState = 'idle' | 'loading' | 'approved' | 'rejected' | 'accepted' | 'declined'

/**
 * Governance actions an admin / invitee can take directly from a notification —
 * mirrors the mobile notifications screen so the web is equally capable of
 * running a community day-to-day. `apply` receives the actionable entity id
 * (carried on `join_request_id`) and whether the action is the positive one.
 */
type ActionKind = 'approveReject' | 'acceptDecline'
type ActionCfg = {
  kind: ActionKind
  /** Join requests / invites are only actionable while still PENDING. */
  requiresPending: boolean
  apply: (entityId: number, positive: boolean) => Promise<unknown>
}

const ACTIONS: Record<string, ActionCfg> = {
  community_join:            { kind: 'approveReject', requiresPending: true,  apply: (id, ok) => communities.actionRequest(id, ok ? 'approve' : 'reject') },
  join_request:             { kind: 'approveReject', requiresPending: true,  apply: (id, ok) => communities.actionRequest(id, ok ? 'approve' : 'reject') },
  contribution_join_request:{ kind: 'approveReject', requiresPending: true,  apply: (id, ok) => contributions.actionJoinRequest(id, ok ? 'approve' : 'reject') },
  contribution_invite:      { kind: 'acceptDecline', requiresPending: true,  apply: (id, ok) => contributions.respondInvite(id, ok ? 'accept' : 'decline') },
  disbursement_requested:   { kind: 'approveReject', requiresPending: false, apply: (id, ok) => contributions.voteDisbursement(id, ok ? 'APPROVE' : 'REJECT') },
  welfare_claim:            { kind: 'approveReject', requiresPending: false, apply: (id, ok) => welfare.voteClaim(id, ok ? 'approve' : 'reject') },
  advance_requested:        { kind: 'approveReject', requiresPending: false, apply: (id, ok) => contributions.actionAdvance(id, ok ? 'approve' : 'reject') },
}

const OUTCOME_LABEL: Record<string, string> = {
  approved: 'Approved', rejected: 'Rejected', accepted: 'Accepted', declined: 'Declined',
}

export default function NotificationsPage() {
  const router = useRouter()
  const [items, setItems] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [states, setStates] = useState<Record<number, ActionState>>({})

  async function load() {
    setLoading(true)
    try { setItems(await notificationsApi.list()) }
    catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  function open(n: Notification) {
    if (!n.is_read) { notificationsApi.markRead(n.id).catch(() => {}); setItems(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x)) }
    if (n.conversation_id) router.push(`/conversation/${n.conversation_id}`)
    else if (n.contribution_id) router.push(`/contribution/${n.contribution_id}`)
    else if (n.community_id) router.push(`/community/${n.community_id}`)
  }

  async function runAction(n: Notification, cfg: ActionCfg, positive: boolean) {
    if (n.join_request_id == null) return
    setStates(p => ({ ...p, [n.id]: 'loading' }))
    const success: ActionState = cfg.kind === 'acceptDecline'
      ? (positive ? 'accepted' : 'declined')
      : (positive ? 'approved' : 'rejected')
    try {
      await cfg.apply(n.join_request_id, positive)
      notificationsApi.markRead(n.id).catch(() => {})
      setItems(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x))
      setStates(p => ({ ...p, [n.id]: success }))
    } catch (e) {
      const msg = apiError(e, '')
      if (msg.toLowerCase().includes('already')) {
        // Another admin acted first — refresh to pick up the resolved state.
        await load(); setStates(p => ({ ...p, [n.id]: 'idle' }))
      } else {
        toast.error(msg || 'Could not process. Please try again.')
        setStates(p => ({ ...p, [n.id]: 'idle' }))
      }
    }
  }

  async function markAll() {
    try { await notificationsApi.markAllRead(); setItems(prev => prev.map(x => ({ ...x, is_read: true }))); toast.success('All marked as read') }
    catch (e) { toast.error(apiError(e)) }
  }
  function remove(id: number, e: React.MouseEvent) {
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
          {items.map(n => {
            const cfg = ACTIONS[n.notification_type]
            const state = states[n.id] ?? 'idle'
            const acted = state !== 'idle' && state !== 'loading'
            const actionable = !!cfg && n.join_request_id != null
            // Already resolved server-side (by this admin in a past session, or another admin).
            const resolvedByOther = actionable && cfg.requiresPending && !!n.join_request_status && n.join_request_status !== 'PENDING'

            return (
              <div key={n.id} className={cn('p-4', !n.is_read && 'bg-primary-pale/40')}>
                <div className="flex items-start gap-3">
                  <div className={cn('mt-1 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-transparent' : 'bg-accent')} />
                  <button onClick={() => open(n)} className="min-w-0 flex-1 text-left">
                    <p className={cn('text-sm', n.is_read ? 'font-medium text-text' : 'font-semibold text-text')}>{n.title}</p>
                    <p className="text-sm text-text-secondary">{n.message}</p>
                    <p className="mt-0.5 text-xs text-text-muted">{formatRelative(n.created_at)}</p>
                  </button>
                  <button onClick={(e) => remove(n.id, e)} className="rounded-lg p-1.5 text-text-muted hover:bg-divider hover:text-error"><Trash2 size={15} /></button>
                </div>

                {actionable && (
                  <div className="mt-2.5 pl-5">
                    {acted ? (
                      <Badge tone={state === 'rejected' || state === 'declined' ? 'danger' : 'success'}>{OUTCOME_LABEL[state]}</Badge>
                    ) : resolvedByOther ? (
                      <Badge tone={n.join_request_status === 'APPROVED' ? 'success' : 'danger'}>
                        {n.join_request_status === 'APPROVED' ? 'Approved' : 'Rejected'}
                      </Badge>
                    ) : (
                      <div className="flex gap-2">
                        <Button size="sm" loading={state === 'loading'} onClick={() => runAction(n, cfg, true)}>
                          <Check size={14} /> {cfg.kind === 'acceptDecline' ? 'Accept' : 'Approve'}
                        </Button>
                        <Button size="sm" variant="outline" disabled={state === 'loading'} onClick={() => runAction(n, cfg, false)}>
                          <X size={14} /> {cfg.kind === 'acceptDecline' ? 'Decline' : 'Reject'}
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
