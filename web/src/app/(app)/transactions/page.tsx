'use client'
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ChevronRight, Receipt } from 'lucide-react'
import { contributions, apiError, type Transaction } from '@/lib/api'
import { txMeta, TX_FILTERS } from '@/lib/transactions'
import { PageHeader } from '@/components/app/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { EmptyState, ErrorState } from '@/components/ui/EmptyState'
import { CardSkeleton } from '@/components/ui/Spinner'
import { formatMoney, formatDate, formatTime, cn } from '@/lib/utils'

export default function TransactionsPage() {
  const router = useRouter()
  const [txns, setTxns] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('all')

  const load = useCallback(async () => {
    setError(null)
    try {
      setTxns(await contributions.myTransactions())
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = filter === 'all' ? txns : txns.filter(t => t.transaction_type === filter)

  return (
    <div>
      <PageHeader title="Transactions" subtitle="Your contributions, payouts and advances" />

      <Tabs
        className="mb-4"
        active={filter}
        onChange={setFilter}
        tabs={TX_FILTERS.map(f => ({ key: f.key, label: f.label }))}
      />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : error ? (
        <ErrorState onRetry={() => { setLoading(true); load() }} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Receipt}
          title={filter === 'all' ? 'No transactions yet' : 'Nothing here'}
          description={filter === 'all'
            ? 'Your contributions and payments will appear here.'
            : 'No transactions match this filter.'}
        />
      ) : (
        <div className="divide-y divide-divider overflow-hidden rounded-xl border border-border bg-surface">
          {filtered.map(t => {
            const meta = txMeta(t.transaction_type)
            const Icon = meta.icon
            return (
              <button
                key={t.id}
                onClick={() => router.push(`/transaction/${t.id}`)}
                className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-divider/50"
              >
                <div className={cn(
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
                  meta.inflow ? 'bg-success/10 text-success' : 'bg-primary-pale text-primary',
                )}>
                  <Icon size={20} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-text">{t.contribution_title}</p>
                  <p className="truncate text-xs text-text-muted">
                    {meta.label} · {formatDate(t.created_at)}, {formatTime(t.created_at)}
                    {t.mpesa_receipt ? ` · ${t.mpesa_receipt}` : ''}
                  </p>
                </div>
                <span className={cn(
                  'shrink-0 text-sm font-semibold tabular-nums',
                  meta.inflow ? 'text-success' : 'text-text',
                )}>
                  {meta.inflow ? '+' : '−'} {formatMoney(t.amount)}
                </span>
                <ChevronRight size={16} className="shrink-0 text-text-muted" />
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
