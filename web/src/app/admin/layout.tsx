'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Moon, Sun, LogOut, ShieldAlert, Loader2 } from 'lucide-react'
import { getAccessToken, isTokenValid, clearTokens } from '@/lib/auth'
import { useOpsStore, useCan } from '@/store/ops'
import { NAV, roleLabel } from '@/lib/opsNav'
import { SearchBox } from '@/components/ops/SearchBox'
import type { OpsMe } from '@/lib/ops'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { me, status, load } = useOpsStore()
  const can = useCan()
  const [dark, setDark] = useState(true)

  // Console theme is remembered locally and scoped to the shell wrapper.
  useEffect(() => {
    const saved = typeof window !== 'undefined' ? localStorage.getItem('ops-theme') : null
    if (saved) setDark(saved === 'dark')
  }, [])
  const toggleTheme = () => {
    setDark((d) => { localStorage.setItem('ops-theme', !d ? 'dark' : 'light'); return !d })
  }

  useEffect(() => {
    const token = getAccessToken()
    if (!token || !isTokenValid(token)) { router.replace('/login'); return }
    if (status === 'idle') load()
  }, [router, status, load])

  const shell = 'min-h-screen ' + (dark ? 'dark' : '')

  if (status === 'idle' || status === 'loading') {
    return (
      <div className={shell}>
        <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      </div>
    )
  }

  if (status === 'denied') {
    return (
      <div className={shell}>
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50 px-6 text-center dark:bg-slate-950">
          <ShieldAlert className="h-10 w-10 text-amber-500" />
          <h1 className="text-lg font-semibold text-slate-800 dark:text-slate-100">No Back Office access</h1>
          <p className="max-w-sm text-sm text-slate-500">
            Your account isn&apos;t assigned an operations role. Ask a Platform Admin to grant you one.
          </p>
          <button onClick={() => { clearTokens(); router.replace('/login') }}
            className="mt-2 rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white dark:bg-slate-200 dark:text-slate-900">
            Sign out
          </button>
        </div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className={shell}>
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50 dark:bg-slate-950">
          <p className="text-sm text-slate-500">Couldn&apos;t load the console.</p>
          <button onClick={() => load()} className="rounded-md border border-slate-300 px-4 py-2 text-sm dark:border-slate-700 dark:text-slate-200">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className={shell}>
      <div className="flex min-h-screen bg-slate-50 text-slate-800 dark:bg-slate-950 dark:text-slate-100">
        {/* Sidebar */}
        <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white md:flex dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-2.5 border-b border-slate-100 px-4 py-4 dark:border-slate-800">
            <div className="grid h-8 w-8 place-items-center rounded-md bg-blue-600 font-mono text-sm font-bold text-white">W</div>
            <div>
              <div className="text-sm font-semibold leading-tight">WEPL Back Office</div>
              <div className="text-[10px] uppercase tracking-widest text-slate-400">Operations Console</div>
            </div>
          </div>
          <nav className="flex-1 overflow-y-auto px-2 py-3">
            {NAV.map((grp) => {
              const items = grp.items.filter((i) => can(i.cap))
              if (!items.length) return null
              return (
                <div key={grp.group} className="mb-4">
                  <div className="px-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">{grp.group}</div>
                  {items.map((it) => {
                    const href = it.slug ? `/admin/${it.slug}` : '/admin'
                    const active = it.slug
                      ? pathname.startsWith(`/admin/${it.slug}`)
                      : pathname === '/admin'
                    const Icon = it.icon
                    return (
                      <Link key={it.slug || 'dashboard'} href={href}
                        className={`flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm font-medium ${
                          active
                            ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300'
                            : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                        }`}>
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className="truncate">{it.label}</span>
                      </Link>
                    )
                  })}
                </div>
              )
            })}
          </nav>
        </aside>

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar dark={dark} toggleTheme={toggleTheme} me={me} onSignOut={() => { clearTokens(); router.replace('/login') }} />
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </div>
  )
}

function TopBar({ dark, toggleTheme, me, onSignOut }: {
  dark: boolean; toggleTheme: () => void; me: OpsMe | null; onSignOut: () => void
}) {
  const primaryRole = me?.roles?.[0]
  return (
    <header className="flex items-center gap-4 border-b border-slate-200 bg-white px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex-1"><SearchBox /></div>
      <button onClick={toggleTheme} title="Toggle theme"
        className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
        {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
      <div className="hidden text-right sm:block">
        <div className="text-sm font-medium leading-tight">{me?.name || me?.phone_number}</div>
        <div className="text-[11px] text-slate-400">
          {me?.is_superuser ? 'Platform Super Admin' : primaryRole ? roleLabel(primaryRole) : 'Operator'}
        </div>
      </div>
      <button onClick={onSignOut} title="Sign out"
        className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
        <LogOut className="h-4 w-4" />
      </button>
    </header>
  )
}
