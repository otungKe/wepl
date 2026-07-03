'use client'
import Link from 'next/link'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  Building2, Users, Banknote, ShieldCheck, Smartphone, ArrowUpRight,
  ChevronRight, TrendingUp, Wallet,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { isAuthenticated } from '@/lib/auth'

const FEATURES = [
  { icon: Users, title: 'Communities & chamas', desc: 'Create or join savings groups and keep everyone in sync.' },
  { icon: Banknote, title: 'Contributions & ROSCA', desc: 'Pool funds, rotate payouts, run welfare funds and shares.' },
  { icon: ShieldCheck, title: 'Secure by design', desc: 'Phone + PIN auth, M-Pesa payments, an audited double-entry ledger.' },
]

export default function WelcomePage() {
  const router = useRouter()
  useEffect(() => { if (isAuthenticated()) router.replace('/communities') }, [router])

  return (
    <div className="flex min-h-screen flex-col bg-primary-bg">
      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary">
            <Building2 size={20} className="text-white" />
          </div>
          <span className="text-xl font-bold text-text">WEPL</span>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2">
          <ThemeToggle />
          <Link href="/login" className="hidden sm:block">
            <Button variant="ghost" size="sm">Sign in</Button>
          </Link>
          <Link href="/login?mode=register">
            <Button size="sm">Create account</Button>
          </Link>
        </div>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <main className="flex-1">
        <section className="mx-auto grid w-full max-w-6xl items-center gap-10 px-6 pb-14 pt-8 lg:grid-cols-2 lg:gap-14 lg:pt-16">
          {/* Copy */}
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-pale px-3 py-1 text-xs font-semibold text-primary">
              <Smartphone size={13} /> The financial OS for communities
            </span>
            <h1 className="mt-5 text-4xl font-bold leading-[1.1] tracking-tight text-text sm:text-5xl">
              Run your chama <span className="text-primary">end-to-end</span>, without the spreadsheets.
            </h1>
            <p className="mt-4 max-w-lg text-base text-text-secondary">
              Contributions, ROSCA payouts, welfare funds, emergency advances and shares —
              over M-Pesa, on one audited ledger.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link href="/login?mode=register"><Button size="lg" className="w-full sm:w-auto">Create account <ArrowUpRight size={18} /></Button></Link>
              <Link href="/login"><Button size="lg" variant="outline" className="w-full sm:w-auto">Sign in</Button></Link>
            </div>
            <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-text-muted">
              <span className="inline-flex items-center gap-1.5"><Smartphone size={14} className="text-primary" /> M-Pesa native</span>
              <span className="inline-flex items-center gap-1.5"><ShieldCheck size={14} className="text-primary" /> Double-entry ledger</span>
              <span className="inline-flex items-center gap-1.5"><Users size={14} className="text-primary" /> Built for chamas & SACCOs</span>
            </div>
          </div>

          {/* Product preview (borrows the dashboard layout) */}
          <ProductPreview />
        </section>

        {/* ── Features ──────────────────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-6xl px-6 pb-16">
          <div className="grid gap-4 sm:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="rounded-xl border border-border bg-surface p-5">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-pale text-primary">
                  <Icon size={20} />
                </div>
                <p className="mt-3 font-semibold text-text">{title}</p>
                <p className="mt-1 text-sm text-text-muted">{desc}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-divider">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-6 py-5 text-xs text-text-muted sm:flex-row">
          <span>© {new Date().getFullYear()} WEPL — Community finance</span>
          <span className="inline-flex items-center gap-1.5"><ShieldCheck size={13} /> Audited ledger · M-Pesa payments</span>
        </div>
      </footer>
    </div>
  )
}

/** A static, credible dashboard preview echoing the app's Communities page. */
function ProductPreview() {
  return (
    <div className="relative">
      <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-modal">
        {/* Header strip */}
        <div className="flex items-center justify-between border-b border-divider px-4 py-3">
          <span className="text-sm font-bold text-text">Communities</span>
          <span className="inline-flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1 text-xs font-semibold text-white">
            + New
          </span>
        </div>

        <div className="space-y-3 p-4">
          {/* Stat tiles */}
          <div className="grid grid-cols-2 gap-3">
            <PreviewStat icon={Wallet} value="KES 3.4M" label="Total managed" />
            <PreviewStat icon={TrendingUp} value="+8.6%" label="Growth this month" />
          </div>

          {/* Community rows */}
          <PreviewCommunity name="Household Chama" tag="Savings" tone="bg-success/10 text-success" members="48 members" amount="KES 245,000" />
          <PreviewCommunity name="Young Investors" tag="Investment" tone="bg-info/10 text-info" members="36 members" amount="+2.1%" />

          {/* Activity */}
          <div className="rounded-lg border border-border bg-primary-bg/60 px-3 py-2.5">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-success/15 text-success">
                <ArrowUpRight size={14} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-text">John contributed KES 5,000</p>
                <p className="text-[11px] text-text-muted">Household Chama · 2m ago</p>
              </div>
              <span className="text-xs font-semibold text-success">KES 5,000</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function PreviewStat({ icon: Icon, value, label }: { icon: typeof Wallet; value: string; label: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-pale text-primary">
        <Icon size={16} />
      </div>
      <p className="mt-2 text-lg font-bold tabular-nums text-text">{value}</p>
      <p className="text-[11px] text-text-muted">{label}</p>
    </div>
  )
}

function PreviewCommunity({ name, tag, tone, members, amount }: { name: string; tag: string; tone: string; members: string; amount: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary-dark text-white">
        <Users size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-text">{name}</p>
        <div className="mt-0.5 flex items-center gap-1.5">
          <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${tone}`}>{tag}</span>
          <span className="text-[11px] text-text-muted">· {members}</span>
        </div>
      </div>
      <span className="text-xs font-semibold text-text">{amount}</span>
      <ChevronRight size={15} className="text-text-muted" />
    </div>
  )
}
