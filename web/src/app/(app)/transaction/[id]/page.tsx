'use client'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { Download, Hash, Phone, Smartphone, StickyNote, Wallet } from 'lucide-react'
import { contributions, apiError, type Transaction } from '@/lib/api'
import { txMeta } from '@/lib/transactions'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { ErrorState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatMoney, formatDate, formatTime, cn } from '@/lib/utils'

function Row({ icon: Icon, label, value }: { icon: typeof Hash; label: string; value: React.ReactNode }) {
  if (value == null || value === '') return null
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <Icon size={17} className="shrink-0 text-text-muted" />
      <span className="text-sm text-text-secondary">{label}</span>
      <span className="ml-auto text-right text-sm font-medium text-text">{value}</span>
    </div>
  )
}

export default function TransactionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [tx, setTx] = useState<Transaction | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      // No single-transaction endpoint yet; resolve from the caller's list.
      const all = await contributions.myTransactions()
      const found = all.find(t => String(t.id) === String(id)) ?? null
      if (!found) setError('This transaction could not be found.')
      setTx(found)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const meta = tx ? txMeta(tx.transaction_type) : null

  return (
    <div>
      <PageHeader title="Transaction" back="/transactions" />

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-36 rounded-2xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : error || !tx || !meta ? (
        <ErrorState
          title="Transaction unavailable"
          description={error ?? 'This transaction could not be found.'}
          onRetry={() => { setLoading(true); load() }}
        />
      ) : (
        <>
          {/* ── Hero (matches the mobile detail header) ─────────────────── */}
          <div className="overflow-hidden rounded-2xl bg-primary p-6 text-white">
            <p className="text-sm text-white/70">{meta.label}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums">
              {meta.inflow ? '+' : '−'} {formatMoney(tx.amount)}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold">
                {tx.contribution_title}
              </span>
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold">
                {formatDate(tx.created_at)}
              </span>
            </div>
          </div>

          {/* ── Actions ─────────────────────────────────────────────────── */}
          <div className="mt-4 flex items-center gap-2">
            <Button variant="outline" onClick={() => window.print()}>
              <Download size={16} /> Download receipt
            </Button>
            <Badge tone={meta.inflow ? 'success' : 'primary'}>{meta.label}</Badge>
          </div>

          {/* ── Details ─────────────────────────────────────────────────── */}
          <div className="mt-4 divide-y divide-divider overflow-hidden rounded-xl border border-border bg-surface">
            <Row icon={Wallet} label="Amount" value={formatMoney(tx.amount)} />
            <Row icon={Hash} label="Type" value={meta.label} />
            <Row icon={Wallet} label="Pool" value={tx.contribution_title} />
            <Row icon={Phone} label="From" value={tx.name ? `${tx.name} · ${tx.phone_number}` : tx.phone_number} />
            <Row icon={Smartphone} label="M-Pesa receipt" value={tx.mpesa_receipt ?? '—'} />
            <Row icon={Hash} label="Reference" value={tx.platform_ref} />
            <Row icon={StickyNote} label="Note" value={tx.note} />
            <Row icon={Hash} label="Date" value={`${formatDate(tx.created_at)}, ${formatTime(tx.created_at)}`} />
          </div>

          {/* ── Print-only receipt (see @media print in globals.css) ─────── */}
          <Receipt tx={tx} label={meta.label} sign={meta.inflow ? '+' : '−'} />
        </>
      )}
    </div>
  )
}

/**
 * Print-only document. Hidden off-screen normally; the print stylesheet in
 * globals.css hides all app chrome and shows only #receipt, so "Download receipt"
 * (window.print → Save as PDF) yields a clean one-page receipt.
 */
function Receipt({ tx, label, sign }: { tx: Transaction; label: string; sign: string }) {
  const rows: [string, string][] = [
    ['Type', label],
    ['Pool', tx.contribution_title],
    ['From', tx.name ? `${tx.name} (${tx.phone_number})` : tx.phone_number],
    ['M-Pesa receipt', tx.mpesa_receipt ?? '—'],
    ['Reference', tx.platform_ref],
    ['Date', `${formatDate(tx.created_at)}, ${formatTime(tx.created_at)}`],
    ...(tx.note ? [['Note', tx.note] as [string, string]] : []),
  ]
  return (
    <div id="receipt" className="receipt-doc">
      <div className="receipt-head">
        <div className="receipt-brand">WEPL</div>
        <div className="receipt-tag">Payment Receipt</div>
      </div>
      <div className="receipt-amount">{sign} {formatMoney(tx.amount)}</div>
      <table className="receipt-table">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td className="receipt-k">{k}</td>
              <td className="receipt-v">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="receipt-foot">
        Generated {formatDate(new Date().toISOString())} · Receipt #{tx.id} · This is a computer-generated receipt.
      </div>
    </div>
  )
}
