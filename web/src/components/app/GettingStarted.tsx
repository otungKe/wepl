'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Check, Clock, X, ArrowRight, UserRound, Users, ShieldCheck, Wallet } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * First-run "Getting started" checklist. Every step is derived from real account
 * state the Communities page already loads — no fabricated progress. Hidden once
 * complete, or when the user dismisses it (persisted per-device).
 */
const DISMISS_KEY = 'wepl.onboardingDismissed'

type StepState = 'done' | 'pending' | 'todo'

interface GettingStartedProps {
  userName?: string | null
  communitiesCount: number
  kycStatus?: 'approved' | 'pending' | 'rejected' | 'not_submitted' | null
  txCount: number
  onCreateCommunity: () => void
}

export function GettingStarted({ userName, communitiesCount, kycStatus, txCount, onCreateCommunity }: GettingStartedProps) {
  const [dismissed, setDismissed] = useState(true) // default hidden until we read storage (avoids flash)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    try { setDismissed(localStorage.getItem(DISMISS_KEY) === '1') } catch { setDismissed(false) }
  }, [])

  const nameDone = !!(userName && userName.trim())
  const communityDone = communitiesCount > 0
  const kycState: StepState = kycStatus === 'approved' ? 'done' : kycStatus === 'pending' ? 'pending' : 'todo'
  const contributionDone = txCount > 0

  const steps: { key: string; label: string; hint: string; icon: typeof Users; state: StepState; href?: string; onClick?: () => void }[] = [
    { key: 'name', label: 'Add your name', hint: 'So members recognise you', icon: UserRound, state: nameDone ? 'done' : 'todo', href: '/profile' },
    { key: 'community', label: 'Create or join a community', hint: 'Your groups live here', icon: Users, state: communityDone ? 'done' : 'todo', onClick: onCreateCommunity },
    { key: 'kyc', label: 'Verify your identity', hint: 'Unlock payments and payouts', icon: ShieldCheck, state: kycState, href: '/kyc' },
    { key: 'contribution', label: 'Make your first contribution', hint: 'Pay into a pool', icon: Wallet, state: contributionDone ? 'done' : 'todo', href: '/contributions' },
  ]

  const doneCount = steps.filter(s => s.state === 'done').length
  const total = steps.length
  const complete = doneCount === total

  // Animate the progress bar on mount.
  useEffect(() => {
    const t = setTimeout(() => setProgress(Math.round((doneCount / total) * 100)), 80)
    return () => clearTimeout(t)
  }, [doneCount, total])

  if (dismissed || complete) return null

  function dismiss() {
    try { localStorage.setItem(DISMISS_KEY, '1') } catch { /* ignore */ }
    setDismissed(true)
  }

  const firstName = (userName || '').trim().split(' ')[0]

  return (
    <div className="mb-5 overflow-hidden rounded-2xl border border-border bg-surface">
      <div className="flex items-start justify-between gap-3 border-b border-divider px-5 py-4">
        <div>
          <p className="text-base font-semibold text-text">
            {firstName ? `Welcome, ${firstName} 👋` : 'Welcome to WEPL 👋'}
          </p>
          <p className="mt-0.5 text-sm text-text-muted">A few quick steps to set up your account.</p>
        </div>
        <button
          onClick={dismiss}
          aria-label="Dismiss getting started"
          className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-divider hover:text-text"
        >
          <X size={16} />
        </button>
      </div>

      {/* Progress */}
      <div className="px-5 pt-4">
        <div className="flex items-center justify-between text-xs font-medium text-text-muted">
          <span>{doneCount} of {total} complete</span>
          <span>{Math.round((doneCount / total) * 100)}%</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-divider">
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Steps */}
      <div className="grid gap-2 p-4 sm:grid-cols-2">
        {steps.map(({ key, ...s }) => <Step key={key} {...s} />)}
      </div>
    </div>
  )
}

function Step({ label, hint, icon: Icon, state, href, onClick }:
  { label: string; hint: string; icon: typeof Users; state: StepState; href?: string; onClick?: () => void }) {
  const inner = (
    <>
      <StepMark state={state} icon={Icon} />
      <div className="min-w-0 flex-1">
        <p className={cn('truncate text-sm font-medium', state === 'done' ? 'text-text-muted line-through' : 'text-text')}>{label}</p>
        <p className="truncate text-xs text-text-muted">{state === 'pending' ? 'Under review' : hint}</p>
      </div>
      {state !== 'done' && state !== 'pending' && (
        <ArrowRight size={15} className="shrink-0 text-text-muted transition-transform group-hover:translate-x-0.5" />
      )}
    </>
  )
  const cls = cn(
    'group flex items-center gap-3 rounded-xl border border-border bg-primary-bg/40 px-3.5 py-3 transition-all duration-200',
    state === 'todo' && 'hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-card',
  )
  if (state === 'done' || state === 'pending') return <div className={cls}>{inner}</div>
  if (onClick) return <button type="button" onClick={onClick} className={cn(cls, 'w-full text-left')}>{inner}</button>
  return <Link href={href || '#'} className={cls}>{inner}</Link>
}

function StepMark({ state, icon: Icon }: { state: StepState; icon: typeof Users }) {
  if (state === 'done') {
    return <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-white"><Check size={16} strokeWidth={3} /></span>
  }
  if (state === 'pending') {
    return <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-pale text-accent"><Clock size={16} /></span>
  }
  return <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-pale text-primary"><Icon size={16} /></span>
}
