import Link from 'next/link'
import { Clock, Coins, Users, ShieldCheck } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Badge, statusTone } from '@/components/ui/Badge'
import { formatMoney, cn } from '@/lib/utils'
import type { Contribution } from '@/lib/api'

const FREQ_LABEL: Record<string, string> = {
  daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly', anytime: 'Anytime',
}

function Pill({ icon: Icon, children }: { icon: typeof Clock; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary-pale px-2 py-0.5 text-xs font-medium text-primary">
      <Icon size={12} /> {children}
    </span>
  )
}

/**
 * Contribution pool card — mirrors the mobile ContributionCard (badge row →
 * title → amount → progress → footer). Reused by the contributions list (UX-04)
 * and community detail (UX-08).
 */
export function ContributionCard({ c }: { c: Contribution }) {
  const cur = Number(c.current_amount)
  const tgt = c.target_amount ? Number(c.target_amount) : 0
  const pct = tgt > 0 ? Math.min((cur / tgt) * 100, 100) : 0
  const amountLabel = c.amount_type === 'fixed' && c.fixed_amount
    ? `${formatMoney(c.fixed_amount)} fixed`
    : 'Open amount'

  return (
    <Link href={`/contribution/${c.id}`} className="block">
      <Card hoverable className="p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill icon={Clock}>{FREQ_LABEL[c.frequency] ?? c.frequency}</Pill>
            <Pill icon={Coins}>{amountLabel}</Pill>
          </div>
          {c.status !== 'active' && (
            <Badge tone={statusTone(c.status)}>{c.status}</Badge>
          )}
        </div>

        <p className="truncate font-semibold text-text">{c.title}</p>
        <p className="mt-0.5 text-2xl font-bold tabular-nums text-text">{formatMoney(cur)}</p>

        {tgt > 0 && (
          <div className="mt-3">
            <div className="h-1.5 overflow-hidden rounded-full bg-divider">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-1 text-xs text-text-muted">{pct.toFixed(0)}% of {formatMoney(tgt)}</p>
          </div>
        )}

        <div className="mt-3 flex items-center gap-1.5 text-xs text-text-muted">
          <Users size={13} />
          <span>{c.participant_count} {c.participant_count === 1 ? 'member' : 'members'}</span>
          <span className={cn('mx-1 h-1 w-1 rounded-full bg-text-muted')} />
          <ShieldCheck size={13} />
          <span className="truncate">{c.voting_label}</span>
        </div>
      </Card>
    </Link>
  )
}
