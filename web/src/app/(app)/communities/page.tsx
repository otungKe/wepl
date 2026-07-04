'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import {
  Users, Plus, Search, Lock, ChevronRight,
  TrendingUp, CircleDot, Wallet, Bell, Pin,
} from 'lucide-react'
import {
  communities, reports, notificationsApi, apiError,
  type Community, type FinancialSummary, type Notification,
} from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/Button'
import { GettingStarted } from '@/components/app/GettingStarted'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatMoney, formatRelative } from '@/lib/utils'
import { toast } from 'sonner'

// ─── helpers ──────────────────────────────────────────────────────────────────

const NOTIFICATION_ICON: Record<string, { emoji: string; color: string }> = {
  contribution_payment:   { emoji: '💸', color: '#16a34a' },
  payment_recorded:       { emoji: '🧾', color: '#0891b2' },
  community_join:         { emoji: '👥', color: '#1A5C38' },
  new_message:            { emoji: '💬', color: '#7c3aed' },
  conversation_created:   { emoji: '💬', color: '#7c3aed' },
  contribution_milestone: { emoji: '🎯', color: '#d97706' },
  contribution_joined:    { emoji: '🤝', color: '#1A5C38' },
}

function timeAgo(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// Color-code the community category so the list scans at a glance (matches the
// mobile/dashboard language). Unknown categories fall back to neutral.
const CATEGORY_TONE: Record<string, 'success' | 'info' | 'warning' | 'primary' | 'neutral'> = {
  savings: 'success', chama: 'success',
  investment: 'info', sacco: 'info',
  welfare: 'warning',
  general: 'neutral',
}
const catTone = (cat?: string) => CATEGORY_TONE[(cat ?? '').toLowerCase()] ?? 'neutral'
const catLabel = (cat?: string) => (cat ? cat.charAt(0).toUpperCase() + cat.slice(1) : '')

// Pinned communities are curated per-device in localStorage — there's no backend
// pin flag yet, so this keeps the reference's "Pinned" section honest and useful
// without fabricating data. (Backend sync is a natural follow-up.)
const PIN_KEY = 'wepl.pinnedCommunities'

function usePinnedCommunities() {
  const [ids, setIds] = useState<number[]>([])
  useEffect(() => {
    try { setIds(JSON.parse(localStorage.getItem(PIN_KEY) || '[]')) } catch { /* ignore */ }
  }, [])
  const toggle = useCallback((id: number) => {
    setIds(prev => {
      const next = prev.includes(id) ? prev.filter(x => x !== id) : [id, ...prev]
      try { localStorage.setItem(PIN_KEY, JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }, [])
  return { pinnedIds: ids, toggle }
}

// ─── main page ────────────────────────────────────────────────────────────────

export default function CommunitiesPage() {
  const [items, setItems]         = useState<Community[]>([])
  const [summary, setSummary]     = useState<FinancialSummary | null>(null)
  const [activity, setActivity]   = useState<Notification[]>([])
  const [loading, setLoading]     = useState(true)
  const [q, setQ]                 = useState('')
  const [cat, setCat]             = useState('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [joinOpen, setJoinOpen]   = useState(false)
  const { pinnedIds, toggle: togglePin } = usePinnedCommunities()
  const user = useAuthStore(s => s.user)

  useEffect(() => {
    Promise.all([
      communities.mine().then(setItems),
      reports.financialSummary().then((r: { data: FinancialSummary }) => setSummary(r.data)),
      notificationsApi.list().then(n => setActivity(n.slice(0, 12))),
    ])
      .catch(e => toast.error(apiError(e)))
      .finally(() => setLoading(false))
  }, [])

  function reload() {
    communities.mine().then((c: Community[]) => setItems(c)).catch((e: unknown) => toast.error(apiError(e)))
  }

  // Category chips are derived from the communities the user actually has.
  const categories = Array.from(new Set(items.map(c => (c.category || '').toLowerCase()).filter(Boolean)))
  const query = q.trim().toLowerCase()
  const filtered = items.filter(c => {
    const matchesQ = !query
      || c.name.toLowerCase().includes(query)
      || (c.location || '').toLowerCase().includes(query)
      || (c.category || '').toLowerCase().includes(query)
    const matchesCat = cat === 'all' || (c.category || '').toLowerCase() === cat
    return matchesQ && matchesCat
  })

  // Split into Pinned (curated) and the rest, preserving pin order.
  const pinnedSet = new Set(pinnedIds)
  const pinned = pinnedIds.map(id => filtered.find(c => c.id === id)).filter(Boolean) as Community[]
  const rest = filtered.filter(c => !pinnedSet.has(c.id))

  // Derived stats (all from real data — no fabricated deltas)
  const growthPct = summary && summary.last_month > 0
    ? Math.round(((summary.this_month - summary.last_month) / summary.last_month) * 100)
    : null
  const totalMembers = items.reduce((s, c) => s + (c.member_count || 0), 0)

  return (
    <div>
      {/* ── Page title row ──────────────────────────────────────────── */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-text">Communities</h1>
          <p className="mt-0.5 text-sm text-text-muted">Your groups, contributions and members in one place</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setJoinOpen(true)}>Join</Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}><Plus size={15} /> Create community</Button>
        </div>
      </div>

      {/* ── First-run getting-started (hidden once complete/dismissed) ─ */}
      {!loading && (
        <GettingStarted
          userName={user?.name}
          communitiesCount={items.length}
          kycStatus={summary?.kyc_status}
          txCount={summary?.tx_count ?? 0}
          onCreateCommunity={() => setCreateOpen(true)}
        />
      )}

      {/* ── Stats row ───────────────────────────────────────────────── */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          icon={<Users size={18} className="text-primary" />}
          value={loading ? '—' : String(items.length)}
          label="Active communities"
          iconBg="bg-primary-pale"
          sub={loading ? undefined : `${totalMembers.toLocaleString()} members`}
        />
        <StatTile
          icon={<Wallet size={18} className="text-info" />}
          value={loading || !summary ? '—' : formatMoney(summary.total_contributed)}
          label="Total managed"
          iconBg="bg-info/10"
          sub={growthPct === null ? undefined : `${growthPct >= 0 ? '+' : ''}${growthPct}% this month`}
          subTone={growthPct !== null && growthPct < 0 ? 'down' : 'up'}
        />
        <StatTile
          icon={<CircleDot size={18} className="text-accent" />}
          value={loading || !summary ? '—' : String(summary.pending_advances)}
          label="Actions pending"
          iconBg="bg-accent-pale"
          dot={summary ? summary.pending_advances > 0 : false}
          sub={!summary ? undefined : summary.pending_advances > 0 ? 'Needs your review' : 'All clear'}
          subTone={summary && summary.pending_advances > 0 ? 'warn' : 'muted'}
        />
        <StatTile
          icon={<TrendingUp size={18} className="text-success" />}
          value={loading || growthPct === null ? '—' : `${growthPct >= 0 ? '+' : ''}${growthPct}%`}
          label="Growth this month"
          iconBg="bg-success/10"
          sub={loading ? undefined : 'vs last month'}
        />
      </div>

      {/* ── Two-column body ─────────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">

        {/* ── Left: community list ─────────────────────────────────── */}
        <div>
          {/* Search */}
          <div className="relative mb-3">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search communities, members or location"
              className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-text placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/10"
            />
          </div>

          {/* Category filter */}
          {categories.length > 1 && (
            <div className="mb-4 flex flex-wrap gap-1.5">
              {['all', ...categories].map(key => (
                <button
                  key={key}
                  onClick={() => setCat(key)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    cat === key
                      ? 'bg-primary text-white'
                      : 'bg-divider/60 text-text-secondary hover:bg-divider'
                  }`}
                >
                  {key === 'all' ? 'All' : catLabel(key)}
                </button>
              ))}
            </div>
          )}

          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-[88px] rounded-xl" />)}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No communities yet"
              description="Create a community or join one with an invite to get started."
              action={<Button onClick={() => setCreateOpen(true)}><Plus size={16} /> Create community</Button>}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No matches"
              description="No communities match your search or filter."
            />
          ) : (
            <div className="space-y-6">
              {/* Pinned */}
              {pinned.length > 0 && (
                <div>
                  <div className="mb-2.5 flex items-center gap-2">
                    <Pin size={14} className="text-primary" fill="currentColor" />
                    <p className="text-sm font-semibold text-text">Pinned</p>
                    <span className="text-xs text-text-muted">{pinned.length}</span>
                  </div>
                  <div className="space-y-2.5">
                    {pinned.map(c => (
                      <PinnedCard key={c.id} c={c} pinned onTogglePin={() => togglePin(c.id)} />
                    ))}
                  </div>
                </div>
              )}

              {/* All communities */}
              {rest.length > 0 && (
                <div>
                  {pinned.length > 0 && (
                    <div className="mb-2.5 flex items-center gap-2">
                      <p className="text-sm font-semibold text-text">All communities</p>
                      <span className="text-xs text-text-muted">{rest.length}</span>
                    </div>
                  )}
                  <div className="space-y-2">
                    {rest.map(c => (
                      <CommunityCard
                        key={c.id}
                        c={c}
                        pinned={pinnedSet.has(c.id)}
                        onTogglePin={() => togglePin(c.id)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Right: recent activity ───────────────────────────────── */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <p className="font-semibold text-text">Recent activity</p>
            <Link href="/notifications" className="text-xs font-medium text-primary hover:underline">View all</Link>
          </div>

          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)}
            </div>
          ) : activity.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-10 text-center">
              <Bell size={24} className="text-border" />
              <p className="text-sm text-text-muted">No activity yet</p>
            </div>
          ) : (
            <div className="divide-y divide-divider overflow-hidden rounded-xl border border-border bg-surface">
              {activity.map(n => {
                const meta = NOTIFICATION_ICON[n.notification_type] ?? { emoji: '🔔', color: '#1A5C38' }
                return (
                  <div key={n.id} className="flex items-start gap-3 px-4 py-3">
                    <div
                      className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-base"
                      style={{ backgroundColor: meta.color + '18' }}
                    >
                      {meta.emoji}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className={`truncate text-sm ${!n.is_read ? 'font-semibold text-text' : 'text-text-secondary'}`}>
                        {n.title}
                      </p>
                      <p className="mt-0.5 text-xs text-text-muted">{timeAgo(n.created_at)}</p>
                    </div>
                    {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 animate-pulse rounded-full bg-primary" />}
                  </div>
                )
              })}
            </div>
          )}

          {/* Invite nudge card */}
          <div className="mt-4 overflow-hidden rounded-xl border border-border bg-surface">
            <div className="flex items-start gap-3 p-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-pale text-primary">
                <Users size={18} />
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-text text-sm">Invite members</p>
                <p className="mt-0.5 text-xs text-text-muted">Grow your community by inviting friends and family.</p>
              </div>
            </div>
            <div className="border-t border-divider px-4 pb-4 pt-3">
              <Button size="sm" variant="outline" fullWidth>Invite members</Button>
            </div>
          </div>

          {/* Community health — real signals from the financial summary */}
          {!loading && summary && <CommunityHealth summary={summary} growthPct={growthPct} />}
        </div>
      </div>

      <CreateModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={reload} />
      <JoinModal open={joinOpen} onClose={() => setJoinOpen(false)} onJoined={reload} />
    </div>
  )
}

// ─── community cards ──────────────────────────────────────────────────────────

/** Pin toggle. Sits inside the card <Link>, so it swallows the navigation. */
function PinButton({ pinned, onToggle }: { pinned?: boolean; onToggle?: () => void }) {
  if (!onToggle) return null
  return (
    <button
      type="button"
      title={pinned ? 'Unpin' : 'Pin'}
      aria-label={pinned ? 'Unpin community' : 'Pin community'}
      aria-pressed={pinned}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle() }}
      className={`rounded-lg p-1.5 transition-colors ${
        pinned ? 'text-primary' : 'text-text-muted opacity-0 hover:bg-divider group-hover:opacity-100'
      }`}
    >
      <Pin size={16} fill={pinned ? 'currentColor' : 'none'} />
    </button>
  )
}

// Real per-community highlights from the enriched list payload (total_managed /
// last_activity). Renders nothing when the backend didn't supply them (e.g. a
// community with no funds yet) — no fabricated figures.
function CommunityMetrics({ c }: { c: Community }) {
  const managed = c.total_managed != null && Number(c.total_managed) > 0
    ? formatMoney(c.total_managed) : null
  const active = c.last_activity ? formatRelative(c.last_activity) : null
  if (!managed && !active) return null
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-text-muted">
      {managed && <span className="font-medium text-text-secondary">{managed} managed</span>}
      {managed && active && <span>·</span>}
      {active && <span>Active {active}</span>}
    </div>
  )
}

// Identity-only avatar: compact rounded square, never dominant.
function CommunityAvatar({ c, size }: { c: Community; size: number }) {
  return (
    <div className="relative shrink-0">
      <Avatar name={c.name} src={c.community_photo} size={size} className="rounded-lg" />
      {c.is_private && (
        <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full border-2 border-surface bg-text-muted">
          <Lock size={7} className="text-white" />
        </span>
      )}
    </div>
  )
}

const CARD_MOTION = 'transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-card'

/** Richer card used in the Pinned section. Denser than before; identity-only avatar. */
function PinnedCard({ c, pinned, onTogglePin }: { c: Community; pinned?: boolean; onTogglePin?: () => void }) {
  return (
    <Link href={`/community/${c.id}`} className={`group flex gap-3 rounded-xl border border-border bg-surface p-3.5 ${CARD_MOTION}`}>
      <CommunityAvatar c={c} size={48} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="truncate text-[15px] font-semibold leading-tight text-text">{c.name}</p>
          <PinButton pinned={pinned} onToggle={onTogglePin} />
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-muted">
          {c.category && <Badge tone={catTone(c.category)}>{catLabel(c.category)}</Badge>}
          <span>{c.member_count} {c.member_count === 1 ? 'member' : 'members'}</span>
          {c.location && <span>· {c.location}</span>}
          {!!c.pending_count && <Badge tone="warning">{c.pending_count} pending</Badge>}
        </div>
        <CommunityMetrics c={c} />
        {c.description && <p className="mt-1 truncate text-xs text-text-secondary">{c.description}</p>}
      </div>
      <ChevronRight size={16} className="mt-0.5 shrink-0 self-start text-text-muted transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}

/** Compact card used in the "All communities" list. */
function CommunityCard({ c, pinned, onTogglePin }: { c: Community; pinned?: boolean; onTogglePin?: () => void }) {
  return (
    <Link href={`/community/${c.id}`} className={`group flex items-center gap-3 rounded-xl border border-border bg-surface px-3.5 py-3 ${CARD_MOTION}`}>
      <CommunityAvatar c={c} size={44} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-[15px] font-semibold leading-tight text-text">{c.name}</p>
          {c.category && <Badge tone={catTone(c.category)}>{catLabel(c.category)}</Badge>}
        </div>
        <p className="mt-0.5 truncate text-xs text-text-muted">
          {c.member_count} {c.member_count === 1 ? 'member' : 'members'}
          {c.location ? ` · ${c.location}` : ''}
          {c.has_welfare_fund ? ' · Welfare fund' : ''}
          {c.has_shares_fund ? ' · Shares' : ''}
        </p>
        <CommunityMetrics c={c} />
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {!!c.pending_count && <Badge tone="warning">{c.pending_count}</Badge>}
        <PinButton pinned={pinned} onToggle={onTogglePin} />
        <ChevronRight size={16} className="text-text-muted transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  )
}

// ─── stat tile ────────────────────────────────────────────────────────────────

function StatTile({ icon, value, label, iconBg, dot, sub, subTone = 'muted' }: {
  icon: React.ReactNode; value: string; label: string; iconBg: string; dot?: boolean
  sub?: string; subTone?: 'up' | 'down' | 'warn' | 'muted'
}) {
  const subClass = {
    up: 'text-success', down: 'text-error', warn: 'text-accent', muted: 'text-text-muted',
  }[subTone]
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-3.5 py-3">
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${iconBg}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="text-lg font-bold leading-tight tabular-nums text-text">{value}</p>
          {dot && <span className="h-2 w-2 rounded-full bg-accent" />}
        </div>
        <p className="truncate text-xs text-text-muted">{label}</p>
        {sub && <p className={`mt-0.5 truncate text-[11px] font-medium ${subClass}`}>{sub}</p>}
      </div>
    </div>
  )
}

// ─── community health ─────────────────────────────────────────────────────────

/** Animated ring showing a 0–100 score. Fills from 0 on mount (motion). */
function HealthRing({ score }: { score: number }) {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => setShown(score), 60)
    return () => clearTimeout(t)
  }, [score])
  const r = 24, circ = 2 * Math.PI * r
  const off = circ - (Math.max(0, Math.min(100, shown)) / 100) * circ
  return (
    <div className="relative h-14 w-14 shrink-0">
      <svg width="56" height="56" viewBox="0 0 56 56" className="-rotate-90">
        <circle cx="28" cy="28" r={r} fill="none" strokeWidth="5" className="stroke-divider" />
        <circle
          cx="28" cy="28" r={r} fill="none" strokeWidth="5" strokeLinecap="round"
          className="stroke-primary transition-[stroke-dashoffset] duration-700 ease-out"
          strokeDasharray={circ} strokeDashoffset={off}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold tabular-nums text-text">{score}</span>
    </div>
  )
}

/**
 * Compact community-health snapshot. All figures are derived from the real
 * FinancialSummary — the ring is contribution *consistency* (share of recent
 * months with activity, from monthly_trend). Per-member participation is not in
 * the payload yet and is intentionally omitted until the backend enrichment.
 */
function CommunityHealth({ summary, growthPct }: { summary: FinancialSummary; growthPct: number | null }) {
  const months = summary.monthly_trend || []
  const active = months.filter(m => m.amount > 0).length
  const consistency = months.length ? Math.round((active / months.length) * 100) : 0
  const poolRatio = summary.total_contributions > 0
    ? `${summary.active_contributions}/${summary.total_contributions}`
    : '—'

  return (
    <div className="mt-4 rounded-xl border border-border bg-surface p-4">
      <p className="text-sm font-semibold text-text">Community health</p>
      <div className="mt-3 flex items-center gap-4">
        <HealthRing score={consistency} />
        <div className="min-w-0 flex-1 space-y-1.5 text-xs">
          <HealthRow label="Contribution consistency" value={`${consistency}%`} />
          <HealthRow
            label="Monthly trend"
            value={growthPct === null ? '—' : `${growthPct >= 0 ? '+' : ''}${growthPct}%`}
            tone={growthPct !== null && growthPct < 0 ? 'down' : 'up'}
          />
          <HealthRow label="Pending approvals" value={String(summary.pending_advances)} tone={summary.pending_advances > 0 ? 'warn' : 'muted'} />
          <HealthRow label="Active pools" value={poolRatio} />
        </div>
      </div>
    </div>
  )
}

function HealthRow({ label, value, tone = 'muted' }: { label: string; value: string; tone?: 'up' | 'down' | 'warn' | 'muted' }) {
  const cls = { up: 'text-success', down: 'text-error', warn: 'text-accent', muted: 'text-text' }[tone]
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="truncate text-text-muted">{label}</span>
      <span className={`shrink-0 font-semibold tabular-nums ${cls}`}>{value}</span>
    </div>
  )
}

// ─── modals ───────────────────────────────────────────────────────────────────

function CreateModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPrivate, setIsPrivate] = useState(false)
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!name.trim()) return toast.error('Enter a community name')
    setLoading(true)
    try {
      await communities.create({ name, description, is_private: isPrivate })
      toast.success('Community created')
      onClose(); setName(''); setDescription(''); onCreated()
    } catch (err) { toast.error(apiError(err)) } finally { setLoading(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="New community">
      <div className="flex flex-col gap-4">
        <Input label="Name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Westlands Chama" autoFocus />
        <Input label="Description" value={description} onChange={e => setDescription(e.target.value)} placeholder="What is this group about?" />
        <label className="flex items-center gap-2 text-sm text-text-secondary">
          <input type="checkbox" checked={isPrivate} onChange={e => setIsPrivate(e.target.checked)} className="h-4 w-4 accent-primary" />
          Private (join by invite only)
        </label>
        <Button onClick={submit} loading={loading} fullWidth>Create community</Button>
      </div>
    </Modal>
  )
}

function JoinModal({ open, onClose, onJoined }: { open: boolean; onClose: () => void; onJoined: () => void }) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!code.trim()) return toast.error('Enter an invite code')
    setLoading(true)
    try {
      await communities.requestByInvite(code.trim())
      toast.success('Request sent'); onClose(); setCode(''); onJoined()
    } catch (err) { toast.error(apiError(err, 'Invalid invite code')) } finally { setLoading(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Join with invite code">
      <div className="flex flex-col gap-4">
        <Input label="Invite code" value={code} onChange={e => setCode(e.target.value)} placeholder="e.g. AB12CD" autoFocus />
        <Button onClick={submit} loading={loading} fullWidth>Request to join</Button>
      </div>
    </Modal>
  )
}
