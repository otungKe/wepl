'use client'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/Button'
import { LogOut, ShieldCheck, Bell, HelpCircle, FileText } from 'lucide-react'

interface SettingRow {
  icon: React.ElementType
  label: string
  description: string
  href?: string
  danger?: boolean
  action?: () => void
}

export default function SettingsPage() {
  const router  = useRouter()
  const logout  = useAuthStore(s => s.logout)

  const handleLogout = () => { logout(); router.push('/') }

  const rows: SettingRow[] = [
    { icon: ShieldCheck, label: 'Identity Verification', description: 'Manage your KYC documents and status', href: '/kyc' },
    { icon: Bell,        label: 'Notifications',         description: 'Manage notification preferences' },
    { icon: HelpCircle,  label: 'Help & Support',        description: 'Get help or contact support' },
    { icon: FileText,    label: 'Terms & Privacy',       description: 'View our terms and privacy policy' },
  ]

  return (
    <div className="max-w-lg mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-text mb-6">Settings</h1>

      <div className="bg-white rounded-lg shadow-card divide-y divide-divider mb-6">
        {rows.map(({ icon: Icon, label, description, href, action }) => (
          <button
            key={label}
            onClick={href ? () => router.push(href) : action}
            className="w-full flex items-center gap-4 px-4 py-4 hover:bg-primary-bg transition-colors text-left"
          >
            <div className="w-9 h-9 rounded-lg bg-primary-pale flex items-center justify-center flex-shrink-0">
              <Icon size={18} className="text-primary" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-text">{label}</p>
              <p className="text-xs text-text-muted mt-0.5">{description}</p>
            </div>
            <span className="text-text-muted">›</span>
          </button>
        ))}
      </div>

      <Button
        variant="danger"
        className="w-full"
        onClick={handleLogout}
      >
        <LogOut size={16} /> Sign Out
      </Button>
    </div>
  )
}
