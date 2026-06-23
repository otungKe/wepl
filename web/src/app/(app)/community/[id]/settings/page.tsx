'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Lock, Users, Globe, ShieldAlert } from 'lucide-react'
import { communities, apiError, type Community } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { PageHeader } from '@/components/app/PageHeader'
import { Input, Textarea, Select } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

type Access = 'private' | 'public_request' | 'public_open'

function toAccess(isPrivate: boolean, joinPolicy: Community['join_policy']): Access {
  if (isPrivate || joinPolicy === 'invite_only') return 'private'
  return joinPolicy === 'open' ? 'public_open' : 'public_request'
}
function fromAccess(a: Access): { is_private: boolean; join_policy: Community['join_policy'] } {
  if (a === 'private')        return { is_private: true,  join_policy: 'invite_only' }
  if (a === 'public_request') return { is_private: false, join_policy: 'request' }
  return                             { is_private: false, join_policy: 'open' }
}

const ACCESS_OPTIONS: { value: Access; icon: typeof Lock; label: string; desc: string }[] = [
  { value: 'private',        icon: Lock,   label: 'Private',                   desc: 'Not discoverable. Members join via invite link only.' },
  { value: 'public_request', icon: Users,  label: 'Public — approval required', desc: 'Appears in Discover. Anyone can request; an admin approves.' },
  { value: 'public_open',    icon: Globe,  label: 'Public — open',             desc: 'Appears in Discover. Any WEPL user can join immediately.' },
]

export default function CommunitySettingsPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const myPhone = useAuthStore(s => s.user?.phone_number)

  const [c, setC] = useState<Community | null>(null)
  const [loading, setLoading] = useState(true)
  const [authorized, setAuthorized] = useState(false)
  const [saving, setSaving] = useState(false)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [access, setAccess] = useState<Access>('private')
  const [invitePerm, setInvitePerm] = useState<Community['invite_permission']>('admins')
  const [contribPerm, setContribPerm] = useState<Community['contribution_permission']>('admins')
  const [listVis, setListVis] = useState<Community['member_list_visibility']>('all')
  const [maxMembers, setMaxMembers] = useState('')
  const [coolingOff, setCoolingOff] = useState('30')

  useEffect(() => {
    async function load() {
      try {
        const { data: comm } = await communities.get(id)
        setC(comm)
        setName(comm.name)
        setDescription(comm.description ?? '')
        setAccess(toAccess(comm.is_private, comm.join_policy))
        setInvitePerm(comm.invite_permission ?? 'admins')
        setContribPerm(comm.contribution_permission ?? 'admins')
        setListVis(comm.member_list_visibility ?? 'all')
        setMaxMembers(comm.max_members ? String(comm.max_members) : '')
        setCoolingOff(comm.cooling_off_days != null ? String(comm.cooling_off_days) : '30')

        let admin = comm.created_by === myPhone
        if (!admin) {
          const members = await communities.members(id).catch(() => [])
          admin = members.some(m => m.phone_number === myPhone && m.role === 'admin')
        }
        setAuthorized(admin)
      } catch (e) { toast.error(apiError(e)) } finally { setLoading(false) }
    }
    load()
  }, [id, myPhone])

  async function save() {
    if (name.trim().length < 3) return toast.error('Community name must be at least 3 characters')
    setSaving(true)
    const { is_private, join_policy } = fromAccess(access)
    try {
      await communities.update(id, {
        name: name.trim(),
        description: description.trim(),
        is_private,
        join_policy,
        invite_permission: invitePerm,
        contribution_permission: contribPerm,
        member_list_visibility: listVis,
        max_members: maxMembers ? Number(maxMembers) : null,
        cooling_off_days: coolingOff ? Number(coolingOff) : 0,
      })
      toast.success('Settings saved')
      router.push(`/community/${id}`)
    } catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }

  if (loading) return <PageLoader />
  if (!c) return <EmptyState title="Community not found" />
  if (!authorized) return (
    <div>
      <PageHeader title="Community settings" back={`/community/${id}`} />
      <EmptyState icon={ShieldAlert} title="Admins only" description="Only the community owner or an admin can change these settings." />
    </div>
  )

  return (
    <div className="max-w-2xl">
      <PageHeader title="Community settings" subtitle={c.name} back={`/community/${id}`} />

      <div className="space-y-6">
        <section className="space-y-4 rounded-lg border border-border bg-surface p-5">
          <Input label="Name" value={name} onChange={e => setName(e.target.value)} />
          <Textarea label="Description" value={description} onChange={e => setDescription(e.target.value)} placeholder="What is this group about?" rows={3} />
        </section>

        <section className="rounded-lg border border-border bg-surface p-5">
          <p className="mb-3 text-sm font-semibold text-text">Who can join</p>
          <div className="space-y-2">
            {ACCESS_OPTIONS.map(opt => {
              const Icon = opt.icon
              const active = access === opt.value
              return (
                <button key={opt.value} onClick={() => setAccess(opt.value)}
                  className={cn('flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors',
                    active ? 'border-primary bg-primary-pale/50' : 'border-border hover:bg-divider/50')}>
                  <Icon size={18} className={cn('mt-0.5 shrink-0', active ? 'text-primary' : 'text-text-muted')} />
                  <div className="min-w-0">
                    <p className="font-medium text-text">{opt.label}</p>
                    <p className="text-sm text-text-muted">{opt.desc}</p>
                  </div>
                </button>
              )
            })}
          </div>
        </section>

        <section className="grid gap-4 rounded-lg border border-border bg-surface p-5 sm:grid-cols-2">
          <Select label="Who can invite members" value={invitePerm} onChange={e => setInvitePerm(e.target.value as Community['invite_permission'])}>
            <option value="admins">Admins only</option>
            <option value="members">All members</option>
          </Select>
          <Select label="Who can create contributions" value={contribPerm} onChange={e => setContribPerm(e.target.value as Community['contribution_permission'])}>
            <option value="admins">Admins only</option>
            <option value="members">All members</option>
          </Select>
          <Select label="Member list visible to" value={listVis} onChange={e => setListVis(e.target.value as Community['member_list_visibility'])}>
            <option value="all">All members</option>
            <option value="admins">Admins only</option>
          </Select>
          <Input label="Max members" type="number" inputMode="numeric" value={maxMembers}
            onChange={e => setMaxMembers(e.target.value)} placeholder="No limit" />
          <Input label="Cooling-off period (days)" type="number" inputMode="numeric" value={coolingOff}
            onChange={e => setCoolingOff(e.target.value)} hint="Wait before a re-joined member can transact. 0 to disable." />
        </section>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => router.push(`/community/${id}`)}>Cancel</Button>
          <Button loading={saving} onClick={save}>Save changes</Button>
        </div>
      </div>
    </div>
  )
}
