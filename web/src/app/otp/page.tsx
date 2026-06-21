'use client'
import { useRef, useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/Button'
import { ArrowLeft } from 'lucide-react'
import { auth } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { getStage } from '@/lib/auth'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

const OTP_LENGTH = 6

export default function OtpPage() {
  const router = useRouter()
  const { pendingPhone, setPendingPhone } = useAuthStore()
  const [digits, setDigits]   = useState<string[]>(Array(OTP_LENGTH).fill(''))
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [resendIn, setResendIn] = useState(60)
  const refs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (!pendingPhone) router.replace('/')
  }, [pendingPhone, router])

  // Countdown timer
  useEffect(() => {
    if (resendIn <= 0) return
    const t = setTimeout(() => setResendIn(n => n - 1), 1000)
    return () => clearTimeout(t)
  }, [resendIn])

  function handleDigit(i: number, val: string) {
    const d = val.replace(/\D/g, '').slice(-1)
    const next = [...digits]
    next[i] = d
    setDigits(next)
    if (d && i < OTP_LENGTH - 1) refs.current[i + 1]?.focus()
  }

  function handleKey(i: number, e: React.KeyboardEvent) {
    if (e.key === 'Backspace' && !digits[i] && i > 0) refs.current[i - 1]?.focus()
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault()
    const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_LENGTH)
    const next = Array(OTP_LENGTH).fill('')
    text.split('').forEach((c, i) => { next[i] = c })
    setDigits(next)
    refs.current[Math.min(text.length, OTP_LENGTH - 1)]?.focus()
  }

  async function handleVerify() {
    const otp = digits.join('')
    if (otp.length !== OTP_LENGTH) { setError('Enter the full 6-digit code'); return }
    setLoading(true); setError('')
    try {
      const { data } = await auth.verifyOtp(pendingPhone, otp)
      const stage = getStage(data.access)
      if (stage === 'otp_verified') {
        router.push('/pin')
      } else if (stage === 'active') {
        const profile = await auth.profile()
        useAuthStore.getState().login(data.access, data.refresh, profile.data)
        router.push('/communities')
      }
    } catch {
      setError('Invalid or expired code. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function resend() {
    try {
      await auth.requestOtp(pendingPhone)
      setResendIn(60)
      setDigits(Array(OTP_LENGTH).fill(''))
      toast.success('New code sent')
    } catch {
      toast.error('Failed to resend code')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-primary-bg px-4">
      <div className="w-full max-w-sm">
        <button
          onClick={() => { setPendingPhone(''); router.push('/login?mode=register') }}
          className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text mb-8"
        >
          <ArrowLeft size={16} /> Back
        </button>

        <h1 className="text-2xl font-bold mb-2">Enter verification code</h1>
        <p className="text-text-secondary mb-8">
          We sent a 6-digit code to <span className="font-medium text-text">{pendingPhone}</span>
        </p>

        {/* OTP boxes */}
        <div className="flex gap-3 mb-6" onPaste={handlePaste}>
          {digits.map((d, i) => (
            <input
              key={i}
              ref={el => { refs.current[i] = el }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={d}
              onChange={e => handleDigit(i, e.target.value)}
              onKeyDown={e => handleKey(i, e)}
              className={cn(
                'w-12 h-14 text-center text-xl font-semibold border rounded-lg bg-white',
                'focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30',
                error ? 'border-error' : 'border-border'
              )}
            />
          ))}
        </div>

        {error && <p className="text-sm text-error mb-4">{error}</p>}

        <Button onClick={handleVerify} loading={loading} size="lg" className="w-full mb-4">
          Verify
        </Button>

        <p className="text-center text-sm text-text-secondary">
          {resendIn > 0
            ? <>Resend code in {resendIn}s</>
            : <button onClick={resend} className="text-primary font-medium">Resend code</button>
          }
        </p>
      </div>
    </div>
  )
}
