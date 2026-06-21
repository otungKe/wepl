'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ArrowLeft } from 'lucide-react'
import { auth } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { toast } from 'sonner'

type Step = 'phone' | 'otp' | 'pin'

export default function ForgotPinPage() {
  const router    = useRouter()
  const { setPendingPhone } = useAuthStore()
  const [step, setStep]     = useState<Step>('phone')
  const [phone, setPhone]   = useState('')
  const [otp, setOtp]       = useState('')
  const [pin, setPin]       = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)

  async function requestOtp(e: React.FormEvent) {
    e.preventDefault(); setLoading(true)
    try {
      await auth.requestOtp(phone)
      setPendingPhone(phone)
      setStep('otp')
    } catch { toast.error('Could not send OTP') }
    finally { setLoading(false) }
  }

  async function verifyOtp(e: React.FormEvent) {
    e.preventDefault(); setLoading(true)
    try {
      await auth.verifyOtp(phone, otp)
      setStep('pin')
    } catch { toast.error('Invalid OTP') }
    finally { setLoading(false) }
  }

  async function resetPin(e: React.FormEvent) {
    e.preventDefault()
    if (pin !== confirm) { toast.error('PINs do not match'); return }
    setLoading(true)
    try {
      await auth.setPin(pin)
      toast.success('PIN reset successfully. Please sign in.')
      router.push('/login')
    } catch { toast.error('Failed to reset PIN') }
    finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-primary-bg px-4">
      <div className="w-full max-w-sm">
        <button onClick={() => router.push('/login')}
          className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text mb-8">
          <ArrowLeft size={16} /> Back to login
        </button>

        <h1 className="text-2xl font-bold mb-2">Reset your PIN</h1>

        {step === 'phone' && (
          <form onSubmit={requestOtp} className="flex flex-col gap-4 mt-6">
            <Input label="Phone number" type="tel" value={phone} onChange={e => setPhone(e.target.value)} autoFocus />
            <Button type="submit" loading={loading} size="lg">Send OTP</Button>
          </form>
        )}

        {step === 'otp' && (
          <form onSubmit={verifyOtp} className="flex flex-col gap-4 mt-6">
            <Input label="OTP code" inputMode="numeric" maxLength={6} value={otp} onChange={e => setOtp(e.target.value)} autoFocus />
            <Button type="submit" loading={loading} size="lg">Verify</Button>
          </form>
        )}

        {step === 'pin' && (
          <form onSubmit={resetPin} className="flex flex-col gap-4 mt-6">
            <Input label="New PIN" type="password" inputMode="numeric" maxLength={4} value={pin} onChange={e => setPin(e.target.value)} autoFocus />
            <Input label="Confirm new PIN" type="password" inputMode="numeric" maxLength={4} value={confirm} onChange={e => setConfirm(e.target.value)} />
            <Button type="submit" loading={loading} size="lg">Reset PIN</Button>
          </form>
        )}
      </div>
    </div>
  )
}
