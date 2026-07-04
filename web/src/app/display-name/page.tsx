'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { AuthShell } from '@/components/app/AuthShell'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { auth, apiError } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { toast } from 'sonner'

/**
 * Final step of the registration journey (after PIN set), mirroring the mobile
 * `display-name` screen: capture the name community members will see. The user
 * already holds an active session token here, so it's a plain profile PATCH.
 */
export default function DisplayNamePage() {
  const router = useRouter()
  const setUser = useAuthStore(s => s.setUser)
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const trimmed = name.trim()

  async function save() {
    if (!trimmed) { setError('Please enter a display name.'); return }
    setLoading(true); setError('')
    try {
      const { data } = await auth.updateProfile({ name: trimmed })
      setUser(data)
      router.replace('/profile')
    } catch (e) {
      // Non-fatal — they can set it later in Profile.
      toast.error(apiError(e, "Couldn't save your name. You can update it later in Profile."))
      router.replace('/profile')
    } finally { setLoading(false) }
  }

  function skip() { router.replace('/profile') }

  return (
    <AuthShell title="What should we call you?" subtitle="This is the name your community members will see. You can change it anytime.">
      <form onSubmit={e => { e.preventDefault(); save() }} className="flex flex-col gap-5">
        <div className="flex justify-center">
          <Avatar name={trimmed || '?'} size={72} />
        </div>
        <Input label="Display name" value={name} maxLength={60} autoFocus placeholder="e.g. Amina Wanjiru"
          onChange={e => { setName(e.target.value); setError('') }} error={error} />
        <Button type="submit" size="lg" loading={loading} disabled={!trimmed} fullWidth>Get started</Button>
        <button type="button" onClick={skip} disabled={loading} className="text-center text-sm font-medium text-text-muted hover:text-text">
          Skip for now
        </button>
      </form>
    </AuthShell>
  )
}
