'use client'
import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { AuthShell } from '@/components/app/AuthShell'
import { auth, apiError } from '@/lib/api'
import { saveTokens } from '@/lib/auth'
import { useAuthStore } from '@/store/auth'
import { cn, landingPath } from '@/lib/utils'
import { Delete } from 'lucide-react'

const LEN = 6

function PinForm() {
  const router = useRouter()
  const isReset = useSearchParams().get('mode') === 'reset'
  const [pin, setPin] = useState('')
  const [confirm, setConfirm] = useState('')
  const [step, setStep] = useState<'enter' | 'confirm'>('enter')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const current = step === 'enter' ? pin : confirm

  function press(d: string) {
    if (step === 'enter') {
      if (pin.length >= LEN) return
      const next = pin + d; setPin(next)
      if (next.length === LEN) setStep('confirm')
    } else {
      if (confirm.length >= LEN) return
      const next = confirm + d; setConfirm(next)
      if (next.length === LEN) submit(pin, next)
    }
  }
  function back() { step === 'enter' ? setPin(p => p.slice(0, -1)) : (setConfirm(''), setError('')) }

  async function submit(p: string, c: string) {
    if (p !== c) { setError('PINs do not match. Try again.'); setConfirm(''); return }
    setLoading(true)
    try {
      const { data } = isReset ? await auth.resetPin(p) : await auth.setPin(p)
      saveTokens(data.access, data.refresh)
      const profile = await auth.profile()
      useAuthStore.getState().login(data.access, data.refresh, profile.data)
      // New account → capture a display name (mirrors mobile). Reset → straight in.
      router.replace(isReset || profile.data.name ? landingPath(profile.data.kyc_status) : '/display-name')
    } catch (err) {
      setError(apiError(err, isReset ? 'Failed to reset PIN.' : 'Failed to set PIN.'))
      setPin(''); setConfirm(''); setStep('enter')
    } finally { setLoading(false) }
  }

  const enterTitle = isReset ? 'Choose a new PIN' : 'Create your PIN'
  const enterSub = isReset ? 'Enter a new 6-digit PIN for your account.' : 'Choose a 6-digit PIN to secure your account.'

  return (
    <AuthShell title={step === 'enter' ? enterTitle : 'Confirm your PIN'}
      subtitle={step === 'enter' ? enterSub : 'Enter your PIN again to confirm.'}>
      <div className="mb-8 flex justify-center gap-3">
        {Array.from({ length: LEN }).map((_, i) => (
          <div key={i} className={cn('h-3.5 w-3.5 rounded-full border-2 transition-colors',
            i < current.length ? 'border-primary bg-primary' : 'border-border bg-transparent')} />
        ))}
      </div>
      {error && <p className="mb-4 text-center text-sm text-error">{error}</p>}
      <div className="mx-auto grid max-w-[260px] grid-cols-3 gap-3">
        {['1','2','3','4','5','6','7','8','9','','0','del'].map((k, i) => {
          if (!k) return <div key={i} />
          return (
            <button key={k} onClick={() => k === 'del' ? back() : press(k)} disabled={loading}
              className="flex h-16 items-center justify-center rounded-xl border border-border bg-surface text-xl font-semibold text-text transition-colors hover:bg-primary-pale hover:text-primary disabled:opacity-50">
              {k === 'del' ? <Delete size={20} /> : k}
            </button>
          )
        })}
      </div>
      {loading && <p className="mt-5 text-center text-sm text-text-muted">{isReset ? 'Resetting your PIN…' : 'Setting up your account…'}</p>}
    </AuthShell>
  )
}

export default function PinPage() {
  return <Suspense><PinForm /></Suspense>
}
