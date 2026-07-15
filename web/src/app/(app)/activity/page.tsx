'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity as ActivityIcon, CreditCard, Smartphone, Wallet, AlarmClock,
  UserPlus, LogOut, TrendingUp, TrendingDown, Heart, Shield, CheckCircle2,
  MessageCircle, Users, Circle, type LucideIcon,
} from 'lucide-react'
import { activityApi, apiError, type Activity } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState, ErrorState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 30

// ── Activity-type presentation ────────────────────────────────────────────────
// Mirrors the mobile activity screen: each type maps to an icon, a token-backed
// tone (so both themes adapt), and a short label. Matched by exact key first,
// then by prefix, so `contribution_due` etc. resolve without an entry each.
type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'primary'

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-divider text-text-secondary',
  success: 'bg-primary-pale text-primary',
  warning: 'bg-accent-pale text-accent',
  danger:  'bg-error/10 text-error',
  info:    'bg-info/10 text-info',
  primary: 'bg-primary/10 text-primary',
}

type Meta = { icon: LucideIcon; tone: Tone; label: string }

const META: Record<string, Meta> = {
  payment:           { icon: CreditCard,    tone: 'info',    label: 'Payment' },
  mpesa:             { icon: Smartphone,    tone: 'info',    label: 'M-Pesa' },
  contribution:      { icon: Wallet,        tone: 'success', label: 'Contribution' },
  contribution_due:  { icon: AlarmClock,    tone: 'warning', label: 'Due' },
  join:              { icon: UserPlus,      tone: 'info',    label: 'Community' },
  join_request:      { icon: UserPlus,      tone: 'info',    label: 'Join request' },
  leave:             { icon: LogOut,        tone: 'neutral', label: 'Left' },
  advance:           { icon: TrendingUp,    tone: 'info',    label: 'Advance' },
  repayment:         { icon: TrendingDown,  tone: 'success', label: 'Repayment' },
  welfare:           { icon: Heart,         tone: 'danger',  label: 'Welfare' },
  welfare_payout:    { icon: Heart,         tone: 'danger',  label: 'Welfare' },
  admin:             { icon: Shield,        tone: 'primary', label: 'Admin' },
  admin_action:      { icon: Shield,        tone: 'primary', label: 'Admin' },
  kyc:               { icon: CheckCircle2,  tone: 'success', label: 'KYC' },
  message:           { icon: MessageCircle, tone: 'info',    label: 'Message' },
  community_created: { icon: Users,         tone: 'primary', label: 'Community' },
}

const DEFAULT_META: Meta = { icon: Circle, tone: 'neutral', label: 'Activity' }

function metaFor(type: string): Meta {
  if (META[type]) return META[type]
  for (const key of Object.keys(META)) {
    if (type.startsWith(key) || key.startsWith(type)) return META[key]
  }
  return DEFAULT_META
}

// ── Filters (mirror the mobile chip row) ──────────────────────────────────────
const FILTERS: { key: string | null; label: string }[] = [
  { key: null,           label: 'All' },
  { key: 'payment',      label: 'Payments' },
  { key: 'contribution', label: 'Contributions' },
  { key: 'join',         label: 'Community' },
  { key: 'advance',      label: 'Advances' },
  { key: 'welfare',      label: 'Welfare' },
  { key: 'admin',        label: 'Admin' },
]

// ── Date grouping ─────────────────────────────────────────────────────────────
function dayLabel(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const today = startOf(new Date())
  const that = startOf(d)
  if (that === today) return 'Today'
  if (that === today - 86_400_000) return 'Yesterday'
  return d.toLocaleDateString('en-KE', { weekday: 'long', month: 'short', day: 'numeric' })
}

function timeLabel(iso: string): string {
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString('en-KE', { hour: 'numeric', minute: '2-digit' })
}

type Row = { kind: 'header'; date: string } | { kind: 'item'; data: Activity }

function toRows(list: Activity[]): Row[] {
  const rows: Row[] = []
  let last = ''
  for (const a of list) {
    const date = dayLabel(a.created_at)
    if (date !== last) { rows.push({ kind: 'header', date }); last = date }
    rows.push({ kind: 'item', data: a })
  }
  return rows
}

// ── Row ───────────────────────────────────────────────────────────────────────
function ActivityRow({ item }: { item: Activity }) {
  const meta = metaFor(item.activity_type)
  const Icon = meta.icon
  return (
    <div className="flex items-start gap-3 px-1 py-3">
      <div className={cn('mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', TONE_CLASSES[meta.tone])}>
        <Icon size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-text">{item.message}</p>
        <div className="mt-1 flex items-center gap-2">
          <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', TONE_CLASSES[meta.tone])}>
            {meta.label}
          </span>
          <span className="text-xs text-text-muted">{timeLabel(item.created_at)}</span>
        </div>
      </div>
    </div>
  )
}

export default function ActivityPage() {
  const [items, setItems] = useState<Activity[]>([])
  const [filter, setFilter] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Guards against a stale in-flight request applying after the filter changed.
  const reqId = useRef(0)

  const load = useCallback(async (type: string | null, offset: number) => {
    const id = ++reqId.current
    offset === 0 ? setLoading(true) : setLoadingMore(true)
    setError(null)
    try {
      const page = await activityApi.feed({ limit: PAGE_SIZE, offset, ...(type ? { type } : {}) })
      if (id !== reqId.current) return // superseded by a newer request
      setItems(prev => (offset === 0 ? page.results : [...prev, ...page.results]))
      setHasMore(page.has_more)
    } catch (e) {
      if (id === reqId.current) setError(apiError(e))
    } finally {
      if (id === reqId.current) { setLoading(false); setLoadingMore(false) }
    }
  }, [])

  useEffect(() => { load(filter, 0) }, [filter, load])

  const rows = toRows(items)

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Activity" subtitle="Your financial and community activity" />

      {/* Filter chips */}
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map(f => {
          const active = filter === f.key
          return (
            <button
              key={f.label}
              onClick={() => setFilter(f.key)}
              className={cn(
                'rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
                active
                  ? 'bg-primary text-white'
                  : 'bg-divider/60 text-text-secondary hover:bg-divider hover:text-text',
              )}
            >
              {f.label}
            </button>
          )
        })}
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex items-start gap-3 px-1 py-3">
              <Skeleton className="h-9 w-9 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState description={error} onRetry={() => load(filter, 0)} retrying={loading} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ActivityIcon}
          title={filter ? 'No matching activity' : 'No activity yet'}
          description={
            filter
              ? 'Try a different filter or clear the selection.'
              : 'Your activity will appear here as you contribute, receive payouts, and interact with communities.'
          }
        />
      ) : (
        <>
          <div className="divide-y divide-divider">
            {rows.map((row, i) =>
              row.kind === 'header' ? (
                <div key={`h-${row.date}-${i}`} className="flex items-center gap-3 pb-1 pt-4 first:pt-0">
                  <span className="text-xs font-bold uppercase tracking-wide text-text-muted">{row.date}</span>
                  <span className="h-px flex-1 bg-divider" />
                </div>
              ) : (
                <ActivityRow key={row.data.id} item={row.data} />
              ),
            )}
          </div>

          {hasMore && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" loading={loadingMore} onClick={() => load(filter, items.length)}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
