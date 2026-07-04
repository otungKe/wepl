'use client'
import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { Menu, X, Building2 } from 'lucide-react'
import { Sidebar } from '@/components/app/Sidebar'
import { KYCBanner } from '@/components/ui/KYCBanner'
import { useAuthStore } from '@/store/auth'
import { useTier } from '@/hooks/useTier'
import { getAccessToken, isTokenValid } from '@/lib/auth'
import { auth } from '@/lib/api'

// Routes a Tier 0 (unverified) user may reach — everything that leads toward
// verification. All other in-app routes are verified-only, matching the mobile
// tab bar where an unverified user only ever sees Profile (ADR-0022).
const TIER0_ALLOWED = ['/profile', '/kyc', '/settings']

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const user = useAuthStore(s => s.user)
  const setUser = useAuthStore(s => s.setUser)
  const { isVerified } = useTier()
  const [ready, setReady] = useState(false)
  const [drawer, setDrawer] = useState(false)

  useEffect(() => {
    const token = getAccessToken()
    if (!token || !isTokenValid(token)) {
      router.replace('/login')
      return
    }
    // Refresh the profile so KYC status / name are always current.
    auth.profile().then(r => setUser(r.data)).catch(() => {}).finally(() => setReady(true))
  }, [router, setUser])

  // Tier gate: once the fresh profile has loaded, keep unverified users out of
  // verified-only routes (e.g. /communities and its "Create community" action)
  // by redirecting them to Profile — the web analogue of the mobile back-guard.
  useEffect(() => {
    if (!ready || isVerified) return
    const allowed = TIER0_ALLOWED.some(p => pathname === p || pathname.startsWith(p + '/'))
    if (!allowed) router.replace('/profile')
  }, [ready, isVerified, pathname, router])

  if (!ready && !user) {
    return <div className="flex h-screen items-center justify-center bg-primary-bg" />
  }

  // While the redirect above is in flight (and for a returning Tier 0 user whose
  // persisted session hasn't refreshed yet), don't flash verified-only content
  // (e.g. the Communities page + its Create button) to an unverified user. The
  // redirect itself still waits for the fresh profile (`ready`) so a verified
  // user with an empty store is never bounced.
  const tier0Blocked = !isVerified &&
    !TIER0_ALLOWED.some(p => pathname === p || pathname.startsWith(p + '/'))

  return (
    <div className="flex h-screen overflow-hidden bg-primary-bg">
      {/* Desktop sidebar */}
      <div className="hidden lg:block">
        <Sidebar />
      </div>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawer(false)} />
          <div className="absolute left-0 top-0 h-full animate-slideUp">
            <Sidebar onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile top bar */}
        <header className="flex items-center gap-3 border-b border-border bg-surface px-4 py-3 lg:hidden">
          <button onClick={() => setDrawer(v => !v)} className="rounded-lg p-1.5 text-text-secondary hover:bg-divider">
            {drawer ? <X size={22} /> : <Menu size={22} />}
          </button>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
              <Building2 size={16} className="text-white" />
            </div>
            <span className="font-bold text-text">WEPL</span>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-6">
            <KYCBanner />
            <div className="mt-4">{tier0Blocked ? null : children}</div>
          </div>
        </main>
      </div>
    </div>
  )
}
