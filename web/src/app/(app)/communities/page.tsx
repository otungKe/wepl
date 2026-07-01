'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  Users, Plus, Search, Lock, ChevronRight,
  TrendingUp, CircleDot, Wallet, Bell,
} from 'lucide-react'
import {
  communities, reports, notificationsApi, apiError,
  type Community, type FinancialSummary, type Notification,
} from '@/lib/api'
import { Button } from '@/components/ui/Button'
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

// ─── main page ────────────────────────────────────────────────────────────────

export default function CommunitiesPage() {
  const [items, setItems]         = useState<Community[]>([])
  const [summary, setSummary]     = useState<FinancialSummary | null>(null)
  const [activity, setActivity]   = useState<Notification[]>([])
  const [loading, setLoading]     = useState(true)
  const [q, setQ]                 = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [joinOpen, setJoinOpen]   = useState(false)

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

  const filtered = items.filter(c => c.name.toLowerCase().includes(q.toLowerCase()))

  // Derived stats
  const growthPct = summary && summary.last_month > 0
    ? Math.round(((summary.this_month - summary.last_month) / summary.last_month) * 100)
    : null

  return (
    <div>
      {/* ── Page title row ──────────────────────────────────────────── */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text">Communities</h1>
          <p className="mt-0.5 text-sm text-text-muted">Your savings groups and chamas</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setJoinOpen(true)}>Join</Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}><Plus size={15} /> New</Button>
        </div>
      </div>

      {/* ── Stats row ───────────────────────────────────────────────── */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          icon={<Users size={18} className="text-primary" />}
          value={loading ? '—' : String(items.length)}
          label="Active communities"
          iconBg="bg-primary-pale"
        />
        <StatTile
          icon={<Wallet size={18} className="text-[#0891b2]" />}
          value={loading || !summary ? '—' : formatMoney(summary.total_contributed)}
          label="Total managed"
          iconBg="bg-[#e0f2fe]"
        />
        <StatTile
          icon={<CircleDot size={18} className="text-accent" />}
          value={loading || !summary ? '—' : String(summary.pending_advances)}
          label="Actions pending"
          iconBg="bg-accent-pale"
          dot={summary ? summary.pending_advances > 0 : false}
        />
        <StatTile
          icon={<TrendingUp size={18} className="text-[#16a34a]" />}
          value={loading || growthPct === null ? '—' : `${growthPct >= 0 ? '+' : ''}${growthPct}%`}
          label="Growth this month"
          iconBg="bg-[#dcfce7]"
        />
      </div>

      {/* ── Two-column body ─────────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">

        {/* ── Left: community list ─────────────────────────────────── */}
        <div>
          {/* Search */}
          <div className="relative mb-4">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search communities, members or transactions"
              className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-text placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/10"
            />
          </div>

          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-[88px] rounded-xl" />)}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No communities yet"
              description="Create a community or join one with an invite to get started."
              action={<Button onClick={() => setCreateOpen(true)}><Plus size={16} /> Create community</Button>}
            />
          ) : (
            <div className="space-y-2">
              {filtered.map(c => <CommunityCard key={c.id} c={c} />)}
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
                    {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />}
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
        </div>
      </div>

      <CreateModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={reload} />
      <JoinModal open={joinOpen} onClose={() => setJoinOpen(false)} onJoined={reload} />
    </div>
  )
}

// ─── community card ───────────────────────────────────────────────────────────

function CommunityCard({ c }: { c: Community }) {
  return (
    <Link
      href={`/community/${c.id}`}
      className="group flex items-center gap-4 rounded-xl border border-border bg-surface px-4 py-3.5 transition-colors hover:border-primary/30 hover:bg-primary-bg/30"
    >
      {/* Photo */}
      <div className="relative shrink-0">
        <Avatar name={c.name} src={c.community_photo} size={56} className="rounded-xl" />
        {c.is_private && (
          <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white bg-text-muted">
            <Lock size={7} className="text-white" />
          </span>
        )}
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate font-semibold text-text">{c.name}</p>
          {c.category && (
            <span className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold text-primary bg-primary-pale">
              {c.category}
            </span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-text-muted">
          {c.member_count} {c.member_count === 1 ? 'member' : 'members'}
          {c.location ? ` · ${c.location}` : ''}
        </p>
        {c.description && (
          <p className="mt-1 truncate text-xs text-text-secondary">{c.description}</p>
        )}
        {(c.has_welfare_fund || c.has_shares_fund) && (
          <div className="mt-1.5 flex gap-1">
            {c.has_welfare_fund && <Badge tone="success">Welfare</Badge>}
            {c.has_shares_fund && <Badge tone="warning">Shares</Badge>}
          </div>
        )}
      </div>

      {/* Right */}
      <div className="flex shrink-0 items-center gap-2">
        <ChevronRight size={16} className="text-text-muted transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  )
}

// ─── stat tile ────────────────────────────────────────────────────────────────

function StatTile({ icon, value, label, iconBg, dot }: {
  icon: React.ReactNode; value: string; label: string; iconBg: string; dot?: boolean
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3.5">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${iconBg}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="text-lg font-bold tabular-nums text-text leading-tight">{value}</p>
          {dot && <span className="h-2 w-2 rounded-full bg-accent" />}
        </div>
        <p className="truncate text-xs text-text-muted">{label}</p>
      </div>
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
