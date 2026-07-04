'use client'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Camera, Save, ShieldCheck, ShieldAlert, Clock, ArrowRight, Lock, ChevronRight,
  Wallet, PiggyBank, Receipt, Zap, CreditCard, Users, Coins, Compass, Megaphone,
  Bell, AlarmClock, Settings, LifeBuoy, FileText, Check,
} from 'lucide-react'
import {
  auth, reports, communities, contributions, notificationsApi, reminders as remindersApi,
  apiError, type FinancialSummary, type Community, type Contribution, type Notification, type Reminder,
} from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { useTier, KYC_PROMPT } from '@/hooks/useTier'
import { PageHeader } from '@/components/app/PageHeader'
import { Avatar } from '@/components/ui/Avatar'
import { Input, Textarea } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Spinner'
import { formatMoney, formatRelative } from '@/lib/utils'
import { toast } from 'sonner'

const UNLOCKS = [
  { icon: CreditCard, label: 'Payments' },
  { icon: Coins, label: 'Contributions' },
  { icon: Zap, label: 'Advances' },
  { icon: Users, label: 'Communities' },
]

export default function ProfilePage() {
  const router = useRouter()
  const user = useAuthStore(s => s.user)
  const setUser = useAuthStore(s => s.setUser)
  const { kycStatus, isVerified } = useTier()
  const prompt = KYC_PROMPT[kycStatus]

  const [name, setName] = useState(user?.name ?? '')
  const [bio, setBio] = useState(user?.bio ?? '')
  const [saving, setSaving] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const [summary, setSummary] = useState<FinancialSummary | null>(null)
  const [discover, setDiscover] = useState<Community[]>([])
  const [campaigns, setCampaigns] = useState<Contribution[]>([])
  const [notifs, setNotifs] = useState<Notification[]>([])
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      reports.financialSummary().then(r => setSummary(r.data)).catch(() => {}),
      communities.discover().then(c => setDiscover(c.slice(0, 3))).catch(() => {}),
      contributions.open().then(c => setCampaigns(c.filter(x => x.is_campaign).slice(0, 2))).catch(() => {}),
      notificationsApi.list().then(n => setNotifs(n.slice(0, 3))).catch(() => {}),
      remindersApi.upcoming(3).then(setReminders).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [])

  async function save() {
    setSaving(true)
    try { const r = await auth.updateProfile({ name, bio }); setUser(r.data); toast.success('Profile updated') }
    catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }
  async function uploadPhoto(file: File) {
    const form = new FormData(); form.append('profile_photo', file)
    try { const r = await auth.updateProfile(form); setUser(r.data); toast.success('Photo updated') }
    catch (e) { toast.error(apiError(e)) }
  }

  const memberSince = summary?.member_since
    ? new Date(summary.member_since).toLocaleDateString('en-KE', { month: 'long', year: 'numeric' })
    : null

  const badgeTone = isVerified ? 'success' : kycStatus === 'pending' ? 'warning' : 'neutral'
  const BadgeIcon = isVerified ? ShieldCheck : kycStatus === 'pending' ? Clock : ShieldAlert
  const hasDiscover = discover.length > 0 || campaigns.length > 0

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Profile" />

      {/* ── Identity header ─────────────────────────────────────────────── */}
      <div className="flex flex-col items-center text-center">
        <div className="relative">
          <Avatar name={user?.name || user?.phone_number || '?'} src={user?.profile_photo} size={88} />
          <button onClick={() => fileRef.current?.click()} className="absolute bottom-0 right-0 flex h-8 w-8 items-center justify-center rounded-full bg-primary text-white shadow-sm ring-2 ring-primary-bg">
            <Camera size={15} />
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => e.target.files?.[0] && uploadPhoto(e.target.files[0])} />
        </div>
        <p className="mt-3 text-xl font-bold text-text">{user?.name || 'WEPL user'}</p>
        <p className="text-sm text-text-muted">{user?.phone_number}</p>
        <Link href={prompt.href} className="mt-2">
          <Badge tone={badgeTone}><BadgeIcon size={12} /> {prompt.badge}</Badge>
        </Link>
        {memberSince && <p className="mt-2 text-xs text-text-muted">Member since {memberSince}</p>}
      </div>

      {/* ── Verification centre ─────────────────────────────────────────── */}
      <VerificationCentre kycStatus={kycStatus} isVerified={isVerified} prompt={prompt} />

      {/* ── Discover communities & campaigns ────────────────────────────── */}
      {loading ? (
        <div className="mt-6 grid gap-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>
      ) : hasDiscover && (
        <section className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Compass size={17} className="text-primary" />
              <p className="font-semibold text-text">Discover communities &amp; campaigns</p>
            </div>
            <Link href="/discover" className="inline-flex items-center gap-0.5 text-xs font-medium text-primary hover:underline">
              See all <ChevronRight size={13} />
            </Link>
          </div>
          {!isVerified && <p className="-mt-1 mb-3 text-sm text-text-muted">See what&apos;s active in your area. Verify your identity to join.</p>}

          <div className="divide-y divide-divider overflow-hidden rounded-xl border border-border bg-surface">
            {discover.map(c => (
              <div key={`c${c.id}`} className="flex items-center gap-3 px-4 py-3">
                <Avatar name={c.name} src={c.community_photo} size={40} className="rounded-lg" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-text">{c.name}</p>
                  <p className="truncate text-xs text-text-muted">{c.member_count} members · {c.category || 'general'}</p>
                </div>
                {isVerified
                  ? <Button size="sm" variant="outline" onClick={() => router.push('/discover')}>View</Button>
                  : <Button size="sm" variant="outline" onClick={() => router.push('/kyc')}><Lock size={13} /> Join</Button>}
              </div>
            ))}
            {campaigns.map(c => (
              <div key={`p${c.id}`} className="flex items-center gap-3 px-4 py-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-pale text-accent"><Megaphone size={18} /></div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-text">{c.title}</p>
                  <p className="truncate text-xs text-text-muted">
                    Campaign · {formatMoney(c.current_amount)}{Number(c.target_amount) > 0 ? ` of ${formatMoney(c.target_amount ?? '0')}` : ''}
                  </p>
                </div>
                {isVerified
                  ? <Button size="sm" variant="outline" onClick={() => router.push(`/contribution/${c.id}`)}>View</Button>
                  : <Button size="sm" variant="outline" onClick={() => router.push('/kyc')}><Lock size={13} /> Support</Button>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Notifications & reminders ───────────────────────────────────── */}
      <section className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-semibold text-text">Notifications &amp; reminders</p>
          {isVerified && <Link href="/notifications" className="text-xs font-medium text-primary hover:underline">View all</Link>}
        </div>
        {loading ? (
          <div className="grid gap-2">{Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
        ) : (notifs.length === 0 && reminders.length === 0) ? (
          <div className="flex items-center gap-3 rounded-xl border border-dashed border-border bg-primary-bg/40 px-4 py-4 text-sm text-text-muted">
            <Bell size={17} /> You&apos;re all caught up — no notifications or reminders yet.
          </div>
        ) : (
          <div className="divide-y divide-divider overflow-hidden rounded-xl border border-border bg-surface">
            {notifs.map(n => (
              <div key={`n${n.id}`} className="flex items-start gap-3 px-4 py-3">
                <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${n.is_read ? 'bg-divider text-text-muted' : 'bg-primary-pale text-primary'}`}><Bell size={15} /></div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-text">{n.title}</p>
                  <p className="truncate text-xs text-text-muted">{n.message}</p>
                </div>
                <span className="shrink-0 text-xs text-text-muted">{formatRelative(n.created_at)}</span>
              </div>
            ))}
            {reminders.map(r => (
              <div key={`r${r.id}`} className="flex items-center gap-3 px-4 py-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-pale text-accent"><AlarmClock size={15} /></div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-text">{r.title}</p>
                  <p className="truncate text-xs text-text-muted">
                    {r.recurrence !== 'none' ? `${r.recurrence.charAt(0).toUpperCase()}${r.recurrence.slice(1)} · ` : ''}
                    {new Date(r.next_fire_at).toLocaleDateString('en-KE', { weekday: 'short', month: 'short', day: 'numeric' })}
                  </p>
                </div>
                {r.is_overdue && <Badge tone="warning">Due</Badge>}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Financial snapshot ──────────────────────────────────────────── */}
      <section className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-semibold text-text">Financial snapshot</p>
          {isVerified && <Link href="/reports" className="text-xs font-medium text-primary hover:underline">View reports</Link>}
        </div>
        {loading ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
          </div>
        ) : isVerified && summary ? (
          <div className="grid grid-cols-2 gap-3">
            <SnapshotTile icon={PiggyBank} label="Total saved" value={formatMoney(summary.total_contributed)} />
            <SnapshotTile icon={Wallet} label="Active pools" value={String(summary.active_contributions)} />
            <SnapshotTile icon={Receipt} label="Transactions" value={String(summary.tx_count)} />
            <SnapshotTile icon={Zap} label="Advances" value={String(summary.pending_advances)} />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              {['Total saved', 'Active pools', 'Transactions', 'Advances'].map(label => (
                <div key={label} className="flex flex-col items-center gap-1 rounded-xl border border-dashed border-border bg-primary-bg/40 px-4 py-5 text-center">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-divider text-text-muted"><Lock size={16} /></div>
                  <p className="mt-1 text-lg font-bold text-text-muted">—</p>
                  <p className="text-xs text-text-muted">{label}</p>
                </div>
              ))}
            </div>
            <p className="mt-2 text-center text-xs text-text-muted">Complete verification to view your financial summary.</p>
          </>
        )}
      </section>

      {/* ── Account ─────────────────────────────────────────────────────── */}
      <section className="mt-6">
        <p className="mb-3 font-semibold text-text">Account</p>
        <div className="divide-y divide-divider overflow-hidden rounded-xl border border-border bg-surface">
          <MenuRow icon={Settings} label="Settings & preferences" onClick={() => router.push('/settings')} />
          {isVerified && <MenuRow icon={FileText} label="Reports & statements" onClick={() => router.push('/reports')} />}
          <MenuRow icon={LifeBuoy} label="Help & support" href="mailto:support@wepl.app" />
        </div>
      </section>

      {/* ── Edit profile ────────────────────────────────────────────────── */}
      <section className="mt-6 mb-2">
        <p className="mb-3 font-semibold text-text">Edit profile</p>
        <div className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-4">
          <Input label="Name" value={name} onChange={e => setName(e.target.value)} />
          <Textarea label="Bio" value={bio} onChange={e => setBio(e.target.value)} placeholder="Tell others about yourself" />
          <Button onClick={save} loading={saving}><Save size={16} /> Save changes</Button>
        </div>
      </section>
    </div>
  )
}

/**
 * Verification centre — the home for identity/KYC verification and, later,
 * any document verification WEPL may require. Modelled as a checklist so new
 * verification items slot in without a redesign.
 */
function VerificationCentre({
  kycStatus, isVerified, prompt,
}: { kycStatus: string; isVerified: boolean; prompt: typeof KYC_PROMPT[keyof typeof KYC_PROMPT] }) {
  // Verification requirements. Identity (KYC) is live today; future document
  // checks can be appended here with status 'upcoming'.
  const identityStatus = isVerified ? 'done' : kycStatus === 'pending' ? 'pending' : 'action'
  const items: { label: string; hint: string; status: 'done' | 'pending' | 'action' | 'upcoming' }[] = [
    { label: 'Identity (KYC)', hint: 'National ID & selfie', status: identityStatus },
    { label: 'Supporting documents', hint: 'Requested only if needed later', status: 'upcoming' },
  ]

  return (
    <section className="mt-6">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck size={17} className="text-primary" />
        <p className="font-semibold text-text">Verification centre</p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-border bg-surface">
        {/* Header / CTA */}
        <div className="flex flex-col gap-3 border-b border-divider p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${isVerified ? 'bg-success/10 text-success' : 'bg-primary-pale text-primary'}`}>
              <ShieldCheck size={22} />
            </div>
            <div>
              <p className="font-semibold text-text">{isVerified ? 'Identity verified' : prompt.title}</p>
              <p className="mt-0.5 text-sm text-text-secondary">
                {isVerified ? 'You have full access to payments, contributions and communities.' : prompt.body}
              </p>
            </div>
          </div>
          {!isVerified && (
            <Link href={prompt.href} className="shrink-0">
              <Button><ArrowRight size={16} /> {prompt.cta}</Button>
            </Link>
          )}
        </div>

        {/* Checklist */}
        <div className="divide-y divide-divider">
          {items.map(it => (
            <div key={it.label} className="flex items-center gap-3 px-5 py-3">
              <VerifyStatusIcon status={it.status} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-text">{it.label}</p>
                <p className="text-xs text-text-muted">{it.hint}</p>
              </div>
              <span className="shrink-0 text-xs font-medium text-text-muted">
                {it.status === 'done' ? 'Verified' : it.status === 'pending' ? 'Under review' : it.status === 'action' ? 'Required' : 'If needed'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* What verification unlocks (only before the user has verified) */}
      {kycStatus === 'not_submitted' && (
        <div className="mt-3 flex flex-wrap gap-2">
          {UNLOCKS.map(({ icon: Icon, label }) => (
            <span key={label} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-primary-bg/50 px-3 py-1 text-xs font-medium text-text-muted">
              <Lock size={11} /> {label}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

function VerifyStatusIcon({ status }: { status: 'done' | 'pending' | 'action' | 'upcoming' }) {
  if (status === 'done') return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success text-white"><Check size={13} /></span>
  if (status === 'pending') return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-warning/15 text-warning"><Clock size={13} /></span>
  if (status === 'action') return <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary-pale text-primary"><ShieldAlert size={13} /></span>
  return <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border text-text-muted"><Lock size={11} /></span>
}

function MenuRow({ icon: Icon, label, onClick, href }: { icon: typeof Settings; label: string; onClick?: () => void; href?: string }) {
  const inner = (
    <>
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-bg text-text-secondary"><Icon size={17} /></div>
      <span className="flex-1 text-sm font-medium text-text">{label}</span>
      <ChevronRight size={16} className="text-text-muted" />
    </>
  )
  const cls = 'flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-divider/50'
  return href
    ? <a href={href} className={cls}>{inner}</a>
    : <button onClick={onClick} className={`w-full ${cls}`}>{inner}</button>
}

function SnapshotTile({ icon: Icon, label, value }: { icon: typeof Wallet; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-pale text-primary"><Icon size={18} /></div>
      <p className="mt-2 text-xl font-bold tabular-nums text-text">{value}</p>
      <p className="text-xs text-text-muted">{label}</p>
    </div>
  )
}
