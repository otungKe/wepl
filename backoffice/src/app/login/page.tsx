'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, Lock } from 'lucide-react'
import { ops, setToken, apiError } from '@/lib/ops'

export default function LoginPage() {
  const router = useRouter()
  const [step, setStep] = useState<'login' | 'change'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submitLogin = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const { data } = await ops.login(email.trim().toLowerCase(), password)
      setToken(data.token)
      if (data.must_change_password) { setStep('change') }
      else { router.replace('/') }
    } catch (err) { setError(apiError(err, 'Invalid email or password.')) }
    finally { setLoading(false) }
  }

  const submitChange = async (e: React.FormEvent) => {
    e.preventDefault(); setError('')
    if (newPassword.length < 10) { setError('Password must be at least 10 characters.'); return }
    if (newPassword !== confirm) { setError('Passwords do not match.'); return }
    setLoading(true)
    try {
      await ops.changePassword(password, newPassword)
      router.replace('/')
    } catch (err) { setError(apiError(err, 'Could not set your password.')) }
    finally { setLoading(false) }
  }

  return (
    <div className="dark flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-blue-600 font-mono text-lg font-bold text-white">W</div>
          <div>
            <div className="text-base font-semibold text-slate-100">WEPL Back Office</div>
            <div className="text-[11px] uppercase tracking-widest text-slate-500">Operations Console</div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
          {step === 'login' ? (
            <form onSubmit={submitLogin} className="space-y-4">
              <h1 className="text-sm font-medium text-slate-300">Sign in with your work account</h1>
              <Field label="Work email">
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.co.ke" autoComplete="username"
                  className={INPUT} />
              </Field>
              <Field label="Password">
                <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password" className={INPUT} />
              </Field>
              {error && <p className="text-sm text-red-400">{error}</p>}
              <Submit loading={loading} label="Sign in" />
              <p className="pt-1 text-center text-[11px] text-slate-500">
                Access is provisioned by a Platform Admin. Forgot your password? Contact your administrator.
              </p>
            </form>
          ) : (
            <form onSubmit={submitChange} className="space-y-4">
              <div className="flex items-center gap-2 text-amber-400"><Lock className="h-4 w-4" />
                <h1 className="text-sm font-medium">Set your password to continue</h1></div>
              <p className="text-xs text-slate-400">First sign-in — choose a password only you know.</p>
              <Field label="New password">
                <input type="password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password" className={INPUT} />
              </Field>
              <Field label="Confirm password">
                <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password" className={INPUT} />
              </Field>
              {error && <p className="text-sm text-red-400">{error}</p>}
              <Submit loading={loading} label="Set password & continue" />
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

const INPUT = 'w-full rounded-lg border border-slate-700 bg-[#0b1220] px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-400">{label}</span>
      {children}
    </label>
  )
}

function Submit({ loading, label }: { loading: boolean; label: string }) {
  return (
    <button type="submit" disabled={loading}
      className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60">
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}{label}
    </button>
  )
}
