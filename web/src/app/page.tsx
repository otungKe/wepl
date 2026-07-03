'use client'
import Link from 'next/link'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  Building2, Layers, Users, Wallet, ShieldCheck, Eye, MessagesSquare, Scale,
  ArrowUpRight, ChevronRight, TrendingUp, Check, Minus,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { isAuthenticated } from '@/lib/auth'

// Benefit-led, mapped to the three pillars: conversations · money · decisions.
const FEATURES = [
  {
    icon: MessagesSquare,
    title: 'Bring everyone together',
    desc: 'Group chat, announcements and member management in one shared space.',
  },
  {
    icon: Wallet,
    title: 'Manage money together',
    desc: 'Contributions, payouts, welfare and savings — with every balance kept clear.',
  },
  {
    icon: Scale,
    title: 'Decide and stay accountable',
    desc: 'Propose, vote and approve, with every action recorded in one auditable history.',
  },
]

const HERO_CHIPS = [
  { icon: Eye, label: 'Transparent by design' },
  { icon: ShieldCheck, label: 'Audited ledger' },
  { icon: Users, label: 'Real-time collaboration' },
]

const TODAY = ['Endless group chats', 'Spreadsheets that drift', 'Notebooks and paper records', 'Scattered payment statements']
const WITH_WEPL = ['One shared workspace', 'One reconciled ledger', 'One clear decision history', 'One source of truth']

const TRUST = [
  'Every transaction is recorded',
  'Every action is traceable',
  'Every balance is reconciled',
  'Members see only what they’re permitted to',
]

