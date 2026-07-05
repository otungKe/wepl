import { create } from 'zustand'
import { ops, type OpsMe } from '@/lib/ops'

type OpsStatus = 'idle' | 'loading' | 'ready' | 'denied' | 'error'

interface OpsState {
  me: OpsMe | null
  status: OpsStatus
  load: () => Promise<void>
  reset: () => void
}

// Operator identity + capabilities, loaded once from /api/ops/me/. Gating in the
// UI is derived from `me.capabilities`; the backend is always the real authority.
export const useOpsStore = create<OpsState>((set) => ({
  me: null,
  status: 'idle',
  load: async () => {
    set({ status: 'loading' })
    try {
      const { data } = await ops.me()
      set({ me: data, status: 'ready' })
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      set({ status: status === 403 ? 'denied' : 'error' })
    }
  },
  reset: () => set({ me: null, status: 'idle' }),
}))

/** Returns a predicate `can(capability)` for conditional rendering. */
export function useCan() {
  const me = useOpsStore((s) => s.me)
  return (capability: string): boolean =>
    !!me && (me.is_superuser || me.capabilities.includes(capability))
}
