'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  Users, Compass, Bell, Settings, LogOut, User,
  ChevronDown, Building2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Avatar } from '@/components/ui/Avatar'
import { useAuthStore } from '@/store/auth'
import { useState } from 'react'

const NAV_ITEMS = [
  { href: '/communities', icon: Users,    label: 'Communities' },
  { href: '/discover',    icon: Compass,  label: 'Discover' },
  { href: '/notifications',icon: Bell,   label: 'Notifications' },
]

const BOTTOM_ITEMS = [
  { href: '/profile',  icon: User,     label: 'Profile' },
  { href: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar() {
  const pathname  = usePathname()
  const router    = useRouter()
  const { user, logout } = useAuthStore()
  const [expanded, setExpanded] = useState(true)

  const handleLogout = () => { logout(); router.push('/') }

  return (
    <aside
      className={cn(
        'flex flex-col bg-white border-r border-border h-screen sticky top-0 flex-shrink-0 transition-all duration-200',
        expanded ? 'w-60' : 'w-16'
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-divider">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
          <Building2 size={18} className="text-white" />
        </div>
        {expanded && (
          <span className="font-bold text-lg text-text tracking-tight">WEPL</span>
        )}
        <button
          onClick={() => setExpanded(e => !e)}
          className={cn('ml-auto p-1 rounded hover:bg-divider text-text-muted transition-transform', !expanded && 'rotate-180')}
        >
          <ChevronDown size={16} className="-rotate-90" />
        </button>
      </div>

      {/* Main nav */}
      <nav className="flex-1 py-3 overflow-y-auto no-scrollbar">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              title={!expanded ? label : undefined}
              className={cn(
                'flex items-center gap-3 mx-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                active
                  ? 'bg-primary-pale text-primary'
                  : 'text-text-secondary hover:bg-primary-bg hover:text-text'
              )}
            >
              <Icon size={18} className="flex-shrink-0" />
              {expanded && <span>{label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* Bottom: profile + settings */}
      <div className="py-3 border-t border-divider">
        {BOTTOM_ITEMS.map(({ href, icon: Icon, label }) => (
          <Link
            key={href}
            href={href}
            title={!expanded ? label : undefined}
            className={cn(
              'flex items-center gap-3 mx-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
              pathname === href
                ? 'bg-primary-pale text-primary'
                : 'text-text-secondary hover:bg-primary-bg hover:text-text'
            )}
          >
            <Icon size={18} className="flex-shrink-0" />
            {expanded && <span>{label}</span>}
          </Link>
        ))}

        {/* User info */}
        {user && (
          <div className={cn('flex items-center gap-3 mx-2 mt-2 px-3 py-2', !expanded && 'justify-center')}>
            <Avatar name={user.name} src={user.profile_photo} size="sm" />
            {expanded && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-text truncate">{user.name}</p>
                <p className="text-xs text-text-muted truncate">{user.phone_number}</p>
              </div>
            )}
            {expanded && (
              <button
                onClick={handleLogout}
                className="p-1 rounded hover:bg-divider text-text-muted"
                title="Sign out"
              >
                <LogOut size={15} />
              </button>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
