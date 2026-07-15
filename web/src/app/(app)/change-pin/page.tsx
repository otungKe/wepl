'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { KeyRound, ArrowRight } from 'lucide-react'
import { auth, apiError } from '@/lib/api'
import { saveTokens } from '@/lib/auth'
import { useAuthStore } from '@/store/auth'
import { PageHeader } from '@/components/app/PageHeader'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { toast } from 'sonner'

type Step = 'current' | 'new' | 'otp'

const STEP_COPY: Record<Step, { title: string; hint: string }> = {
  current: { title: 'Confirm your current PIN', hint: 'For your security, confirm the PIN you use today.' },
  new:     { title: 'Choose a new PIN', hint: 'Pick a new 6-digit PIN and confirm it.' },
  otp:     { title: 'Verify it’s you', hint: 'Enter the 6-digit code we sent to your phone to finish.' },
}

export default function ChangePinPage() {
  const router = useRouter()
  const phone = useAuthStore(s => s.user?.phone_number ?? '')

  const [step, setStep] = useState<Step>('current')
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [otp, setOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const digits = (v: string) => v.replace(/\D/g, '')

  // Step 1 — verify the current PIN (login rotates to a fresh valid session).
  async function verifyCurrent(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (current.length !== 6) { setError('Enter your 6-digit PIN'); return }
    setLoading(true)
    try {
      const { data } = await auth.login(phone, current)
      saveTokens(data.access, data.refresh)
      setStep('new')
    } catch (err) {
      setError(apiError(err, 'That PIN is incorrect.'))
    } finally {
      setLoading(false)
    }
  }

  // Step 2 — choose the new PIN, then send an OTP to authorise the change.
  async function chooseNew(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (next.length !== 6) { setError('New PIN must be 6 digits'); return }
    if (next !== confirm) { setError('PINs do not match'); return }
    if (next === current) { setError('New PIN must be different from the current one'); return }
    setLoading(true)
    try {
      await auth.requestOtp(phone)
      setOtp('')
      setStep('otp')
    } catch (err) {
      setError(apiError(err, 'Could not send a verification code.'))
    } finally {
      setLoading(false)
    }
  }

  // Step 3 — verify OTP (yields a recovery token), set the new PIN, then re-login.
  async function verifyAndSet(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (otp.length !== 6) { setError('Enter the 6-digit code'); return }
    setLoading(true)
    try {
      const { data } = await auth.verifyOtp(phone, otp)
      saveTokens(data.access, data.refresh)
      await auth.resetPin(next)
      // Re-login with the new PIN to restore a normal active session.
      try {
        const relog = await auth.login(phone, next)
        saveTokens(relog.data.access, relog.data.refresh)
      } catch { /* non-fatal: recovery session still works */ }
      toast.success('PIN changed')
      router.push('/settings')
    } catch (err) {
      setError(apiError(err, 'Verification failed. Check the code and try again.'))
    } finally {
      setLoading(false)
    }
  }

  const copy = STEP_COPY[step]

  return (
    <div className="mx-auto max-w-md">
      <PageHeader title="Change PIN" back="/settings" />

      {/* Step indicator */}
      <div className="mb-5 flex items-center gap-2">
        {(['current', 'new', 'otp'] as Step[]).map((s, i) => {
          const order = ['current', 'new', 'otp']
          const done = order.indexOf(step) > i
          const active = step === s
          return (
            <div key={s} className="flex flex-1 items-center gap-2">
              <div className={`h-1.5 flex-1 rounded-full ${done || active ? 'bg-primary' : 'bg-divider'}`} />
            </div>
          )
        })}
      </div>

      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <KeyRound size={18} />
          </div>
          <div>
            <p className="font-semibold text-text">{copy.title}</p>
            <p className="text-sm text-text-muted">{copy.hint}</p>
          </div>
        </div>

        {step === 'current' && (
          <form onSubmit={verifyCurrent} className="flex flex-col gap-4">
            <Input label="Current PIN" type="password" inputMode="numeric" maxLength={6} autoFocus
              value={current} onChange={e => setCurrent(digits(e.target.value))} error={error} />
            <Button type="submit" loading={loading} fullWidth>Continue <ArrowRight size={16} /></Button>
          </form>
        )}

        {step === 'new' && (
          <form onSubmit={chooseNew} className="flex flex-col gap-4">
            <Input label="New PIN" type="password" inputMode="numeric" maxLength={6} autoFocus
              value={next} onChange={e => setNext(digits(e.target.value))} />
            <Input label="Confirm new PIN" type="password" inputMode="numeric" maxLength={6}
              value={confirm} onChange={e => setConfirm(digits(e.target.value))} error={error} />
            <Button type="submit" loading={loading} fullWidth>Send code <ArrowRight size={16} /></Button>
          </form>
        )}

        {step === 'otp' && (
          <form onSubmit={verifyAndSet} className="flex flex-col gap-4">
            <Input label="Verification code" inputMode="numeric" maxLength={6} autoFocus
              value={otp} onChange={e => setOtp(digits(e.target.value))} error={error}
              hint={`Sent to ${phone || 'your phone'}.`} />
            <Button type="submit" loading={loading} fullWidth>Change PIN</Button>
          </form>
        )}
      </div>
    </div>
  )
}
