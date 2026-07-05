'use client'
import { useOpsStore } from '@/store/ops'
import { roleLabel } from '@/lib/opsNav'

// P0 dashboard placeholder. Real KPI tiles + "my queues" / "my approvals" land as
// their source modules ship (P1+); the layout is here so the shell is complete.
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
  const primaryRole = me?.roles?.[0]

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">
          {greeting()}, {me?.name || me?.phone_number}
        </h1>
        <p className="text-sm text-slate-500">
          {me?.is_superuser ? 'Platform Super Admin' : primaryRole ? roleLabel(primaryRole) : 'Operator'} ·
          {' '}your shift overview
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map((t) => (
          <div key={t.label}
            className={`rounded-xl border bg-white p-4 dark:bg-slate-900 ${
              t.accent ? 'border-blue-200 dark:border-blue-500/30' : 'border-slate-200 dark:border-slate-800'
            }`}>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{t.label}</div>
            <div className="mt-2 font-mono text-2xl tabular-nums text-slate-300 dark:text-slate-600">—</div>
            <div className="mt-1 text-[11px] text-slate-400">{t.hint}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white/50 p-6 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40">
        <p className="font-medium text-slate-600 dark:text-slate-300">Operations console — P0 shell</p>
        <p className="mt-1">
          Navigation, auth, RBAC and federated search are live. Each module in the sidebar
          fills in with its real queues and KPIs across phases P1–P4. Use search (⌘K) to jump to
          any user, community or journal you have access to.
        </p>
      </div>
    </div>
  )
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}
