'use client'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Search, CornerDownLeft } from 'lucide-react'
import { ops, type OpsSearchResult } from '@/lib/ops'

const TYPE_LABEL: Record<string, string> = {
  user: 'User', community: 'Community', verification: 'KYC', journal: 'Journal',
}

// Topbar federated search. A lightweight precursor to the full ⌘K command
// palette (P0.4): debounced query → /api/ops/search/ → deep-linkable results.
export function SearchBox() {
  const router = useRouter()
  const [q, setQ] = useState('')
  const [results, setResults] = useState<OpsSearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // ⌘K / Ctrl-K focuses the box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault(); inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Close on outside click.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setResults([]); return }
    setLoading(true)
    const t = setTimeout(() => {
      ops.search(term)
        .then((r) => { setResults(r.data.results); setOpen(true) })
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 220)
    return () => clearTimeout(t)
  }, [q])

  const go = (r: OpsSearchResult) => {
    setOpen(false); setQ('')
    router.push(r.url)
  }

  return (
    <div ref={boxRef} className="relative w-full max-w-md">
      <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800/60">
        <Search className="h-4 w-4 text-slate-400" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onKeyDown={(e) => { if (e.key === 'Enter' && results[0]) go(results[0]); if (e.key === 'Escape') setOpen(false) }}
          placeholder="Search users, communities, journals…"
          className="w-full bg-transparent text-slate-800 placeholder:text-slate-400 focus:outline-none dark:text-slate-100"
        />
        <kbd className="hidden rounded border border-slate-300 px-1.5 text-[10px] font-medium text-slate-400 sm:inline dark:border-slate-600">⌘K</kbd>
      </div>

      {open && (results.length > 0 || loading) && (
        <div className="absolute z-50 mt-1.5 w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {loading && <div className="px-3 py-2 text-xs text-slate-400">Searching…</div>}
          {results.map((r) => (
            <button
              key={`${r.type}-${r.id}`}
              onClick={() => go(r)}
              className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              <span className="w-16 shrink-0 text-[10px] font-semibold uppercase tracking-wide text-slate-400">{TYPE_LABEL[r.type] ?? r.type}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-slate-800 dark:text-slate-100">{r.label}</span>
                <span className="block truncate text-xs text-slate-400">{r.sublabel}</span>
              </span>
              <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-slate-300 dark:text-slate-600" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
