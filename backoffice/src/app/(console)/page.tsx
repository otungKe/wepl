'use client'
import Link from 'next/link'
import { useOpsStore, useCan } from '@/store/ops'
import { usePaletteStore } from '@/store/palette'
import { NAV, roleLabel } from '@/lib/opsNav'

const TILES = [
  { label: 'Pending payouts', hint: 'Financial Operations · P2' },
  { label: 'KYC queue age (p95)', hint: 'Verification · P1' },
  { label: 'Open reconciliation breaks', hint: 'Reconciliation · P3' },
  { label: 'Trial-balance delta', hint: 'Ledger · P3', accent: true },
  { label: 'Outbox relay lag', hint: 'System Health · P4' },
  { label: 'My approvals', hint: 'Approvals · P2' },
]

export default function Dashboard() {
  const me = useOpsStore((s) => s.me)
  const can = useCan()
  const openPalette = usePaletteStore((s) => s.setOpen)
  const primaryRole = me?.roles?.[0]
  const h = new Date().getHours()
  const greeting = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'

  // Modules this operator can reach (excludes the dashboard itself).
  const modules = NAV.flatMap((g) => g.items).filter((i) => i.slug && can(i.cap))

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">{greeting}, {me?.name || me?.email}</h1>
        <p className="text-sm text-slate-500">
          {me?.is_superuser ? 'Platform Super Admin' : primaryRole ? roleLabel(primaryRole) : 'Operator'} · your shift overview
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map((t) => (
          <div key={t.label} className={`rounded-xl border bg-white p-4 dark:bg-slate-900 ${
            t.accent ? 'border-blue-200 dark:border-blue-500/30' : 'border-slate-200 dark:border-slate-800'}`}>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{t.label}</div>
            <div className="mt-2 font-mono text-2xl tabular-nums text-slate-300 dark:text-slate-600">—</div>
            <div className="mt-1 text-[11px] text-slate-400">{t.hint}</div>
          </div>
        ))}
      </div>
      <div className="mt-8">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Your workspaces</h2>
          <button onClick={() => openPalette(true)} className="text-xs font-medium text-blue-600 dark:text-blue-400">Search or jump to… ⌘K</button>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {modules.map((m) => {
            const Icon = m.icon
            return (
              <Link key={m.slug} href={`/${m.slug}`}
                className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm hover:border-blue-300 hover:bg-blue-50/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-blue-500/40 dark:hover:bg-blue-500/5">
                <Icon className="h-4 w-4 shrink-0 text-slate-400" />
                <span className="truncate font-medium text-slate-700 dark:text-slate-200">{m.label}</span>
              </Link>
            )
          })}
        </div>
      </div>

      <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white/50 p-6 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40">
        <p className="font-medium text-slate-600 dark:text-slate-300">Operations console — P0 complete</p>
        <p className="mt-1">Navigation, staff auth, RBAC, federated search and the ⌘K command palette are live.
          KPI tiles above fill in as their source modules ship (P1+). Press <kbd className="rounded border border-slate-300 px-1 text-[11px] dark:border-slate-600">⌘K</kbd> to
          search any user, community or journal — or jump to a workspace.</p>
      </div>
    </div>
  )
}
