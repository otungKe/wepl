'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Users, Compass, Bell, User as UserIcon, Settings, LogOut, Building2, ShieldCheck, BarChart3, Clock, Receipt, Coins, Activity } from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { useTier } from '@/hooks/useTier'
import { notificationsApi } from '@/lib/api'
import { Avatar } from '@/components/ui/Avatar'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { cn } from '@/lib/utils'

// `tier0: true` marks the items an unverified (Tier 0) user may see. Everything
// else is verified-only — mirrors the mobile tab bar, where an unverified user
// sees only Profile (+ the paths that lead to verification). See ADR-0022.
const NAV = [
  { href: '/communities',  label: 'Communities',  icon: Users },
  { href: '/contributions', label: 'Contributions', icon: Coins },
  { href: '/discover',     label: 'Discover',     icon: Compass, tier0: true },
  { href: '/requests',     label: 'My requests',  icon: Clock },
  { href: '/transactions', label: 'Transactions', icon: Receipt },
  { href: '/activity',     label: 'Activity',     icon: Activity },
  { href: '/reports',      label: 'Reports',      icon: BarChart3 },
  { href: '/notifications',label: 'Notifications',icon: Bell, key: 'notifications' },
  { href: '/kyc',          label: 'Verification', icon: ShieldCheck, tier0: true },
  { href: '/profile',      label: 'Profile',      icon: UserIcon, tier0: true },
  { href: '/settings',     label: 'Settings',     icon: Settings, tier0: true },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const user = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)
  const { isVerified } = useTier()
  const [unread, setUnread] = useState(0)

  // Tier 0 (unverified) users get a minimal nav: verify + profile + settings.
  const nav = isVerified ? NAV : NAV.filter(i => i.tier0)

  useEffect(() => {
    let alive = true
    notificationsApi.unreadCount().then(n => alive && setUnread(n)).catch(() => {})
    const t = setInterval(() => notificationsApi.unreadCount().then(n => alive && setUnread(n)).catch(() => {}), 30000)
    return () => { alive = false; clearInterval(t) }
  }, [pathname])

  function handleLogout() {
    logout()
    router.replace('/')
  }

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary">
          <Building2 size={20} className="text-white" />
        </div>
        <span className="text-xl font-bold text-text">WEPL</span>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {nav.map(({ href, label, icon: Icon, key }) => {
          const active = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150',
                active
                  ? 'bg-primary-pale font-semibold text-primary'
                  : 'font-medium text-text-secondary hover:bg-divider/60 hover:text-text',
              )}
            >
              <Icon size={18} className={active ? 'text-primary' : 'text-text-muted'} />
              <span className="flex-1">{label}</span>
              {key === 'notifications' && unread > 0 && (
                <span className="rounded-full bg-accent px-1.5 text-xs font-semibold text-white">{unread > 99 ? '99+' : unread}</span>
              )}
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-divider p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <Avatar name={user?.name || user?.phone_number || '?'} src={user?.profile_photo} size={36} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-text">{user?.name || 'WEPL user'}</p>
            <p className="truncate text-xs text-text-muted">{user?.phone_number}</p>
          </div>
          <ThemeToggle />
          <button onClick={handleLogout} title="Log out" className="rounded-lg p-1.5 text-text-muted hover:bg-divider hover:text-error">
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </aside>
  )
}
