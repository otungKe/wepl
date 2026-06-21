'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { AuthShell } from '@/components/app/AuthShell'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { auth, apiError } from '@/lib/api'
import { saveTokens } from '@/lib/auth'
import { toast } from 'sonner'

function normalizePhone(raw: string): string {
  const d = raw.replace(/\D/g, '')
  if (d.startsWith('0')) return '254' + d.slice(1)
  if (d.startsWith('7') || d.startsWith('1')) return '254' + d
  return d
}

export default function ForgotPinPage() {
  const router = useRouter()
  const [step, setStep] = useState<'phone' | 'otp' | 'pin'>('phone')
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [pin, setPin] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function requestOtp(e: React.FormEvent) {
    e.preventDefault(); setError('')
    const p = normalizePhone(phone)
    if (!/^2547\d{8}$/.test(p)) { setError('Enter a valid Kenyan phone number'); return }
    setLoading(true)
    try { await auth.requestOtp(p); setStep('otp') } catch (err) { setError(apiError(err)) } finally { setLoading(false) }
  }
  async function verifyOtp(e: React.FormEvent) {
    e.preventDefault(); setError('')
    setLoading(true)
    try { const { data } = await auth.verifyOtp(normalizePhone(phone), otp); saveTokens(data.access, data.refresh); setStep('pin') }
    catch (err) { setError(apiError(err, 'Invalid OTP')) } finally { setLoading(false) }
  }
  async function resetPin(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (pin.length !== 6) { setError('PIN must be 6 digits'); return }
    if (pin !== confirm) { setError('PINs do not match'); return }
    setLoading(true)
    try { await auth.resetPin(pin); toast.success('PIN reset. Please sign in.'); router.push('/login') }
    catch (err) { setError(apiError(err, 'Failed to reset PIN')) } finally { setLoading(false) }
  }

  return (
    <AuthShell title="Reset your PIN"
      subtitle={step === 'phone' ? 'We’ll send a verification code to your number.' : step === 'otp' ? 'Enter the code we sent you.' : 'Choose a new 6-digit PIN.'}
      onBack={() => router.push('/login')} backLabel="Back to sign in">
      {step === 'phone' && (
        <form onSubmit={requestOtp} className="flex flex-col gap-5">
          <Input label="Phone number" type="tel" value={phone} onChange={e => setPhone(e.target.value)} error={error} autoFocus />
          <Button type="submit" size="lg" loading={loading} fullWidth>Send code</Button>
        </form>
      )}
      {step === 'otp' && (
        <form onSubmit={verifyOtp} className="flex flex-col gap-5">
          <Input label="Verification code" inputMode="numeric" maxLength={6} value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, ''))} error={error} autoFocus />
          <Button type="submit" size="lg" loading={loading} fullWidth>Verify</Button>
        </form>
      )}
      {step === 'pin' && (
        <form onSubmit={resetPin} className="flex flex-col gap-5">
          <Input label="New PIN" type="password" inputMode="numeric" maxLength={6} value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} autoFocus />
          <Input label="Confirm new PIN" type="password" inputMode="numeric" maxLength={6} value={confirm} onChange={e => setConfirm(e.target.value.replace(/\D/g, ''))} error={error} />
          <Button type="submit" size="lg" loading={loading} fullWidth>Reset PIN</Button>
        </form>
      )}
    </AuthShell>
  )
}
