'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { auth } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { toast } from 'sonner'

const PIN_LENGTH = 6

export default function PinPage() {
  const router = useRouter()
  const { pendingPhone } = useAuthStore()
  const [pin, setPin]       = useState('')
  const [confirm, setConfirm] = useState('')
  const [step, setStep]     = useState<'enter' | 'confirm'>('enter')
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState('')

  function addDigit(d: string) {
    if (step === 'enter') {
      if (pin.length >= PIN_LENGTH) return
      const next = pin + d
      setPin(next)
      if (next.length === PIN_LENGTH) setStep('confirm')
    } else {
      if (confirm.length >= PIN_LENGTH) return
      const next = confirm + d
      setConfirm(next)
      if (next.length === PIN_LENGTH) handleCreate(pin, next)
    }
  }

  function backspace() {
    if (step === 'enter') setPin(p => p.slice(0, -1))
    else { setConfirm(''); setError('') }
  }

  async function handleCreate(p: string, c: string) {
    if (p !== c) { setError('PINs do not match. Try again.'); setConfirm(''); return }
    setLoading(true)
    try {
      await auth.setPin(p)
      const profile = await auth.profile()
      useAuthStore.getState().login(
        localStorage.getItem('access_token') ?? '',
        localStorage.getItem('refresh_token') ?? '',
        profile.data
      )
      router.push('/communities')
    } catch {
      toast.error('Failed to set PIN. Please try again.')
      setPin(''); setConfirm(''); setStep('enter')
    } finally {
      setLoading(false)
    }
  }

  const current = step === 'enter' ? pin : confirm

  return (
    <div className="min-h-screen flex items-center justify-center bg-primary-bg px-4">
      <div className="w-full max-w-xs text-center">
        <h1 className="text-2xl font-bold mb-2">
          {step === 'enter' ? 'Create your PIN' : 'Confirm your PIN'}
        </h1>
        <p className="text-text-secondary mb-10 text-sm">
          {step === 'enter'
            ? 'Choose a 6-digit PIN to secure your account.'
            : 'Enter your PIN again to confirm.'}
        </p>

        {/* Dots */}
        <div className="flex justify-center gap-4 mb-10">
          {Array.from({ length: PIN_LENGTH }).map((_, i) => (
            <div
              key={i}
              className={cn(
                'w-4 h-4 rounded-full border-2 transition-all',
                i < current.length
                  ? 'bg-primary border-primary'
                  : 'bg-transparent border-border'
              )}
            />
          ))}
        </div>

        {error && <p className="text-sm text-error mb-4">{error}</p>}

        {/* Keypad */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          {['1','2','3','4','5','6','7','8','9','','0','⌫'].map((key, idx) => {
            if (!key) return <div key={idx} />
            return (
              <button
                key={key}
                onClick={() => key === '⌫' ? backspace() : addDigit(key)}
                className={cn(
                  'h-16 rounded-xl text-xl font-semibold transition-colors',
                  key === '⌫'
                    ? 'text-text-secondary bg-white border border-border hover:bg-divider'
                    : 'bg-white border border-border hover:bg-primary-pale hover:text-primary active:bg-primary-pale'
                )}
              >
                {key}
              </button>
            )
          })}
        </div>

        {loading && <p className="text-sm text-text-muted">Setting up your account…</p>}
      </div>
    </div>
  )
}
