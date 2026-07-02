import { ArrowUpCircle, ArrowDownCircle, Zap, CheckCircle2, type LucideIcon } from 'lucide-react'

export type TxType = 'CONTRIBUTION' | 'WITHDRAWAL' | 'ADVANCE' | 'REPAYMENT'

// `inflow` = money moving *to* the user (shown green, with a "+"); outflow is
// money leaving the user (shown in default text, with a "-").
export const TX_META: Record<TxType, { label: string; icon: LucideIcon; inflow: boolean }> = {
  CONTRIBUTION: { label: 'Contribution', icon: ArrowUpCircle,   inflow: false },
  WITHDRAWAL:   { label: 'Withdrawal',   icon: ArrowDownCircle, inflow: true },
  ADVANCE:      { label: 'Advance',      icon: Zap,             inflow: true },
  REPAYMENT:    { label: 'Repayment',    icon: CheckCircle2,    inflow: false },
}

export function txMeta(type: string) {
  return TX_META[type as TxType] ?? { label: type, icon: ArrowUpCircle, inflow: false }
}

export const TX_FILTERS: { key: string; label: string }[] = [
  { key: 'all',          label: 'All' },
  { key: 'CONTRIBUTION', label: 'Contributions' },
  { key: 'WITHDRAWAL',   label: 'Withdrawals' },
  { key: 'ADVANCE',      label: 'Advances' },
  { key: 'REPAYMENT',    label: 'Repayments' },
]
