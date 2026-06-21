'use client'
import { useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Building2, ArrowLeft } from 'lucide-react'
import { auth } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { toast } from 'sonner'

type Phase = 'phone' | 'pin'

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}

function LoginForm() {
  const searchParams = useSearchParams()
  const isRegister   = searchParams.get('mode') === 'register'
  const router       = useRouter()
  const { setPendingPhone, login } = useAuthStore()

  const [phase, setPhase]       = useState<Phase>('phone')
  const [phone, setPhone]       = useState('')
  const [pin, setPin]           = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')

  async function handlePhone(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (!phone.trim()) return
    setLoading(true)
    try {
      if (isRegister) {
        await auth.requestOtp(phone)
        setPendingPhone(phone)
        router.push('/otp')
      } else {
        setPhase('pin')
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function handlePin(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (pin.length !== 6) { setError('Enter your 6-digit PIN'); return }
    setLoading(true)
    try {
      const { data } = await auth.login(phone, pin)
      const profile  = await auth.profile()
      login(data.access, data.refresh, profile.data)
      router.push('/communities')
    } catch {
      setError('Incorrect phone number or PIN.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-primary-bg px-4">
      <div className="w-full max-w-sm">
        {/* Back */}
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text mb-8">
          <ArrowLeft size={16} /> Back
        </Link>

        {/* Logo */}
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
            <Building2 size={22} className="text-white" />
          </div>
          <span className="text-2xl font-bold text-text">WEPL</span>
        </div>

        {phase === 'phone' ? (
          <>
            <h1 className="text-2xl font-bold mb-1">{isRegister ? 'Create account' : 'Sign in'}</h1>
            <p className="text-text-secondary mb-8">
              {isRegister ? 'Enter your phone number to get started.' : 'Enter your phone number to continue.'}
            </p>
            <form onSubmit={handlePhone} className="flex flex-col gap-5">
              <Input
                label="Phone number"
                type="tel"
                placeholder="+254 7XX XXX XXX"
                value={phone}
                onChange={e => setPhone(e.target.value)}
                error={error}
                autoFocus
              />
              <Button type="submit" loading={loading} size="lg">
                {isRegister ? 'Send OTP' : 'Continue'}
              </Button>
            </form>
            <p className="mt-6 text-center text-sm text-text-secondary">
              {isRegister
                ? <>Already have an account? <Link href="/login" className="text-primary font-medium">Sign in</Link></>
                : <>New to WEPL? <Link href="/login?mode=register" className="text-primary font-medium">Create account</Link></>
              }
            </p>
          </>
        ) : (
          <>
            <button
              onClick={() => { setPhase('phone'); setPin(''); setError('') }}
              className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text mb-6"
            >
              <ArrowLeft size={16} /> {phone}
            </button>
            <h1 className="text-2xl font-bold mb-1">Enter your PIN</h1>
            <p className="text-text-secondary mb-8">Use your 6-digit security PIN.</p>
            <form onSubmit={handlePin} className="flex flex-col gap-5">
              <Input
                label="PIN"
                type="password"
                inputMode="numeric"
                maxLength={6}
                placeholder="••••••"
                value={pin}
                onChange={e => setPin(e.target.value.replace(/\D/g, ''))}
                error={error}
                autoFocus
              />
              <Button type="submit" loading={loading} size="lg">Sign In</Button>
              <div className="text-center">
                <Link href="/forgot-pin" className="text-sm text-primary">Forgot PIN?</Link>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
