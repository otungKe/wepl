'use client'
// Console alert bell (OP-2). Polls open StaffNotice alerts raised by ops_alerts
// and lets any operator glance at (and dismiss) them. Critical alerts pulse red.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Loader2, X } from 'lucide-react'
import { notices, type Notice } from '@/lib/platform'

export function NoticeBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<Notice[]>([])
  const [critical, setCritical] = useState(0)
  const [busyId, setBusyId] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    notices.list().then((r) => { setItems(r.data.results); setCritical(r.data.critical) }).catch(() => {})
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 60_000)   // refresh every minute
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    const onClick = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const dismiss = async (id: number) => {
    setBusyId(id)
    try { await notices.dismiss(id); load() } catch { /* ignore */ } finally { setBusyId(null) }
  }

  const count = items.length

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} title="Alerts"
        className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
        <Bell className="h-4 w-4" />
        {count > 0 && (
          <span className={`absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[9px] font-bold text-white ${
            critical > 0 ? 'animate-pulse bg-red-600' : 'bg-amber-500'}`}>
            {count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900">
          <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-400 dark:border-slate-800">
            Alerts {count > 0 && `(${count})`}
          </div>
          {count === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-slate-400">All clear.</p>
          ) : (
            <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
              {items.map((n) => (
                <li key={n.id} className="flex items-start gap-2 px-4 py-3">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    n.level === 'CRITICAL' ? 'bg-red-500' : n.level === 'WARNING' ? 'bg-amber-500' : 'bg-slate-400'}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{n.title}</p>
                    <p className="text-xs text-slate-500">{n.message}</p>
                    <p className="mt-0.5 text-[10px] text-slate-400">{new Date(n.created_at).toLocaleString()}</p>
                  </div>
                  <button onClick={() => dismiss(n.id)} disabled={busyId === n.id}
                    title="Dismiss" className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
                    {busyId === n.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
