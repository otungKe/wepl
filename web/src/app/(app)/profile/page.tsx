'use client'
import { useRef, useState } from 'react'
import { Camera, Save, ShieldCheck } from 'lucide-react'
import Link from 'next/link'
import { auth, apiError } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { PageHeader } from '@/components/app/PageHeader'
import { Avatar } from '@/components/ui/Avatar'
import { Input, Textarea } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Badge, statusTone } from '@/components/ui/Badge'
import { toast } from 'sonner'

export default function ProfilePage() {
  const user = useAuthStore(s => s.user)
  const setUser = useAuthStore(s => s.setUser)
  const [name, setName] = useState(user?.name ?? '')
  const [bio, setBio] = useState(user?.bio ?? '')
  const [saving, setSaving] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  async function save() {
    setSaving(true)
    try { const r = await auth.updateProfile({ name, bio }); setUser(r.data); toast.success('Profile updated') }
    catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }
  async function uploadPhoto(file: File) {
    const form = new FormData(); form.append('profile_photo', file)
    try { const r = await auth.updateProfile(form); setUser(r.data); toast.success('Photo updated') }
    catch (e) { toast.error(apiError(e)) }
  }

  const kyc = user?.kyc_status ?? 'not_submitted'

  return (
    <div className="max-w-lg">
      <PageHeader title="Profile" subtitle="Manage your account details" />

      <div className="mb-6 flex items-center gap-4">
        <div className="relative">
          <Avatar name={user?.name || user?.phone_number || '?'} src={user?.profile_photo} size={76} />
          <button onClick={() => fileRef.current?.click()} className="absolute -bottom-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full bg-primary text-white shadow-sm">
            <Camera size={14} />
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => e.target.files?.[0] && uploadPhoto(e.target.files[0])} />
        </div>
        <div>
          <p className="text-lg font-bold text-text">{user?.name || 'WEPL user'}</p>
          <p className="text-sm text-text-muted">{user?.phone_number}</p>
        </div>
      </div>

      <Link href="/kyc" className="mb-6 flex items-center justify-between rounded-lg border border-border bg-surface p-4 hover:bg-divider/40">
        <span className="flex items-center gap-2 text-text"><ShieldCheck size={18} className="text-primary" /> Identity verification</span>
        <Badge tone={statusTone(kyc)}>{kyc.replace('_', ' ')}</Badge>
      </Link>

      <div className="flex flex-col gap-4">
        <Input label="Name" value={name} onChange={e => setName(e.target.value)} />
        <Textarea label="Bio" value={bio} onChange={e => setBio(e.target.value)} placeholder="Tell others about yourself" />
        <Button onClick={save} loading={saving}><Save size={16} /> Save changes</Button>
      </div>
    </div>
  )
}
