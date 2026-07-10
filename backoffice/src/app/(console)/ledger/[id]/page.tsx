'use client'
// Account 360 — one account in full: identity (id, external UID, code), where it
// sits in the tree (its GL/pool parent and immediate children), and its balance.
// The detail companion to the Chart-of-Accounts browser (ADR-0025).
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { Loader2, ArrowLeft, BookOpen } from 'lucide-react'
import { accounts, type Account360, type AccountRow } from '@/lib/platform'

const ROLE_LABEL: Record<string, string> = { gl: 'GL head', pool: 'Pool control', member: 'Member sub-ledger' }

export default function Account360Page() {
  const params = useParams()
  const router = useRouter()
  const id = String(params.id)
  const [data, setData] = useState<Account360 | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  const load = useCallback(() => {
    setStatus('loading')
    accounts.account360(id).then((r) => { setData(r.data); setStatus('ready') }).catch(() => setStatus('error'))
  }, [id])
  useEffect(() => { load() }, [load])

  if (status === 'loading') return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
  if (status === 'error' || !data) return <p className="py-20 text-center text-sm text-slate-500">Couldn&apos;t load this account.</p>

  return (
    <div className="mx-auto max-w-5xl">
      <button onClick={() => router.push('/ledger')} className="mb-4 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <ArrowLeft className="h-4 w-4" /> Chart of Accounts
      </button>

      <div className="mb-1 flex flex-wrap items-center gap-3">
        <BookOpen className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="font-mono text-xl font-semibold">{data.code}</h1>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{ROLE_LABEL[data.role]}</span>
        <span className="font-mono text-lg tabular-nums text-slate-700 dark:text-slate-200">KES {data.balance}</span>
      </div>
      <p className="mb-5 text-sm text-slate-500">{data.name}</p>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Identity">
          <dl className="space-y-1.5 text-sm">
            <Row k="Code" v={<span className="font-mono text-xs">{data.code}</span>} />
            <Row k="External UID" v={<span className="font-mono text-[10px] break-all">{data.account_uid ?? '—'}</span>} />
            <Row k="Type" v={data.type} />
            <Row k="Currency" v={data.currency} />
            <Row k="Status" v={data.is_active ? 'Active' : 'Inactive'} />
          </dl>
        </Card>

        <Card title="Ownership & fund">
          <dl className="space-y-1.5 text-sm">
            <Row k="Owner" v={
              data.owner_id
                ? <Link href={`/users/${data.owner_id}`} className="text-blue-600 hover:underline dark:text-blue-400">{data.owner}</Link>
                : '— (control account)'} />
            {data.owner_member_no && <Row k="Member no." v={<span className="font-mono text-xs">{data.owner_member_no}</span>} />}
            <Row k="Fund" v={data.fund_type ? `${data.fund_type} #${data.fund_id}` : '—'} />
            <Row k="Rolls into" v={
              data.parent
                ? <Link href={`/ledger/${data.parent.id}`} className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400">{data.parent.code}</Link>
                : '— (top of tree)'} />
          </dl>
        </Card>
      </div>

      <div className="mt-5">
        <Card title={`Rolls up · immediate children${data.child_count ? ` (${data.child_count})` : ''}`}>
          {data.children.length === 0 ? (
            <p className="text-sm text-slate-400">A leaf account — no sub-accounts roll into it.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-100 dark:border-slate-800">
              <table className="w-full min-w-[520px] text-xs">
                <thead>
                  <tr className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                    <th className="px-3 py-1.5 text-left font-semibold">Account</th>
                    <th className="px-3 py-1.5 text-left font-semibold">Owner</th>
                    <th className="px-3 py-1.5 text-right font-semibold">Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {data.children.map((c: AccountRow) => (
                    <tr key={c.id} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="px-3 py-1.5">
                        <Link href={`/ledger/${c.id}`} className="font-mono text-[11px] text-blue-600 hover:underline dark:text-blue-400">{c.code}</Link>
                        <span className="ml-2 text-slate-500">{c.name}</span>
                      </td>
                      <td className="px-3 py-1.5 text-slate-500">{c.owner ?? '—'}</td>
                      <td className="px-3 py-1.5 text-right font-mono tabular-nums">{c.balance}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.child_count > data.children.length && (
                <p className="px-3 py-1.5 text-[10px] text-slate-400">Showing first {data.children.length} of {data.child_count}.</p>
              )}
            </div>
          )}
        </Card>
      </div>
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
