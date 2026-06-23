'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  TrendingUp, Wallet, ArrowUpCircle, ArrowDownCircle, Receipt,
  Zap, CheckCircle2, Coins,
} from 'lucide-react'
import {
  reports, contributions, apiError,
  type FinancialSummary, type Transaction, type Contribution,
} from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { Tabs } from '@/components/ui/Tabs'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatMoney, formatDate, cn } from '@/lib/utils'
import { toast } from 'sonner'

function fmtKES(n: number) {
  if (n >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000)     return `KES ${(n / 1_000).toFixed(1)}K`
  return `KES ${Math.round(n).toLocaleString()}`
}

const TX_META: Record<string, { label: string; icon: typeof Receipt; tone: string; sign: 1 | -1 }> = {
  CONTRIBUTION: { label: 'Contribution', icon: ArrowUpCircle,   tone: 'text-primary', sign: -1 },
  WITHDRAWAL:   { label: 'Withdrawal',   icon: ArrowDownCircle, tone: 'text-primary', sign: 1 },
  ADVANCE:      { label: 'Advance',      icon: Zap,             tone: 'text-accent',  sign: 1 },
  REPAYMENT:    { label: 'Repayment',    icon: CheckCircle2,    tone: 'text-blue-600', sign: -1 },
}

type TxFilter = 'all' | 'CONTRIBUTION' | 'WITHDRAWAL' | 'ADVANCE' | 'REPAYMENT'

export default function ReportsPage() {
  const [tab, setTab] = useState('overview')
  const [summary, setSummary] = useState<FinancialSummary | null>(null)
  const [txns, setTxns] = useState<Transaction[]>([])
  const [pools, setPools] = useState<Contribution[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<TxFilter>('all')

  useEffect(() => {
    Promise.all([
      reports.financialSummary().then(r => r.data).catch(() => null),
      contributions.myTransactions().catch(() => []),
      contributions.mine().catch(() => []),
    ]).then(([s, t, p]) => { setSummary(s); setTxns(t); setPools(p) })
      .catch(e => toast.error(apiError(e)))
      .finally(() => setLoading(false))
  }, [])

  const filtered = filter === 'all' ? txns : txns.filter(t => t.transaction_type === filter)

  return (
    <div>
      <PageHeader title="Reports & statements" subtitle="Your contributions, payouts and transaction history" />

      <Tabs active={tab} onChange={setTab} className="mb-4"
        tabs={[
          { key: 'overview', label: 'Overview' },
          { key: 'transactions', label: 'Transactions' },
          { key: 'contributions', label: 'Pools' },
        ]} />

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : tab === 'overview' ? (
        !summary ? <EmptyState icon={TrendingUp} title="No summary yet" description="Your financial summary will appear once you start contributing." /> : (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard accent label="Total saved" value={fmtKES(summary.total_contributed)} icon={Wallet}
                hint={summary.this_month > 0 ? `↑ ${fmtKES(summary.this_month)} this month` : 'No contributions yet'} />
              <StatCard label="Total received" value={fmtKES(summary.total_received)} icon={ArrowDownCircle}
                hint={`${summary.active_contributions} active pools`} />
              <StatCard label="Transactions" value={String(summary.tx_count)} icon={Receipt}
                hint={`${summary.total_contributions} pools total`} />
              <StatCard label="This month" value={fmtKES(summary.this_month)} icon={TrendingUp}
                hint={summary.last_month > 0 ? `${fmtKES(summary.last_month)} last month` : '—'} />
            </div>

            {summary.monthly_trend?.length > 0 && (
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="mb-3 text-sm font-semibold text-text">Monthly contributions</p>
                <MonthlyTrend data={summary.monthly_trend} />
              </div>
            )}

            {summary.pending_advances > 0 && (
              <div className="flex items-center justify-between rounded-lg border border-accent/30 bg-accent-pale px-4 py-3">
                <div className="flex items-center gap-2 text-accent"><Zap size={18} /><span className="font-medium">Outstanding advances</span></div>
                <div className="text-right">
                  <p className="font-bold text-accent">{fmtKES(summary.advance_balance_due)} due</p>
                  <p className="text-xs text-text-muted">{summary.pending_advances} active</p>
                </div>
              </div>
            )}

            <p className="text-center text-xs text-text-muted">Member since {formatDate(summary.member_since)}</p>
          </div>
        )
      ) : tab === 'transactions' ? (
        <div>
          <div className="mb-3 flex flex-wrap gap-2">
            {(['all', 'CONTRIBUTION', 'WITHDRAWAL', 'ADVANCE', 'REPAYMENT'] as TxFilter[]).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={cn('rounded-full border px-3 py-1 text-sm',
                  filter === f ? 'border-primary bg-primary text-white' : 'border-border bg-surface text-text-secondary hover:bg-divider')}>
                {f === 'all' ? 'All' : TX_META[f].label}
              </button>
            ))}
          </div>
          {filtered.length === 0 ? (
            <EmptyState icon={Receipt} title="No transactions" description="Your contributions and payouts will be listed here." />
          ) : (
            <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
              {filtered.map(t => {
                const meta = TX_META[t.transaction_type] ?? { label: t.transaction_type, icon: Receipt, tone: 'text-text-muted', sign: 1 as const }
                const Icon = meta.icon
                return (
                  <div key={t.id} className="flex items-center gap-3 p-3.5">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-divider"><Icon size={18} className={meta.tone} /></div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-text">{t.contribution_title || meta.label}</p>
                      <p className="truncate text-sm text-text-muted">{meta.label} · {formatDate(t.created_at)}{t.mpesa_receipt ? ` · ${t.mpesa_receipt}` : ''}</p>
                    </div>
                    <p className={cn('shrink-0 font-semibold tabular-nums', meta.sign === -1 ? 'text-primary' : 'text-text')}>
                      {meta.sign === -1 ? '+' : '−'}{formatMoney(t.amount)}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      ) : (
        pools.length === 0 ? (
          <EmptyState icon={Coins} title="No contributions" description="Pools you join or create will appear here." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {pools.map(ct => (
              <Link key={ct.id} href={`/contribution/${ct.id}`} className="rounded-lg border border-border bg-surface p-4 hover:shadow-card">
                <div className="flex items-center justify-between">
                  <p className="truncate font-semibold text-text">{ct.title}</p>
                  <Badge tone={ct.status === 'active' ? 'success' : 'neutral'}>{ct.status}</Badge>
                </div>
                <p className="mt-1 text-sm text-text-muted">{ct.participant_count} members · {ct.frequency}</p>
                <p className="mt-2 text-lg font-bold text-primary">{formatMoney(ct.current_amount)}</p>
                {ct.user_balance != null && <p className="mt-0.5 text-xs text-text-muted">Your balance: {formatMoney(ct.user_balance)}</p>}
              </Link>
            ))}
          </div>
        )
      )}
    </div>
  )
}

function MonthlyTrend({ data }: { data: { month: string; amount: number }[] }) {
  const max = Math.max(...data.map(d => d.amount), 1)
  return (
    <div className="flex items-end gap-2" style={{ height: 140 }}>
      {data.map((d, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-1.5">
          <div className="flex w-full flex-1 items-end">
            <div className="w-full rounded-t bg-primary/80 transition-all"
              style={{ height: `${Math.max((d.amount / max) * 100, 2)}%` }}
              title={fmtKES(d.amount)} />
          </div>
          <span className="text-[10px] text-text-muted">{d.month}</span>
        </div>
      ))}
    </div>
  )
}
