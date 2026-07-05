import { create } from 'zustand'

interface PaletteState {
  open: boolean
  setOpen: (v: boolean) => void
  toggle: () => void
}

// Global open-state for the ⌘K command palette so the topbar trigger and the
// keyboard shortcut both drive the same modal.
export const usePaletteStore = create<PaletteState>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  toggle: () => set((s) => ({ open: !s.open })),
}))
