'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Moon, Sun, LogOut, ShieldAlert, Loader2, Search } from 'lucide-react'
import { getToken, clearToken, type OpsMe } from '@/lib/ops'
import { useOpsStore, useCan } from '@/store/ops'
import { usePaletteStore } from '@/store/palette'
import { NAV, roleLabel } from '@/lib/opsNav'
import { staffFirstName } from '@/lib/staff'
import { CommandPalette } from '@/components/CommandPalette'

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { me, status, load } = useOpsStore()
  const can = useCan()
  const [dark, setDark] = useState(true)

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? localStorage.getItem('ops-theme') : null
    if (saved) setDark(saved === 'dark')
  }, [])
  const toggleTheme = () => setDark((d) => { localStorage.setItem('ops-theme', !d ? 'dark' : 'light'); return !d })
  useEffect(() => { document.documentElement.classList.toggle('dark', dark) }, [dark])

  useEffect(() => {
    if (!getToken()) { router.replace('/login'); return }
    if (status === 'idle') load()
  }, [router, status, load])

  // An operator who still owes a password change can't use the console.
  useEffect(() => {
    if (status === 'ready' && me?.must_change_password) router.replace('/login')
  }, [status, me, router])

  const signOut = () => { clearToken(); router.replace('/login') }

  if (status === 'idle' || status === 'loading') {
    return <Center><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></Center>
  }
  if (status === 'denied') {
    return (
      <Center>
        <ShieldAlert className="h-10 w-10 text-amber-500" />
        <h1 className="text-lg font-semibold">No Back Office access</h1>
        <p className="max-w-sm text-center text-sm text-slate-500">
          Your account isn&apos;t assigned an operations role. Ask a Platform Admin to grant you one.
        </p>
        <button onClick={signOut} className="mt-2 rounded-md bg-slate-200 px-4 py-2 text-sm font-medium text-slate-900 dark:bg-slate-800 dark:text-slate-100">Sign out</button>
      </Center>
    )
  }
  if (status === 'error') {
    return <Center><p className="text-sm text-slate-500">Couldn&apos;t load the console.</p>
      <button onClick={() => load()} className="rounded-md border border-slate-300 px-4 py-2 text-sm dark:border-slate-700">Retry</button></Center>
  }

  return (
    <div className="flex min-h-screen">
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
                  const href = it.slug ? `/${it.slug}` : '/'
                  const active = it.slug ? pathname.startsWith(`/${it.slug}`) : pathname === '/'
                  const Icon = it.icon
                  return (
                    <Link key={it.slug || 'dashboard'} href={href}
                      className={`flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm font-medium ${
                        active ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300'
                               : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'}`}>
                      <Icon className="h-4 w-4 shrink-0" /><span className="truncate">{it.label}</span>
                    </Link>
                  )
                })}
              </div>
            )
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar dark={dark} toggleTheme={toggleTheme} me={me} onSignOut={signOut} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
      <CommandPalette />
    </div>
  )
}

function Center({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50 px-6 dark:bg-slate-950">{children}</div>
}

function TopBar({ dark, toggleTheme, me, onSignOut }: {
  dark: boolean; toggleTheme: () => void; me: OpsMe | null; onSignOut: () => void }) {
  const primaryRole = me?.roles?.[0]
  const openPalette = usePaletteStore((s) => s.setOpen)
  return (
    <header className="flex items-center gap-4 border-b border-slate-200 bg-white px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900">
      <button onClick={() => openPalette(true)}
        className="flex max-w-md flex-1 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:bg-slate-800">
        <Search className="h-4 w-4" />
        <span className="flex-1 text-left">Search or jump to…</span>
        <kbd className="hidden rounded border border-slate-300 px-1.5 text-[10px] font-medium sm:inline dark:border-slate-600">⌘K</kbd>
      </button>
      <button onClick={toggleTheme} title="Toggle theme" className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
        {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
      <div className="hidden text-right sm:block">
        <div className="text-sm font-medium leading-tight">{staffFirstName(me?.name || me?.email) || 'Operator'}</div>
        <div className="text-[11px] text-slate-400">
          {me?.is_superuser ? 'Platform Super Admin' : primaryRole ? roleLabel(primaryRole) : 'Operator'}
        </div>
      </div>
      <button onClick={onSignOut} title="Sign out" className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
        <LogOut className="h-4 w-4" />
      </button>
    </header>
  )
}
