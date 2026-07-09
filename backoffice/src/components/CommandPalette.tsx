'use client'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Search, CornerDownLeft, ArrowUp, ArrowDown } from 'lucide-react'
import { ops, type OpsSearchResult } from '@/lib/ops'
import { usePaletteStore } from '@/store/palette'
import { useCan } from '@/store/ops'
import { NAV } from '@/lib/opsNav'

type Item =
  | { kind: 'nav'; group: string; label: string; sublabel?: string; href: string }
  | { kind: 'entity'; group: string; label: string; sublabel?: string; href: string }

const GROUP_ORDER = ['Go to', 'User', 'Transaction', 'Verification', 'Community', 'Journal']
const ENTITY_GROUP: Record<OpsSearchResult['type'], string> = {
  user: 'User', transaction: 'Transaction', verification: 'Verification',
  community: 'Community', journal: 'Journal',
}

// Backend deep-links are /admin/*; this app serves the console at the root.
const toConsolePath = (url: string) => url.replace(/^\/admin/, '') || '/'

export function CommandPalette() {
  const router = useRouter()
  const { open, setOpen, toggle } = usePaletteStore()
  const can = useCan()
  const [q, setQ] = useState('')
  const [entities, setEntities] = useState<OpsSearchResult[]>([])
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // ⌘K / Ctrl-K toggles; also global so it works from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); toggle() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  useEffect(() => {
    if (open) { setQ(''); setEntities([]); setActive(0); setTimeout(() => inputRef.current?.focus(), 0) }
  }, [open])

  // Debounced federated search for entities.
  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setEntities([]); return }
    const t = setTimeout(() => {
      ops.search(term).then((r) => setEntities(r.data.results)).catch(() => setEntities([]))
    }, 200)
    return () => clearTimeout(t)
  }, [q])

  const navCommands = useMemo<Item[]>(() =>
    NAV.flatMap((g) => g.items).filter((i) => can(i.cap)).map((i) => ({
      kind: 'nav', group: 'Go to', label: i.label, href: i.slug ? `/${i.slug}` : '/',
    })), [can])

  const items = useMemo<Item[]>(() => {
    const term = q.trim().toLowerCase()
    const nav = term ? navCommands.filter((c) => c.label.toLowerCase().includes(term)) : navCommands
    const ent: Item[] = entities.map((r) => ({
      kind: 'entity', group: ENTITY_GROUP[r.type], label: r.label, sublabel: r.sublabel,
      href: toConsolePath(r.url),
    }))
    const all = [...nav, ...ent]
    return all.sort((a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group))
  }, [q, navCommands, entities])

  useEffect(() => { setActive((a) => Math.min(a, Math.max(0, items.length - 1))) }, [items.length])

  if (!open) return null

  const select = (it?: Item) => { if (!it) return; setOpen(false); router.push(it.href) }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); select(items[active]) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  // Group items for rendering while keeping a flat index for keyboard nav.
  let idx = -1
  const groups = GROUP_ORDER.filter((g) => items.some((i) => i.group === g))

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 p-4 pt-[12vh]"
      onMouseDown={() => setOpen(false)}>
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-slate-100 px-4 dark:border-slate-800">
          <Search className="h-4 w-4 text-slate-400" />
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKeyDown}
            placeholder="Search or jump to…"
            className="w-full bg-transparent py-3.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none dark:text-slate-100" />
          <kbd className="rounded border border-slate-300 px-1.5 text-[10px] text-slate-400 dark:border-slate-600">ESC</kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto py-2">
          {items.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-slate-400">
              {q.trim().length >= 2 ? 'No matches.' : 'Type to search users, journals, communities — or jump to a module.'}
            </div>
          )}
          {groups.map((g) => (
            <div key={g} className="mb-1">
              <div className="px-4 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">{g}</div>
              {items.filter((i) => i.group === g).map((it) => {
                idx += 1; const here = idx
                const isActive = here === active
                return (
                  <button key={`${g}-${it.label}-${here}`}
                    onMouseEnter={() => setActive(here)} onClick={() => select(it)}
                    className={`flex w-full items-center gap-3 px-4 py-2 text-left ${
                      isActive ? 'bg-blue-50 dark:bg-blue-500/10' : ''}`}>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-slate-800 dark:text-slate-100">{it.label}</span>
                      {it.sublabel && <span className="block truncate text-xs text-slate-400">{it.sublabel}</span>}
                    </span>
                    {isActive && <CornerDownLeft className="h-3.5 w-3.5 text-slate-400" />}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        <div className="flex items-center gap-4 border-t border-slate-100 px-4 py-2 text-[11px] text-slate-400 dark:border-slate-800">
          <span className="flex items-center gap-1"><ArrowUp className="h-3 w-3" /><ArrowDown className="h-3 w-3" /> navigate</span>
          <span className="flex items-center gap-1"><CornerDownLeft className="h-3 w-3" /> open</span>
        </div>
      </div>
    </div>
  )
}
