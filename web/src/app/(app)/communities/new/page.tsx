'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Globe, Lock, UserCheck, HeartHandshake, TrendingUp } from 'lucide-react'
import { communities, apiError } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Input, Textarea, Select } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { OptionCard, ToggleRow } from '@/components/ui/OptionCard'
import { toast } from 'sonner'

const CATEGORIES = [
  ['general', 'General'], ['savings', 'Savings'], ['chama', 'Chama / Investment Club'],
  ['investment', 'Investment'], ['welfare', 'Welfare'], ['emergency', 'Emergency Fund'],
  ['business', 'Business'],
] as const

type Access = 'private' | 'request' | 'open'

// Access level → the two backend fields it drives.
const ACCESS: Record<Access, { is_private: boolean; join_policy: string }> = {
  private: { is_private: true,  join_policy: 'invite_only' },
  request: { is_private: false, join_policy: 'request' },
  open:    { is_private: false, join_policy: 'open' },
}

export default function NewCommunityPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('general')
  const [location, setLocation] = useState('')
  const [access, setAccess] = useState<Access>('private')
  const [hasWelfare, setHasWelfare] = useState(false)
  const [hasShares, setHasShares] = useState(false)
  const [sharePrice, setSharePrice] = useState('100')
  const [invitePermission, setInvitePermission] = useState('admins')
  const [contributionPermission, setContributionPermission] = useState('admins')
  const [memberListVisibility, setMemberListVisibility] = useState('all')
  const [maxMembers, setMaxMembers] = useState('')
  const [coolingOff, setCoolingOff] = useState('0')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    if (name.trim().length < 3) { setError('Name must be at least 3 characters'); return }
    setError(''); setSaving(true)
    try {
      const { is_private, join_policy } = ACCESS[access]
      const { data: c } = await communities.create({
        name: name.trim(),
        description: description.trim() || undefined,
        category, location: location.trim() || undefined,
        is_private, join_policy,
        has_welfare_fund: hasWelfare,
        has_shares_fund: hasShares,
        ...(hasShares && sharePrice ? { share_price: Number(sharePrice) } : {}),
        invite_permission: invitePermission,
        contribution_permission: contributionPermission,
        member_list_visibility: memberListVisibility,
        max_members: maxMembers ? Number(maxMembers) : null,
        cooling_off_days: coolingOff ? Number(coolingOff) : 0,
      })
      toast.success('Community created')
      router.replace(`/community/${c.id}`)
    } catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }

  return (
    <div className="mx-auto max-w-2xl pb-10">
      <PageHeader title="Create a community" subtitle="Set up a group for savings, contributions and members" back />

      <form onSubmit={e => { e.preventDefault(); submit() }} className="flex flex-col gap-6">
        {/* Identity */}
        <section className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5">
          <Input label="Name" required value={name} onChange={e => { setName(e.target.value); setError('') }}
            placeholder="e.g. Westlands Chama" error={error} autoFocus />
          <Textarea label="Description" value={description} onChange={e => setDescription(e.target.value)}
            placeholder="What is this group about?" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Category" value={category} onChange={e => setCategory(e.target.value)}>
              {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Input label="Location" value={location} onChange={e => setLocation(e.target.value)} placeholder="e.g. Nairobi, Westlands" />
          </div>
        </section>

        {/* Access */}
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-text">Who can join?</h2>
          <OptionCard label="Private" desc="Invite only — hidden from discovery" icon={<Lock size={18} />}
            active={access === 'private'} onClick={() => setAccess('private')} />
          <OptionCard label="Request to join" desc="Public, but admins approve each request" icon={<UserCheck size={18} />}
            active={access === 'request'} onClick={() => setAccess('request')} />
          <OptionCard label="Open" desc="Anyone can find and join instantly" icon={<Globe size={18} />}
            active={access === 'open'} onClick={() => setAccess('open')} />
        </section>

        {/* Funds */}
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-text">Funds</h2>
          <ToggleRow label="Welfare fund" desc="Members contribute to a shared safety net" icon={<HeartHandshake size={20} />}
            checked={hasWelfare} onChange={setHasWelfare} />
          <ToggleRow label="Shares fund" desc="Members buy shares and build ownership" icon={<TrendingUp size={20} />}
            checked={hasShares} onChange={setHasShares} />
          {hasShares && (
            <Input label="Price per share (KES)" type="number" inputMode="decimal" value={sharePrice}
              onChange={e => setSharePrice(e.target.value)} placeholder="100" />
          )}
        </section>

        {/* Governance */}
        <section className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5">
          <h2 className="text-sm font-semibold text-text">Permissions</h2>
          <Select label="Who can invite members?" value={invitePermission} onChange={e => setInvitePermission(e.target.value)}>
            <option value="admins">Admins only</option>
            <option value="members">All members</option>
          </Select>
          <Select label="Who can create contributions?" value={contributionPermission} onChange={e => setContributionPermission(e.target.value)}>
            <option value="admins">Admins only</option>
            <option value="members">All members</option>
          </Select>
          <Select label="Member list visible to" value={memberListVisibility} onChange={e => setMemberListVisibility(e.target.value)}>
            <option value="all">All members</option>
            <option value="admins">Admins only</option>
          </Select>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Max members" type="number" inputMode="numeric" value={maxMembers}
              onChange={e => setMaxMembers(e.target.value)} placeholder="No limit" hint="Leave blank for unlimited" />
            <Input label="Cooling-off (days)" type="number" inputMode="numeric" value={coolingOff}
              onChange={e => setCoolingOff(e.target.value)} placeholder="0" hint="Delay before new members can transact" />
          </div>
        </section>

        <div className="flex gap-3">
          <Button type="button" variant="outline" onClick={() => router.back()} className="flex-1">Cancel</Button>
          <Button type="submit" loading={saving} className="flex-[2]">Create community</Button>
        </div>
      </form>
    </div>
  )
}
