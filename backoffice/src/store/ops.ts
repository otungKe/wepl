import { create } from 'zustand'
import { ops, type OpsMe } from '@/lib/ops'

type Status = 'idle' | 'loading' | 'ready' | 'denied' | 'error'

interface OpsState {
  me: OpsMe | null
  status: Status
  load: () => Promise<void>
  reset: () => void
}

export const useOpsStore = create<OpsState>((set) => ({
  me: null,
  status: 'idle',
  load: async () => {
    set({ status: 'loading' })
    try {
      const { data } = await ops.me()
      set({ me: data, status: 'ready' })
    } catch (err) {
      const s = (err as { response?: { status?: number } })?.response?.status
      set({ status: s === 403 ? 'denied' : 'error' })
    }
  },
  reset: () => set({ me: null, status: 'idle' }),
}))

export function useCan() {
  const me = useOpsStore((s) => s.me)
  return (cap: string) => !!me && (me.is_superuser || me.capabilities.includes(cap))
}
