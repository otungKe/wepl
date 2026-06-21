'use client'
import { Sidebar } from '@/components/app/Sidebar'
import { useAuthStore } from '@/store/auth'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { getAccessToken, isTokenValid } from '@/lib/auth'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const user   = useAuthStore(s => s.user)

  useEffect(() => {
    const token = getAccessToken()
    if (!token || !isTokenValid(token)) {
      router.replace('/')
    }
  }, [router])

  if (!user) return null

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-primary-bg">
        {children}
      </main>
    </div>
  )
}
