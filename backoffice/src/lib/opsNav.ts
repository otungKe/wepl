// Back Office navigation tree. Each item is gated by a capability; the sidebar
// renders only what the operator can see. Slugs map to /admin/<slug> routes —
// unbuilt modules fall through to the "in build" placeholder, so the IA is
// complete from day one even as modules land phase by phase.
import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard, Banknote, ArrowLeftRight, Users2, ShieldCheck, Siren,
  LifeBuoy, BookOpen, Scale, Landmark, CheckSquare, RefreshCw, BarChart3,
  ScrollText, HeartPulse, SlidersHorizontal, TerminalSquare, Building2,
} from 'lucide-react'

export interface NavItem {
  label: string
  slug: string
  cap: string
  icon: LucideIcon
  phase?: string   // shown on the placeholder until the module ships
}

export interface NavGroup {
  group: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    group: 'Overview',
    items: [
      { label: 'Dashboard', slug: '', cap: 'dashboard.view', icon: LayoutDashboard },
    ],
  },
  {
    group: 'Operations',
    items: [
      { label: 'Financial Operations', slug: 'finops', cap: 'finops.view', icon: Banknote, phase: 'P2' },
      { label: 'Transactions', slug: 'transactions', cap: 'transactions.view', icon: ArrowLeftRight, phase: 'P2' },
      { label: 'Communities', slug: 'communities', cap: 'communities.view', icon: Building2 },
      { label: 'Users', slug: 'users', cap: 'users.view', icon: Users2 },
    ],
  },
  {
    group: 'Trust & Safety',
    items: [
      { label: 'Verification Centre', slug: 'verification', cap: 'verification.view', icon: ShieldCheck },
      { label: 'Risk & Compliance', slug: 'risk', cap: 'risk.view', icon: Siren, phase: 'P4' },
      { label: 'Support', slug: 'support', cap: 'support.view', icon: LifeBuoy, phase: 'P1' },
    ],
  },
  {
    group: 'Finance',
    items: [
      { label: 'Ledger', slug: 'ledger', cap: 'ledger.view', icon: BookOpen, phase: 'P3' },
      { label: 'Reconciliation', slug: 'reconciliation', cap: 'reconciliation.view', icon: RefreshCw, phase: 'P3' },
      { label: 'Treasury', slug: 'treasury', cap: 'treasury.view', icon: Landmark, phase: 'P3' },
      { label: 'Approvals', slug: 'approvals', cap: 'approvals.view', icon: CheckSquare, phase: 'P2' },
    ],
  },
  {
    group: 'Insight',
    items: [
      { label: 'Reporting', slug: 'reporting', cap: 'reporting.view', icon: BarChart3, phase: 'P4' },
      { label: 'Audit', slug: 'audit', cap: 'audit.view', icon: ScrollText },
    ],
  },
  {
    group: 'Platform',
    items: [
      { label: 'System Health', slug: 'health', cap: 'health.view', icon: HeartPulse, phase: 'P4' },
      { label: 'Configuration', slug: 'config', cap: 'config.view', icon: SlidersHorizontal, phase: 'P4' },
      { label: 'Developer Tools', slug: 'devtools', cap: 'devtools.view', icon: TerminalSquare, phase: 'P4' },
    ],
  },
]

// Flat lookup for the placeholder page: slug -> item.
export const NAV_BY_SLUG: Record<string, NavItem> = Object.fromEntries(
  NAV.flatMap((g) => g.items).map((i) => [i.slug, i]),
)

const ROLE_LABELS: Record<string, string> = {
  super_admin: 'Platform Super Admin', finance: 'Finance', treasury: 'Treasury',
  operations: 'Operations', support: 'Customer Support', compliance: 'Compliance',
  risk: 'Risk / Fraud Ops', verification: 'Verification Officer', auditor: 'Internal Auditor',
  analyst: 'Read-only Analyst', developer: 'Developer',
}
export const roleLabel = (slug: string) => ROLE_LABELS[slug] ?? slug
