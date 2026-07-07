'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useOpsStore, useCan } from '@/store/ops'
import { usePaletteStore } from '@/store/palette'
import { NAV, roleLabel } from '@/lib/opsNav'
import { staffFirstName } from '@/lib/staff'
import { platform, type OpsMetrics } from '@/lib/platform'

function age(h: number | null | undefined) {
  if (h == null) return null
  if (h < 1) return `${Math.round(h * 60)}m`
  if (h < 48) return `${Math.round(h)}h`
  return `${Math.round(h / 24)}d`
}

export default function Dashboard() {
  const me = useOpsStore((s) => s.me)
  const can = useCan()
  const openPalette = usePaletteStore((s) => s.setOpen)
  const primaryRole = me?.roles?.[0]
  const h = new Date().getHours()
  const greeting = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
  const [m, setM] = useState<OpsMetrics | null>(null)

  useEffect(() => { platform.metrics().then((r) => setM(r.data)).catch(() => setM({})) }, [])

  // Modules this operator can reach (excludes the dashboard itself).
  const modules = NAV.flatMap((g) => g.items).filter((i) => i.slug && can(i.cap))

  // Live KPI tiles — each renders only when its metrics block came back
  // (the API filters blocks by capability).
  const tiles: { label: string; value: string | number; hint: string; href?: string; alert?: boolean }[] = []
  if (m?.verification) {
    tiles.push({
      label: 'KYC pending review', value: m.verification.kyc_pending,
      hint: m.verification.kyc_oldest_hours != null
        ? `oldest waiting ${age(m.verification.kyc_oldest_hours)}` : 'queue clear',
      href: '/verification', alert: (m.verification.kyc_oldest_hours ?? 0) > 24,
    })
    tiles.push({
      label: 'Transaction reviews', value: m.verification.edd_open,
      hint: 'held movements awaiting documents or decision', href: '/verification',
      alert: m.verification.edd_open > 0,
    })
  }
  if (m?.holds) tiles.push({
    label: 'Open holds', value: m.holds.open,
    hint: 'blocked movements in the review queue', alert: m.holds.open > 0,
  })
  if (m?.ledger) tiles.push({
    label: 'Trial-balance delta', value: m.ledger.trial_balance_delta,
    hint: m.ledger.balanced ? 'books balance' : 'BOOKS DO NOT BALANCE — investigate now',
    alert: !m.ledger.balanced,
  })
  if (m?.outbox) tiles.push({
    label: 'Outbox relay', value: m.outbox.pending,
    hint: m.outbox.dead > 0
      ? `${m.outbox.dead} dead-lettered event(s)`
      : m.outbox.oldest_pending_seconds != null
        ? `oldest pending ${m.outbox.oldest_pending_seconds}s` : 'all delivered',
    alert: m.outbox.dead > 0 || (m.outbox.oldest_pending_seconds ?? 0) > 300,
  })
  if (m?.communities) tiles.push({
    label: 'Communities', value: m.communities.active,
    hint: m.communities.suspended > 0
      ? `${m.communities.suspended} suspended` : `${m.communities.total} total`,
    href: '/communities', alert: m.communities.suspended > 0,
  })
  if (m?.users) tiles.push({
    label: 'Active members', value: m.users.total,
    hint: `${m.users.new_7d} joined in the last 7 days`,
  })

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">{greeting}, {staffFirstName(me?.name || me?.email) || 'Operator'}</h1>
        <p className="text-sm text-slate-500">
          {me?.is_superuser ? 'Platform Super Admin' : primaryRole ? roleLabel(primaryRole) : 'Operator'} · your shift overview
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(m === null ? [] : tiles).map((t) => {
          const inner = (
            <div className={`rounded-xl border bg-white p-4 dark:bg-slate-900 ${
              t.alert ? 'border-amber-300 dark:border-amber-500/40'
                      : 'border-slate-200 dark:border-slate-800'} ${t.href ? 'hover:border-blue-300 dark:hover:border-blue-500/40' : ''}`}>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{t.label}</div>
              <div className={`mt-2 font-mono text-2xl tabular-nums ${
                t.alert ? 'text-amber-600 dark:text-amber-400' : 'text-slate-800 dark:text-slate-100'}`}>
                {t.value}
              </div>
              <div className="mt-1 text-[11px] text-slate-400">{t.hint}</div>
            </div>
          )
          return t.href
            ? <Link key={t.label} href={t.href}>{inner}</Link>
            : <div key={t.label}>{inner}</div>
        })}
        {m === null && [1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900" />
        ))}
      </div>

      <div className="mt-8">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Your workspaces</h2>
          <button onClick={() => openPalette(true)} className="text-xs font-medium text-blue-600 dark:text-blue-400">Search or jump to… ⌘K</button>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {modules.map((mod) => {
            const Icon = mod.icon
            return (
              <Link key={mod.slug} href={`/${mod.slug}`}
                className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm hover:border-blue-300 hover:bg-blue-50/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-blue-500/40 dark:hover:bg-blue-500/5">
                <Icon className="h-4 w-4 shrink-0 text-slate-400" />
                <span className="truncate font-medium text-slate-700 dark:text-slate-200">{mod.label}</span>
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  )
}
