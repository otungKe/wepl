'use client'
import { useRef, useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AuthShell } from '@/components/app/AuthShell'
import { Button } from '@/components/ui/Button'
import { auth, apiError } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { getStage, saveTokens } from '@/lib/auth'
import { toast } from 'sonner'
import { cn, landingPath } from '@/lib/utils'

const LEN = 6

export default function OtpPage() {
  const router = useRouter()
  const { pendingPhone, setPendingPhone } = useAuthStore()
  const [digits, setDigits] = useState<string[]>(Array(LEN).fill(''))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [resendIn, setResendIn] = useState(60)
  const refs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => { if (!pendingPhone) router.replace('/login?mode=register') }, [pendingPhone, router])
  useEffect(() => { if (resendIn <= 0) return; const t = setTimeout(() => setResendIn(n => n - 1), 1000); return () => clearTimeout(t) }, [resendIn])

  function setDigit(i: number, v: string) {
    const d = v.replace(/\D/g, '').slice(-1)
    const next = [...digits]; next[i] = d; setDigits(next)
    if (d && i < LEN - 1) refs.current[i + 1]?.focus()
  }
  function onPaste(e: React.ClipboardEvent) {
    e.preventDefault()
    const t = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, LEN)
    const next = Array(LEN).fill(''); t.split('').forEach((c, i) => next[i] = c); setDigits(next)
    refs.current[Math.min(t.length, LEN - 1)]?.focus()
  }

  async function verify() {
    const otp = digits.join('')
    if (otp.length !== LEN) { setError('Enter the full 6-digit code'); return }
    setLoading(true); setError('')
    try {
      const { data } = await auth.verifyOtp(pendingPhone, otp)
      saveTokens(data.access, data.refresh)
      const stage = getStage(data.access)
      if (stage === 'active') {
        const profile = await auth.profile()
        useAuthStore.getState().login(data.access, data.refresh, profile.data)
        router.push(landingPath(profile.data.kyc_status))
      } else if (stage === 'otp_recovery') {
        // Existing account verifying via OTP — go set a *new* PIN (reset), not create one.
        router.push('/pin?mode=reset')
      } else {
        router.push('/pin')
      }
    } catch (err) { setError(apiError(err, 'Invalid or expired code.')) } finally { setLoading(false) }
  }

  async function resend() {
    try { await auth.requestOtp(pendingPhone); setResendIn(60); setDigits(Array(LEN).fill('')); toast.success('New code sent') }
    catch (err) { toast.error(apiError(err, 'Failed to resend code')) }
  }

  return (
    <AuthShell title="Verify your number" subtitle={`Enter the 6-digit code sent to ${pendingPhone}`}
      onBack={() => { setPendingPhone(''); router.push('/login?mode=register') }}>
      <div className="flex gap-2.5" onPaste={onPaste}>
        {digits.map((d, i) => (
          <input key={i} ref={el => { refs.current[i] = el }} type="text" inputMode="numeric" maxLength={1} value={d}
            onChange={e => setDigit(i, e.target.value)}
            onKeyDown={e => { if (e.key === 'Backspace' && !digits[i] && i > 0) refs.current[i - 1]?.focus() }}
            className={cn('h-14 w-full rounded-lg border bg-surface text-center text-xl font-semibold focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20',
              error ? 'border-error' : 'border-border')} />
        ))}
      </div>
      {error && <p className="mt-3 text-sm text-error">{error}</p>}
      <Button onClick={verify} size="lg" loading={loading} fullWidth className="mt-5">Verify</Button>
      <p className="mt-4 text-center text-sm text-text-secondary">
        {resendIn > 0 ? `Resend code in ${resendIn}s` : <button onClick={resend} className="font-semibold text-primary">Resend code</button>}
      </p>
    </AuthShell>
  )
}
