'use client'
// Ledger — the Chart-of-Accounts browser (ADR-0025). One searchable namespace
// over the whole tree: GL heads, pool control accounts, and member sub-ledgers.
// Inquiry-first, like Transactions: nothing loads until the operator searches;
// at millions of sub-ledgers you query for the account you want, you don't
// scroll the book.
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { BookOpen, Search, Loader2 } from 'lucide-react'
import { accounts, type AccountRow, type AccountFacets, type AccountFilters } from '@/lib/platform'

const ROLE_BADGE: Record<string, string> = {
  gl: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300',
  pool: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
  member: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
}
const ROLE_LABEL: Record<string, string> = { gl: 'GL', pool: 'Pool', member: 'Member' }

export default function LedgerBrowser() {
  // Form fields.
  const [q, setQ] = useState('')
  const [owner, setOwner] = useState('')
  const [gl, setGl] = useState('')
  const [type, setType] = useState('')
  const [role, setRole] = useState('')
  const [facets, setFacets] = useState<AccountFacets | null>(null)
  // Results.
  const [rows, setRows] = useState<AccountRow[]>([])
  const [count, setCount] = useState(0)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [err, setErr] = useState('')

  // One cheap call on mount (no criteria → no query) to populate the facets
  // (account types, GL heads); results stay idle.
  useEffect(() => {
    accounts.list({}).then((r) => setFacets(r.data.facets)).catch(() => {})
  }, [])

  const buildParams = (): AccountFilters => ({
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(owner.trim() ? { owner: owner.trim() } : {}),
    ...(gl ? { gl } : {}),
    ...(type ? { type } : {}),
    ...(role ? { role } : {}),
  })

  const hasCriteria = !!(q.trim() || owner.trim() || gl || type || role)

  const onSearch = (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!hasCriteria) { setErr('Enter at least one search criterion.'); return }
    setStatus('loading'); setErr('')
    accounts.list(buildParams())
      .then((r) => { setRows(r.data.results); setCount(r.data.count); setStatus('ready') })
      .catch(() => setStatus('error'))
  }

  const onClear = () => {
    setQ(''); setOwner(''); setGl(''); setType(''); setRole('')
    setRows([]); setCount(0); setStatus('idle'); setErr('')
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex items-center gap-3">
        <BookOpen className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        <h1 className="text-xl font-semibold">Chart of Accounts</h1>
      </div>

      {/* Inquiry form — the browser returns only what these ask for. */}
      <form onSubmit={onSearch} className="mb-5 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Code or name">
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="2000, 2000-0350000, Fee Revenue…" className={`${inputCls} font-mono`} />
          </Field>
          <Field label="Member">
            <input value={owner} onChange={(e) => setOwner(e.target.value)}
              placeholder="Phone, member no. or id" className={inputCls} />
          </Field>
          <Field label="GL head">
            <select value={gl} onChange={(e) => setGl(e.target.value)} className={inputCls}>
              <option value="">Any GL head</option>
              {facets?.gl_heads.map((o) => <option key={o.value} value={o.value}>{o.value} · {o.label}</option>)}
            </select>
          </Field>
          <Field label="Account type">
            <select value={type} onChange={(e) => setType(e.target.value)} className={inputCls}>
              <option value="">Any type</option>
              {facets?.types.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Field>
          <Field label="Role">
            <select value={role} onChange={(e) => setRole(e.target.value)} className={inputCls}>
              <option value="">Any role</option>
              {facets?.roles.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Field>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <button type="submit" disabled={status === 'loading'}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {status === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Search
          </button>
          <button type="button" onClick={onClear}
            className="rounded-lg px-3.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
            Clear
          </button>
          {err && <span className="text-sm text-red-600 dark:text-red-400">{err}</span>}
        </div>
      </form>

      {status === 'idle' && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          Search by code, member, fund or type to browse the ledger.
        </div>
      )}
      {status === 'loading' && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
      {status === 'error' && <p className="py-16 text-center text-sm text-slate-500">Couldn&apos;t run the inquiry.</p>}
      {status === 'ready' && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center text-sm text-slate-500 dark:border-slate-700">
          No accounts match these criteria.
        </div>
      )}

      {status === 'ready' && rows.length > 0 && (
        <>
          <div className="mb-2 text-xs text-slate-400">
            {count} account{count === 1 ? '' : 's'}{rows.length < count ? ` · showing first ${rows.length}` : ''}
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                  <th className="px-4 py-2.5 text-left font-semibold">Account</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Role</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Type</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Owner</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Under</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Balance (KES)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                    <td className="px-4 py-2.5">
                      <Link href={`/ledger/${r.id}`} className="block">
                        <span className="font-mono text-xs text-slate-800 dark:text-slate-100">{r.code}</span>
                        <span className="block text-[11px] text-slate-400">{r.name}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${ROLE_BADGE[r.role]}`}>{ROLE_LABEL[r.role]}</span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-500">{r.type}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500">
                      {r.owner_id
                        ? <Link href={`/users/${r.owner_id}`} className="text-blue-600 hover:underline dark:text-blue-400">{r.owner}</Link>
                        : '—'}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-slate-400">{r.parent_code ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">{r.balance}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

const inputCls =
  'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</span>
      {children}
    </label>
  )
}
