'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, BookOpen, ShieldAlert } from 'lucide-react'
import { transactions, type Tx360 } from '@/lib/platform'
import { TxState } from '@/components/TxState'

export default function Transaction360Page() {
  const params = useParams()
  const router = useRouter()
  const id = String(params.id)
  const [data, setData] = useState<Tx360 | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  const load = useCallback(() => {
    setStatus('loading')
    transactions.tx360(id).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [id])
  useEffect(() => { load() }, [load])

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this transaction.</p>

  const m = data.movement

  return (
    <div className="mx-auto max-w-5xl">
      <button onClick={() => router.push('/transactions')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Transactions
      </button>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{m.op_type_label}</h1>
        <TxState state={m.state} />
        <span className="font-mono text-lg tabular-nums text-slate-700 dark:text-slate-200">KES {m.amount}</span>
      </div>
      <div className="mb-5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
        <span className="font-mono">#{m.id}</span>
        <span>Created {new Date(m.created_at).toLocaleString()}</span>
        <span className="font-mono">key {m.idempotency_key}</span>
      </div>

      {m.failure_reason && (
        <p className="mb-5 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-400">
          Failure: {m.failure_reason}
        </p>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Parties">
          <dl className="space-y-1.5 text-sm">
            <Row k="Initiated by" v={
              data.parties.initiated_by_id
                ? <Link href={`/users/${data.parties.initiated_by_id}`} className="text-blue-600 hover:underline dark:text-blue-400">{data.parties.initiated_by}</Link>
                : data.parties.initiated_by} />
            {data.parties.initiated_by_phone && <Row k="Phone" v={<span className="font-mono text-xs">{data.parties.initiated_by_phone}</span>} />}
            {data.parties.recipient_phone && <Row k="Recipient" v={<span className="font-mono text-xs">{data.parties.recipient_phone}</span>} />}
          </dl>
        </Card>

        <Card title="Context">
          <dl className="space-y-1.5 text-sm">
            <Row k="Fund" v={data.context.fund ?? '—'} />
            <Row k="Community" v={
              data.context.community_id
                ? <Link href={`/communities/${data.context.community_id}`} className="text-blue-600 hover:underline dark:text-blue-400">{data.context.community_name}</Link>
                : '—'} />
            {data.context.trigger_type && (
              <Row k="Triggered by" v={`${data.context.trigger_type.replace(/_/g, ' ')} #${data.context.trigger_id ?? ''}`} />
            )}
            {m.note && <Row k="Note" v={m.note} />}
          </dl>
        </Card>

        <Card title="Payment rail">
          <dl className="space-y-1.5 text-sm">
            <Row k="Receipt" v={<span className="font-mono text-xs">{data.rail.mpesa_receipt ?? '—'}</span>} />
            <Row k="Checkout ref" v={<span className="font-mono text-[11px]">{data.rail.mpesa_checkout_id ?? '—'}</span>} />
            <Row k="Conversation ref" v={<span className="font-mono text-[11px]">{data.rail.mpesa_conversation_id ?? '—'}</span>} />
          </dl>
        </Card>

        <Card title="Control decisions">
          {data.controls.length === 0 ? (
            <p className="text-sm text-slate-400">No control rules examined this movement.</p>
          ) : (
            <ul className="space-y-2">
              {data.controls.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <ShieldAlert className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                    c.decision === 'ALLOW' ? 'text-emerald-500' : 'text-amber-500'}`} />
                  <div>
                    <span className="font-semibold">{c.decision}</span>
                    {c.rule && <span className="text-slate-400"> · {c.rule}</span>}
                    <span className="block text-slate-500">{c.reason}</span>
                    <span className="block font-mono text-[10px] text-slate-400">{new Date(c.at).toLocaleString()}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {data.journal && (
        <div className="mt-5">
          <Card title="Journal (the money truth)">
            {data.journal.length === 0 ? (
              <p className="text-sm text-slate-400">No journal posted — this movement never reached the books.</p>
            ) : data.journal.map((j) => (
              <div key={j.id} className="mb-3 last:mb-0">
                <p className="mb-1.5 flex items-center gap-2 text-xs text-slate-500">
                  <BookOpen className="h-3.5 w-3.5" />
                  <span className="font-medium text-slate-700 dark:text-slate-200">Entry #{j.id}</span>
                  {j.narration && <span>· {j.narration}</span>}
                  {j.posted_at && <span className="font-mono text-[10px]">{new Date(j.posted_at).toLocaleString()}</span>}
                  {j.reverses_id && <span className="font-semibold text-amber-600 dark:text-amber-400">reverses #{j.reverses_id}</span>}
                </p>
                <div className="overflow-x-auto rounded-lg border border-slate-100 dark:border-slate-800">
                  <table className="w-full min-w-[480px] text-xs">
                    <thead>
                      <tr className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                        <th className="px-3 py-1.5 text-left font-semibold">Account</th>
                        <th className="px-3 py-1.5 text-right font-semibold">Debit</th>
                        <th className="px-3 py-1.5 text-right font-semibold">Credit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {j.lines.map((ln, i) => (
                        <tr key={i} className="border-t border-slate-100 dark:border-slate-800">
                          <td className="px-3 py-1.5">
                            <span className="font-mono text-[10px] text-slate-400">{ln.account_code}</span>
                            <span className="ml-2 text-slate-700 dark:text-slate-200">{ln.account_name}</span>
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                            {ln.direction === 'DEBIT' ? ln.amount : ''}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                            {ln.direction === 'CREDIT' ? ln.amount : ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </Card>
        </div>
      )}
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-slate-400">{title}</h2>
      {children}
    </div>
  )
}
function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="shrink-0 text-slate-400">{k}</dt>
      <dd className="min-w-0 text-right text-slate-700 dark:text-slate-200">{v}</dd>
    </div>
  )
}
