'use client'
import { useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { AuthShell } from '@/components/app/AuthShell'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { auth, apiError } from '@/lib/api'
import { saveTokens } from '@/lib/auth'
import { landingPath } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'

function normalizePhone(raw: string): string {
  const d = raw.replace(/\D/g, '')
  if (d.startsWith('0')) return '254' + d.slice(1)
  if (d.startsWith('7') || d.startsWith('1')) return '254' + d
  return d
}

function LoginForm() {
  const params = useSearchParams()
  const isRegister = params.get('mode') === 'register'
  const router = useRouter()
  const { setPendingPhone, login } = useAuthStore()

  const [phase, setPhase] = useState<'phone' | 'pin'>('phone')
  const [phone, setPhone] = useState('')
  const [pin, setPin] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handlePhone(e: React.FormEvent) {
    e.preventDefault(); setError('')
    const normalized = normalizePhone(phone)
    if (!/^2547\d{8}$/.test(normalized)) { setError('Enter a valid Kenyan phone number'); return }
    setLoading(true)
    try {
      if (isRegister) {
        await auth.requestOtp(normalized)
        setPendingPhone(normalized)
        router.push('/otp')
      } else {
        setPendingPhone(normalized)
        setPhase('pin')
      }
    } catch (err) { setError(apiError(err)) } finally { setLoading(false) }
  }

  async function handlePin(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (pin.length !== 6) { setError('Enter your 6-digit PIN'); return }
    setLoading(true)
    try {
      const { data } = await auth.login(normalizePhone(phone), pin)
      saveTokens(data.access, data.refresh)
      const profile = await auth.profile()
      login(data.access, data.refresh, profile.data)
      router.push(landingPath(profile.data.kyc_status))
    } catch (err) { setError(apiError(err, 'Incorrect phone number or PIN.')) } finally { setLoading(false) }
  }

  if (phase === 'pin') {
    return (
      <AuthShell title="Enter your PIN" subtitle={`Signing in as ${normalizePhone(phone)}`} onBack={() => { setPhase('phone'); setPin(''); setError('') }} backLabel="Change number">
        <form onSubmit={handlePin} className="flex flex-col gap-5">
          <Input label="6-digit PIN" type="password" inputMode="numeric" maxLength={6} placeholder="••••••"
            value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} error={error} autoFocus />
          <Button type="submit" size="lg" loading={loading} fullWidth>Sign in</Button>
          <div className="text-center"><Link href="/forgot-pin" className="text-sm font-medium text-primary">Forgot PIN?</Link></div>
        </form>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title={isRegister ? 'Create account' : 'Welcome back'}
      subtitle={isRegister ? 'Enter your phone number to get started.' : 'Enter your phone number to continue.'}
      footer={isRegister
        ? <>Already have an account? <Link href="/login" className="font-semibold text-primary">Sign in</Link></>
        : <>New to WEPL? <Link href="/login?mode=register" className="font-semibold text-primary">Create account</Link></>}
    >
      <form onSubmit={handlePhone} className="flex flex-col gap-5">
        <Input label="Phone number" type="tel" placeholder="07XX XXX XXX or 2547XXXXXXXX"
          value={phone} onChange={e => setPhone(e.target.value)} error={error} autoFocus />
        <Button type="submit" size="lg" loading={loading} fullWidth>{isRegister ? 'Send OTP' : 'Continue'}</Button>
      </form>
    </AuthShell>
  )
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>
}
