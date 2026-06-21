'use client'
import Link from 'next/link'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { getAccessToken, isTokenValid } from '@/lib/auth'
import { Button } from '@/components/ui/Button'
import { Building2, Shield, Users, TrendingUp } from 'lucide-react'

const FEATURES = [
  { icon: Users,     text: 'Community savings groups & ROSCA' },
  { icon: TrendingUp,text: 'Multi-sig disbursements & advances' },
  { icon: Shield,    text: 'Welfare & shares funds' },
]

export default function WelcomePage() {
  const router = useRouter()

  useEffect(() => {
    const token = getAccessToken()
    if (token && isTokenValid(token)) router.replace('/communities')
  }, [router])

  return (
    <div className="min-h-screen flex">
      {/* Left — branding panel */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-primary px-12 py-16 text-white">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
            <Building2 size={22} className="text-white" />
          </div>
          <span className="text-2xl font-bold tracking-tight">WEPL</span>
        </div>

        <div>
          <h1 className="text-4xl font-bold leading-tight mb-4">
            Your community&apos;s financial OS
          </h1>
          <p className="text-primary-pale text-lg mb-10">
            Contributions, rotations, welfare funds, and emergency advances — built for the way your community already works.
          </p>
          <ul className="space-y-4">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-primary-pale">
                <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center">
                  <Icon size={16} className="text-white" />
                </div>
                <span className="text-sm">{text}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-primary-pale/60">
          © {new Date().getFullYear()} WEPL. Powered by M-Pesa.
        </p>
      </div>

      {/* Right — auth panel */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-16">
        {/* Mobile logo */}
        <div className="lg:hidden flex items-center gap-3 mb-12">
          <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
            <Building2 size={22} className="text-white" />
          </div>
          <span className="text-2xl font-bold text-text tracking-tight">WEPL</span>
        </div>

        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-bold text-text mb-2">Welcome</h2>
          <p className="text-text-secondary mb-8">Sign in or create your account</p>

          <div className="flex flex-col gap-3">
            <Link href="/login" className="block">
              <Button className="w-full" size="lg">Sign In</Button>
            </Link>
            <Link href="/login?mode=register" className="block">
              <Button variant="secondary" className="w-full" size="lg">Create Account</Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