export default function WelcomePage() {
  const router = useRouter()
  useEffect(() => { if (isAuthenticated()) router.replace('/communities') }, [router])

  return (
    <div className="flex min-h-screen flex-col bg-primary-bg">
      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-transparent bg-primary-bg/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary">
              <Building2 size={20} className="text-white" />
            </div>
            <span className="text-xl font-bold tracking-tight text-text">WEPL</span>
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
        </div>
      </header>

      <main className="flex-1">
        {/* ── Hero ──────────────────────────────────────────────────────── */}
        <section className="mx-auto grid w-full max-w-6xl items-center gap-12 px-6 pb-20 pt-10 lg:grid-cols-2 lg:gap-16 lg:pb-28 lg:pt-20">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs font-semibold text-primary">
              <Layers size={13} /> The operating system for communities
            </span>
            <h1 className="mt-6 text-4xl font-bold leading-[1.08] tracking-tight text-text sm:text-5xl lg:text-[3.35rem]">
              One platform for your community&apos;s <span className="text-primary">money, conversations and decisions</span>.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-text-secondary">
              Bring your community&apos;s finances, conversations and governance into one trusted
              place — where members stay aligned and every balance is accounted for.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/login?mode=register"><Button size="lg" className="w-full sm:w-auto">Create account <ArrowUpRight size={18} /></Button></Link>
              <Link href="/login"><Button size="lg" variant="outline" className="w-full sm:w-auto">Sign in</Button></Link>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2.5 text-xs font-medium text-text-muted">
              {HERO_CHIPS.map(({ icon: Icon, label }) => (
                <span key={label} className="inline-flex items-center gap-1.5"><Icon size={14} className="text-primary" /> {label}</span>
              ))}
            </div>
          </div>

          <ProductPreview />
        </section>

        {/* ── Features ──────────────────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-6xl px-6 py-16 lg:py-20">
          <SectionHeading
            eyebrow="One workspace"
            title="Everything your community needs, in one place"
            subtitle="Communication, money and governance — designed to work together, not in separate apps."
          />
          <div className="mt-10 grid gap-4 sm:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="group rounded-2xl border border-border bg-surface p-6 transition-colors hover:border-primary/30">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-pale text-primary">
                  <Icon size={22} />
                </div>
                <p className="mt-4 text-base font-semibold text-text">{title}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-text-muted">{desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Why WEPL — from scattered tools to one source of truth ─────── */}
        <section className="mx-auto w-full max-w-6xl px-6 py-16 lg:py-20">
          <SectionHeading
            eyebrow="Why WEPL"
            title="One source of truth, instead of five"
            subtitle="Communities lose money and trust in the gaps between tools. WEPL closes them."
          />
          <div className="mt-10 grid overflow-hidden rounded-2xl border border-border bg-surface md:grid-cols-2">
            <div className="border-b border-divider p-7 md:border-b-0 md:border-r">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Today</p>
              <ul className="mt-4 space-y-3">
                {TODAY.map(item => (
                  <li key={item} className="flex items-center gap-3 text-sm text-text-muted">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-divider text-text-muted">
                      <Minus size={12} />
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-primary-pale/40 p-7">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary">With WEPL</p>
              <ul className="mt-4 space-y-3">
                {WITH_WEPL.map(item => (
                  <li key={item} className="flex items-center gap-3 text-sm font-medium text-text">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-white">
                      <Check size={12} strokeWidth={3} />
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* ── Trust ─────────────────────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-6xl px-6 py-16 lg:py-20">
          <div className="rounded-2xl border border-border bg-surface p-8 lg:p-12">
            <div className="max-w-2xl">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary">
                <ShieldCheck size={15} /> Designed for transparency
              </span>
              <h2 className="mt-4 text-2xl font-bold tracking-tight text-text lg:text-3xl">
                Financial infrastructure, with trust built in.
              </h2>
              <p className="mt-3 text-base text-text-secondary">
                WEPL runs on a double-entry ledger — the same foundation banks use — so every
                shilling is traceable and every balance reconciles.
              </p>
            </div>
            <div className="mt-8 grid gap-x-8 gap-y-4 sm:grid-cols-2">
              {TRUST.map(item => (
                <div key={item} className="flex items-center gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-pale text-primary">
                    <Check size={14} strokeWidth={3} />
                  </span>
                  <span className="text-sm font-medium text-text">{item}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Closing CTA ───────────────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-6xl px-6 pb-20 pt-4">
          <div className="relative overflow-hidden rounded-3xl bg-primary px-8 py-14 text-center lg:py-20">
            <h2 className="mx-auto max-w-2xl text-3xl font-bold tracking-tight text-white lg:text-4xl">
              Bring your community together.
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-base text-white/80">
              Start free. Set up your first community in minutes.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link href="/login?mode=register">
                <Button size="lg" variant="outline" className="w-full border-white bg-white text-primary hover:bg-white/90 sm:w-auto">
                  Create account <ArrowUpRight size={18} />
                </Button>
              </Link>
              <Link href="/login">
                <Button size="lg" variant="ghost" className="w-full text-white hover:bg-white/10 sm:w-auto">
                  Sign in
                </Button>
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-divider">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-6 py-6 text-xs text-text-muted sm:flex-row">
          <span>© {new Date().getFullYear()} WEPL — The operating system for communities</span>
          <span className="inline-flex items-center gap-1.5"><ShieldCheck size={13} /> Audited ledger · Transparent by design</span>
        </div>
      </footer>
    </div>
  )
}

function SectionHeading({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {
  return (
    <div className="max-w-2xl">
      <span className="text-xs font-semibold uppercase tracking-wide text-primary">{eyebrow}</span>
      <h2 className="mt-3 text-2xl font-bold tracking-tight text-text lg:text-3xl">{title}</h2>
      {subtitle && <p className="mt-3 text-base leading-relaxed text-text-secondary">{subtitle}</p>}
    </div>
  )
}

/** A static, credible dashboard preview echoing the app's Communities page,
 *  lifted off the page with a soft glow, layered depth and a slight tilt. */
function ProductPreview() {
  return (
    <div className="relative lg:pl-6">
      {/* Ambient glow */}
      <div aria-hidden className="absolute -inset-6 -z-10 rounded-[2.5rem] bg-primary/10 blur-3xl" />
      {/* Stacked card behind for depth */}
      <div aria-hidden className="absolute inset-0 -z-10 translate-x-3 translate-y-4 rounded-2xl border border-border bg-surface/50 lg:rotate-[2deg]" />

      <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-modal ring-1 ring-black/5 transition-transform duration-500 lg:-rotate-[1.5deg] lg:hover:rotate-0 dark:ring-white/5">
        <div className="flex items-center justify-between border-b border-divider px-4 py-3">
          <span className="text-sm font-bold text-text">Communities</span>
          <span className="inline-flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1 text-xs font-semibold text-white">
            + New
          </span>
        </div>

        <div className="space-y-3 p-4">
          <div className="grid grid-cols-2 gap-3">
            <PreviewStat icon={Wallet} value="KES 3.4M" label="Total managed" />
            <PreviewStat icon={TrendingUp} value="+8.6%" label="Growth this month" />
          </div>

          <PreviewCommunity name="Household Chama" tag="Savings" tone="bg-success/10 text-success" members="48 members" amount="KES 245,000" />
          <PreviewCommunity name="Young Investors" tag="Investment" tone="bg-info/10 text-info" members="36 members" amount="+2.1%" />

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
