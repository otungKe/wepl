import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { clearTokens, saveTokens } from '@/lib/auth'

interface User {
  id: string
  phone_number: string
  name: string
  kyc_status: 'not_submitted' | 'pending' | 'approved' | 'rejected'
  profile_photo?: string
}

interface AuthState {
  user: User | null
  pendingPhone: string
  setUser: (u: User) => void
  setPendingPhone: (p: string) => void
  login: (access: string, refresh: string, user: User) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      pendingPhone: '',
      setUser:        (user)  => set({ user }),
      setPendingPhone:(phone) => set({ pendingPhone: phone }),
      login: (access, refresh, user) => {
        saveTokens(access, refresh)
        set({ user })
      },
      logout: () => {
        clearTokens()
        set({ user: null })
      },
    }),
    { name: 'wepl-auth', partialize: (s) => ({ user: s.user }) }
  )
)
