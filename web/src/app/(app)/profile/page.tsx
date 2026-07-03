'use client'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Camera, Save, ShieldCheck, ShieldAlert, Clock, ArrowRight, Lock,
  Wallet, PiggyBank, Receipt, Zap, CreditCard, Users, Coins,
} from 'lucide-react'
import { auth, reports, communities, apiError, type FinancialSummary, type Community } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { useTier, KYC_PROMPT } from '@/hooks/useTier'
import { PageHeader } from '@/components/app/PageHeader'
import { Avatar } from '@/components/ui/Avatar'
import { Input, Textarea } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Spinner'
import { formatMoney } from '@/lib/utils'
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
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      reports.financialSummary().then(r => setSummary(r.data)).catch(() => {}),
      // Public communities for the locked discover section (unverified users).
      communities.discover().then(setDiscover).catch(() => {}),
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

      {/* ── Verify hero (unverified only) ───────────────────────────────── */}
      {!isVerified && (
        <div className="mt-6 rounded-2xl border border-border bg-surface p-6 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-primary-pale text-primary">
            <ShieldCheck size={26} />
          </div>
          <p className="mt-3 text-lg font-bold text-text">{prompt.title}</p>
          <p className="mx-auto mt-1.5 max-w-md text-sm text-text-secondary">{prompt.body}</p>
          <Link href={prompt.href}>
            <Button size="lg" className="mt-5"><ArrowRight size={18} /> {prompt.cta}</Button>
          </Link>
          {kycStatus === 'not_submitted' && (
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {UNLOCKS.map(({ icon: Icon, label }) => (
                <span key={label} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-primary-bg/50 px-3 py-1 text-xs font-medium text-text-muted">
                  <Lock size={11} /> {label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Financial Snapshot ──────────────────────────────────────────── */}
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

      {/* ── Discover communities (unverified only) ──────────────────────── */}
      {!isVerified && discover.length > 0 && (
        <section className="mt-6">
          <div className="mb-1 flex items-center justify-between">
            <p className="font-semibold text-text">Discover communities</p>
            <Link href="/kyc" className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-text-muted hover:bg-divider">
              <Lock size={11} /> Verify to join
            </Link>
          </div>
          <p className="mb-3 text-sm text-text-muted">See what savings groups are active. Verify your identity to join.</p>
          <div className="divide-y divide-divider overflow-hidden rounded-xl border border-border bg-surface">
            {discover.slice(0, 5).map(c => (
              <div key={c.id} className="flex items-center gap-3 px-4 py-3">
                <Avatar name={c.name} src={c.community_photo} size={40} className="rounded-lg" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-text">{c.name}</p>
                  <p className="truncate text-xs text-text-muted">{c.member_count} members · {c.category || 'general'}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => router.push('/kyc')}>
                  <Lock size={13} /> Join
                </Button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Edit profile ────────────────────────────────────────────────── */}
      <section className="mt-8">
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

function SnapshotTile({ icon: Icon, label, value }: { icon: typeof Wallet; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-pale text-primary"><Icon size={18} /></div>
      <p className="mt-2 text-xl font-bold tabular-nums text-text">{value}</p>
      <p className="text-xs text-text-muted">{label}</p>
    </div>
  )
}
