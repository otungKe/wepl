'use client'
import { useAuthStore } from '@/store/auth'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { KYCBanner } from '@/components/ui/KYCBanner'
import { ShieldCheck, Phone, User } from 'lucide-react'
import Link from 'next/link'

export default function ProfilePage() {
  const user = useAuthStore(s => s.user)
  if (!user) return null

  const kycVariant = user.kyc_status === 'approved' ? 'approved'
    : user.kyc_status === 'pending' ? 'pending'
    : user.kyc_status === 'rejected' ? 'rejected'
    : 'default'

  return (
    <div className="max-w-lg mx-auto px-4 py-8">
      {/* Avatar + name */}
      <div className="flex flex-col items-center gap-3 mb-8">
        <Avatar name={user.name} src={user.profile_photo} size="xl" />
        <div className="text-center">
          <h1 className="text-2xl font-bold text-text">{user.name}</h1>
          <p className="text-text-secondary mt-0.5">{user.phone_number}</p>
        </div>
        <Badge variant={kycVariant}>
          <ShieldCheck size={12} className="mr-1" />
          {user.kyc_status === 'approved' ? 'Verified'
            : user.kyc_status === 'pending' ? 'Under review'
            : user.kyc_status === 'rejected' ? 'Rejected'
            : 'Not verified'}
        </Badge>
      </div>

      {/* KYC banner */}
      {user.kyc_status !== 'approved' && (
        <div className="mb-6">
          <KYCBanner status={user.kyc_status} />
        </div>
      )}

      {/* Info card */}
      <div className="bg-white rounded-lg shadow-card divide-y divide-divider mb-6">
        <div className="flex items-center gap-3 px-4 py-4">
          <User size={16} className="text-text-muted" />
          <div>
            <p className="text-xs text-text-muted">Full name</p>
            <p className="text-sm font-medium text-text mt-0.5">{user.name}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 px-4 py-4">
          <Phone size={16} className="text-text-muted" />
          <div>
            <p className="text-xs text-text-muted">Phone number</p>
            <p className="text-sm font-medium text-text mt-0.5">{user.phone_number}</p>
          </div>
        </div>
      </div>

      {/* Actions */}
      {user.kyc_status !== 'approved' && (
        <Link href="/kyc">
          <Button className="w-full mb-3">Complete Identity Verification</Button>
        </Link>
      )}
      <Link href="/settings">
        <Button variant="secondary" className="w-full">Account Settings</Button>
      </Link>
    </div>
  )
}
