'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { LogOut, KeyRound, MonitorSmartphone, CreditCard, Lock, ChevronRight, type LucideIcon } from 'lucide-react'
import { notificationsApi, apiError } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

type Prefs = { push_enabled: boolean; payments: boolean; contributions: boolean; reminders: boolean; communities: boolean; advances: boolean }

const ROWS: { key: keyof Prefs; label: string; desc: string }[] = [
  { key: 'push_enabled',  label: 'Push notifications', desc: 'Master switch for all alerts' },
  { key: 'payments',      label: 'Payments',           desc: 'M-PESA confirmations & payouts' },
  { key: 'contributions', label: 'Contributions',      desc: 'Pool activity & governance' },
  { key: 'communities',   label: 'Communities & chat', desc: 'Messages and member updates' },
  { key: 'advances',      label: 'Advances & welfare', desc: 'Loan and welfare claim updates' },
  { key: 'reminders',     label: 'Reminders',          desc: 'Scheduled contribution reminders' },
]

const ACCOUNT_LINKS: { href: string; label: string; desc: string; icon: LucideIcon }[] = [
  { href: '/change-pin',      label: 'Change PIN',      desc: 'Update the PIN you use to sign in', icon: KeyRound },
  { href: '/sessions',        label: 'Active devices',  desc: 'See and sign out other devices',   icon: MonitorSmartphone },
  { href: '/payment-methods', label: 'Payment methods', desc: 'Manage where payouts are sent',     icon: CreditCard },
  { href: '/privacy',         label: 'Privacy',         desc: 'Visibility controls and your data', icon: Lock },
]

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={cn('relative h-6 w-11 rounded-full transition-colors', on ? 'bg-primary' : 'bg-border')}>
      <span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform', on ? 'translate-x-[22px]' : 'translate-x-0.5')} />
    </button>
  )
}

export default function SettingsPage() {
  const router = useRouter()
  const logout = useAuthStore(s => s.logout)
  const [prefs, setPrefs] = useState<Prefs | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    notificationsApi.prefs().then(r => setPrefs(r.data)).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [])

  async function toggle(key: keyof Prefs) {
    if (!prefs) return
    const next = { ...prefs, [key]: !prefs[key] }
    setPrefs(next)
    try { await notificationsApi.updatePrefs({ [key]: next[key] }) } catch (e) { toast.error(apiError(e)); setPrefs(prefs) }
  }

  return (
    <div className="max-w-lg">
      <PageHeader title="Settings" subtitle="Notifications & account" />

      <h2 className="mb-3 font-semibold text-text">Notifications</h2>
      {loading ? (
        <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : prefs ? (
        <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
          {ROWS.map(r => (
            <div key={r.key} className="flex items-center justify-between gap-4 p-4">
              <div>
                <p className="font-medium text-text">{r.label}</p>
                <p className="text-sm text-text-muted">{r.desc}</p>
              </div>
              <Toggle on={!!prefs[r.key]} onClick={() => toggle(r.key)} />
            </div>
          ))}
        </div>
      ) : null}

      <h2 className="mb-3 mt-8 font-semibold text-text">Account &amp; security</h2>
      <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
        {ACCOUNT_LINKS.map(({ href, label, desc, icon: Icon }) => (
          <Link key={href} href={href} className="flex items-center gap-3 p-4 transition-colors hover:bg-divider/40">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Icon size={17} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-text">{label}</p>
              <p className="text-sm text-text-muted">{desc}</p>
            </div>
            <ChevronRight size={18} className="shrink-0 text-text-muted" />
          </Link>
        ))}
      </div>

      <h2 className="mb-3 mt-8 font-semibold text-text">Account</h2>
      <Button variant="danger" onClick={() => { logout(); router.replace('/') }}><LogOut size={16} /> Log out</Button>
    </div>
  )
}
