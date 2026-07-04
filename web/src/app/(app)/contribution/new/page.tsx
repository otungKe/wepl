'use client'
import { Suspense, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { ArrowLeft, ArrowRight, Infinity as InfinityIcon, CalendarClock, Timer } from 'lucide-react'
import { contributions, communities, apiError, type Community } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Input, Textarea, Select } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { OptionCard, ToggleRow } from '@/components/ui/OptionCard'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from 'sonner'

type Tenure = 'open' | 'date' | 'period'
type Frequency = 'anytime' | 'daily' | 'weekly' | 'monthly'
type AmountType = 'open' | 'fixed'

const STEPS = ['Basics', 'Term & target', 'Schedule', 'Members', 'Governance'] as const

function NewContributionInner() {
  const router = useRouter()
  const forced = useSearchParams().get('community')
  const forcedId = forced ? Number(forced) : null

  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [myCommunities, setMyCommunities] = useState<Community[]>([])

  // Basics
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [communityId, setCommunityId] = useState<number | null>(forcedId)

  // Term & target
  const [tenure, setTenure] = useState<Tenure>('open')
  const [endDate, setEndDate] = useState('')
  const [periodMonths, setPeriodMonths] = useState('')
  const [target, setTarget] = useState('')
  const [memberTarget, setMemberTarget] = useState('')

  // Schedule
  const [frequency, setFrequency] = useState<Frequency>('anytime')
  const [amountType, setAmountType] = useState<AmountType>('open')
  const [fixedAmount, setFixedAmount] = useState('')

  // Members (only when community-scoped)
  const [addAll, setAddAll] = useState(true)

  // Governance
  const [votingThreshold, setVotingThreshold] = useState('admins')
  const [customPct, setCustomPct] = useState('')
  const [useCustomPct, setUseCustomPct] = useState(false)
  const [txVisibility, setTxVisibility] = useState('all')
  const [amendmentProposer, setAmendmentProposer] = useState('creator')
  const [amendmentThreshold, setAmendmentThreshold] = useState('admins')
  const [latePolicy, setLatePolicy] = useState('open')
  const [lateGraceDays, setLateGraceDays] = useState('7')
  const [isCampaign, setIsCampaign] = useState(false)

  useEffect(() => {
    if (forcedId) return
    communities.mine().then(setMyCommunities).catch(() => {})
  }, [forcedId])

  // community is the source of truth; visibility is derived (mirrors mobile).
  const isOpen = communityId == null
  // Members step is only relevant when scoped to a community.
  const steps = useMemo(() => isOpen ? STEPS.filter(s => s !== 'Members') : STEPS, [isOpen])
  const current = steps[step]

  function canAdvance(): boolean {
    if (current === 'Basics') return !!title.trim()
    if (current === 'Term & target') {
      if (tenure === 'date') return !!endDate
      if (tenure === 'period') return !!periodMonths
      return true
    }
    if (current === 'Schedule') return amountType === 'open' || !!fixedAmount.trim()
    return true
  }

  function next() {
    if (!canAdvance()) { toast.error('Please complete the required fields'); return }
    if (step < steps.length - 1) setStep(s => s + 1)
    else create()
  }

  async function create() {
    let threshold = votingThreshold
    if (useCustomPct) {
      const pct = Number(customPct)
      if (!customPct || isNaN(pct) || pct < 1 || pct > 100) { toast.error('Enter a custom percentage between 1 and 100'); return }
      threshold = String(Math.round(pct))
    }
    setSaving(true)
    try {
      const { data: c } = await contributions.create({
        title: title.trim(),
        description: description.trim() || undefined,
        visibility: isOpen ? 'open' : 'closed',
        community: communityId,
        target_amount: target ? Number(target) : null,
        member_target_amount: memberTarget ? Number(memberTarget) : null,
        tenure_type: tenure,
        end_date: tenure === 'date' ? endDate : null,
        period_months: tenure === 'period' ? Number(periodMonths) : null,
        frequency,
        amount_type: amountType,
        fixed_amount: amountType === 'fixed' ? Number(fixedAmount) : null,
        voting_threshold: threshold,
        transaction_visibility: txVisibility,
        amendment_proposer: amendmentProposer,
        amendment_voting_threshold: amendmentThreshold,
        late_contribution_policy: latePolicy,
        late_contribution_grace_days: latePolicy === 'grace' ? Number(lateGraceDays) : 7,
        add_all_members: isOpen ? false : addAll,
        member_phones: [],
        is_campaign: isOpen ? isCampaign : false,
      })
      toast.success('Contribution created')
      router.replace(`/contribution/${c.id}`)
    } catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }

  return (
    <div className="mx-auto max-w-2xl pb-10">
      <PageHeader title="Create a contribution" subtitle={STEPS.includes(current) ? `Step ${step + 1} of ${steps.length} · ${current}` : undefined} back />

      {/* Progress */}
      <div className="mb-6 flex gap-1.5">
        {steps.map((s, i) => (
          <div key={s} className={`h-1.5 flex-1 rounded-full transition-colors ${i <= step ? 'bg-primary' : 'bg-divider'}`} />
        ))}
      </div>

      <div className="flex flex-col gap-4">
        {current === 'Basics' && (
          <>
            <Input label="Title" required value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Monthly savings" autoFocus />
            <Textarea label="Description" value={description} onChange={e => setDescription(e.target.value)} placeholder="What is this pool for?" />
            {!forcedId && (
              <Select label="Community" value={communityId ?? ''} onChange={e => setCommunityId(e.target.value ? Number(e.target.value) : null)}
                hint="Leave as Personal for a standalone, public campaign.">
                <option value="">Personal (standalone)</option>
                {myCommunities.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            )}
          </>
        )}

        {current === 'Term & target' && (
          <>
            <h2 className="text-sm font-semibold text-text">How long does it run?</h2>
            <OptionCard label="Open-ended" desc="No fixed end date" icon={<InfinityIcon size={18} />}
              active={tenure === 'open'} onClick={() => setTenure('open')} />
            <OptionCard label="Until a date" desc="Ends on a specific day" icon={<CalendarClock size={18} />}
              active={tenure === 'date'} onClick={() => setTenure('date')} />
            <OptionCard label="Fixed period" desc="Runs for a number of months" icon={<Timer size={18} />}
              active={tenure === 'period'} onClick={() => setTenure('period')} />
            {tenure === 'date' && (
              <Input label="End date" type="date" required value={endDate} onChange={e => setEndDate(e.target.value)} />
            )}
            {tenure === 'period' && (
              <Input label="Number of months" type="number" inputMode="numeric" required value={periodMonths}
                onChange={e => setPeriodMonths(e.target.value)} placeholder="e.g. 12" />
            )}
            <div className="mt-2 grid gap-4 sm:grid-cols-2">
              <Input label="Pool target (KES)" type="number" inputMode="decimal" value={target}
                onChange={e => setTarget(e.target.value)} placeholder="Optional" hint="Overall goal for the pool" />
              <Input label="Per-member target (KES)" type="number" inputMode="decimal" value={memberTarget}
                onChange={e => setMemberTarget(e.target.value)} placeholder="Optional" hint="Goal for each member" />
            </div>
          </>
        )}

        {current === 'Schedule' && (
          <>
            <h2 className="text-sm font-semibold text-text">How often do members contribute?</h2>
            {([['anytime', 'Anytime', 'Whenever they want'], ['daily', 'Daily', 'Once per day'],
               ['weekly', 'Weekly', 'Once per week'], ['monthly', 'Monthly', 'Once per month']] as [Frequency, string, string][])
              .map(([v, l, d]) => <OptionCard key={v} label={l} desc={d} active={frequency === v} onClick={() => setFrequency(v)} />)}
            <h2 className="mt-3 text-sm font-semibold text-text">Contribution amount per member</h2>
            <OptionCard label="Open amount" desc="Members choose how much to pay" active={amountType === 'open'} onClick={() => setAmountType('open')} />
            <OptionCard label="Fixed amount" desc="Everyone pays the same set amount" active={amountType === 'fixed'} onClick={() => setAmountType('fixed')} />
            {amountType === 'fixed' && (
              <Input label="Fixed amount (KES)" type="number" inputMode="decimal" required value={fixedAmount}
                onChange={e => setFixedAmount(e.target.value)} placeholder="e.g. 1000" />
            )}
          </>
        )}

        {current === 'Members' && (
          <>
            <h2 className="text-sm font-semibold text-text">Who joins this contribution?</h2>
            <ToggleRow label="Add all community members" desc="Everyone in the community is added as a participant"
              checked={addAll} onChange={setAddAll} />
            {!addAll && <p className="text-sm text-text-muted">Only you will be added — members can join the contribution later.</p>}
          </>
        )}

        {current === 'Governance' && (
          <>
            <h2 className="text-sm font-semibold text-text">Who approves payouts &amp; changes?</h2>
            <OptionCard label="Admins only" desc="Admins & treasurers decide" active={!useCustomPct && votingThreshold === 'admins'}
              onClick={() => { setUseCustomPct(false); setVotingThreshold('admins') }} />
            <OptionCard label="50% + 1 majority" desc="A simple majority of members" active={!useCustomPct && votingThreshold === '50'}
              onClick={() => { setUseCustomPct(false); setVotingThreshold('50') }} />
            <OptionCard label="All members" desc="Unanimous approval" active={!useCustomPct && votingThreshold === '100'}
              onClick={() => { setUseCustomPct(false); setVotingThreshold('100') }} />
            <OptionCard label="Custom %" desc="Set your own threshold" active={useCustomPct}
              onClick={() => setUseCustomPct(true)} />
            {useCustomPct && (
              <Input label="Custom threshold (%)" type="number" inputMode="numeric" value={customPct}
                onChange={e => setCustomPct(e.target.value)} placeholder="1–100" />
            )}

            <div className="mt-3 flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5">
              <Select label="Who sees transactions?" value={txVisibility} onChange={e => setTxVisibility(e.target.value)}>
                <option value="all">All members see all</option>
                <option value="own">Members see only their own</option>
                <option value="admins_all">Admins see all, members see own</option>
              </Select>
              <Select label="Who can propose rule changes?" value={amendmentProposer} onChange={e => setAmendmentProposer(e.target.value)}>
                <option value="creator">Creator only</option>
                <option value="admins">Admins & treasurers</option>
                <option value="members">Any member</option>
              </Select>
              <Select label="Amendment approval" value={amendmentThreshold} onChange={e => setAmendmentThreshold(e.target.value)}>
                <option value="admins">Admins only</option>
                <option value="50">50% + 1 majority</option>
                <option value="100">All members</option>
              </Select>
              <Select label="Late contribution policy" value={latePolicy} onChange={e => setLatePolicy(e.target.value)}>
                <option value="open">Always open</option>
                <option value="strict">Strict — none after the end date</option>
                <option value="grace">Grace period after the end date</option>
              </Select>
              {latePolicy === 'grace' && (
                <Input label="Grace period (days)" type="number" inputMode="numeric" value={lateGraceDays}
                  onChange={e => setLateGraceDays(e.target.value)} placeholder="7" />
              )}
            </div>

            {isOpen && (
              <ToggleRow label="Public campaign" desc="Feature this open contribution for anyone to support"
                checked={isCampaign} onChange={setIsCampaign} />
            )}
          </>
        )}
      </div>

      {/* Nav */}
      <div className="mt-8 flex gap-3">
        {step > 0
          ? <Button variant="outline" onClick={() => setStep(s => s - 1)} className="flex-1"><ArrowLeft size={16} /> Back</Button>
          : <Button variant="outline" onClick={() => router.back()} className="flex-1">Cancel</Button>}
        <Button onClick={next} loading={saving} disabled={!canAdvance()} className="flex-[2]">
          {step < steps.length - 1 ? <>Continue <ArrowRight size={16} /></> : 'Create contribution'}
        </Button>
      </div>
    </div>
  )
}

export default function NewContributionPage() {
  return (
    <Suspense fallback={<PageLoader />}>
      <NewContributionInner />
    </Suspense>
  )
}
