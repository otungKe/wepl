'use client'
import Link from 'next/link'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Building2, Users, Banknote, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { isAuthenticated } from '@/lib/auth'

const FEATURES = [
  { icon: Users, title: 'Communities & chamas', desc: 'Create or join savings groups and stay in sync.' },
  { icon: Banknote, title: 'Contributions & ROSCA', desc: 'Pool funds, rotate payouts, run welfare & shares.' },
  { icon: ShieldCheck, title: 'Secure by design', desc: 'Phone + PIN auth, M-PESA payments, audited ledger.' },
]

export default function WelcomePage() {
  const router = useRouter()
  useEffect(() => { if (isAuthenticated()) router.replace('/communities') }, [router])

  return (
    <div className="min-h-screen bg-primary-bg">
      <div className="mx-auto flex max-w-5xl flex-col items-center px-6 py-16 lg:py-24">
        <div className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary">
            <Building2 size={22} className="text-white" />
          </div>
          <span className="text-2xl font-bold text-text">WEPL</span>
        </div>

        <h1 className="mt-10 max-w-2xl text-center text-3xl font-bold leading-tight text-text sm:text-4xl">
          Community savings & contributions, <span className="text-primary">simplified.</span>
        </h1>
        <p className="mt-4 max-w-xl text-center text-text-secondary">
          Run your chama, SACCO or welfare group end-to-end — contributions, ROSCA payouts,
          emergency advances and shares, all over M-PESA.
        </p>

        <div className="mt-8 flex w-full max-w-xs flex-col gap-3">
          <Link href="/login?mode=register"><Button size="lg" fullWidth>Create account</Button></Link>
          <Link href="/login"><Button size="lg" variant="outline" fullWidth>Sign in</Button></Link>
        </div>

        <div className="mt-16 grid w-full gap-4 sm:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="rounded-lg border border-border bg-surface p-5">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-pale text-primary">
                <Icon size={20} />
              </div>
              <p className="mt-3 font-semibold text-text">{title}</p>
              <p className="mt-1 text-sm text-text-muted">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
