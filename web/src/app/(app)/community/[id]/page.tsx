'use client'
import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { MessageSquare, Coins, HeartHandshake, Plus, Copy, LogOut, Crown, Shield, UserMinus, Settings2 } from 'lucide-react'
import {
  communities, contributions, conversations, apiError,
  type Community, type CommunityMember, type Contribution, type Conversation,
} from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { PageHeader } from '@/components/app/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton, PageLoader } from '@/components/ui/Spinner'
import { formatMoney } from '@/lib/utils'
import { toast } from 'sonner'

export default function CommunityDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const myPhone = useAuthStore(s => s.user?.phone_number)
  const [c, setC] = useState<Community | null>(null)
  const [tab, setTab] = useState('chats')
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    communities.get(id).then(r => {
      setC(r.data)
      if (r.data.created_by === myPhone) { setIsAdmin(true); return }
      communities.members(id)
        .then(ms => setIsAdmin(ms.some(m => m.phone_number === myPhone && m.role === 'admin')))
        .catch(() => {})
    }).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [id, myPhone])

  async function leave() {
    if (!confirm('Leave this community?')) return
    try { await communities.leave(id); toast.success('You left the community'); router.push('/communities') }
    catch (e) { toast.error(apiError(e)) }
  }
  function copyInvite() { if (c) { navigator.clipboard.writeText(c.invite_code); toast.success('Invite code copied') } }

  if (loading) return <PageLoader />
  if (!c) return <EmptyState title="Community not found" />

  return (
    <div>
      <PageHeader title={c.name} subtitle={`${c.member_count} members`} back="/communities"
        action={
          <div className="flex gap-2">
            {isAdmin && (
              <Link href={`/community/${id}/settings`}>
                <Button variant="outline" size="sm"><Settings2 size={15} /> Settings</Button>
              </Link>
            )}
            <Button variant="ghost" size="sm" onClick={leave}><LogOut size={15} /> Leave</Button>
          </div>
        } />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button onClick={copyInvite} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-text-secondary hover:bg-divider">
          <Copy size={14} /> Invite code: <span className="font-semibold text-text">{c.invite_code}</span>
        </button>
        {c.has_welfare_fund && (
          <Link href={`/welfare/${c.id}`} className="inline-flex items-center gap-1.5 rounded-lg bg-primary-pale px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary-pale/70">
            <HeartHandshake size={15} /> Welfare fund
          </Link>
        )}
        {c.has_shares_fund && (
          <Link href={`/shares/${c.id}`} className="inline-flex items-center gap-1.5 rounded-lg bg-accent-pale px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent-pale/70">
            <Coins size={15} /> Shares fund
          </Link>
        )}
      </div>

      <Tabs active={tab} onChange={setTab} className="mb-4"
        tabs={[{ key: 'chats', label: 'Chats' }, { key: 'contributions', label: 'Contributions' }, { key: 'members', label: 'Members' }]} />

      {tab === 'chats' && <ChatsTab communityId={id} />}
      {tab === 'contributions' && <ContributionsTab communityId={id} />}
      {tab === 'members' && <MembersTab communityId={id} community={c} />}
    </div>
  )
}

function ChatsTab({ communityId }: { communityId: string }) {
  const [items, setItems] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [topic, setTopic] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    conversations.forCommunity(communityId).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [communityId])
  useEffect(() => { load() }, [load])

  async function create() {
    if (!topic.trim()) return
    setSaving(true)
    try { await conversations.create(communityId, topic.trim()); setTopic(''); setOpen(false); load() }
    catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }

  if (loading) return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>

  return (
    <div>
      <div className="mb-3 flex justify-end"><Button size="sm" onClick={() => setOpen(true)}><Plus size={15} /> New topic</Button></div>
      {items.length === 0 ? (
        <EmptyState icon={MessageSquare} title="No conversations yet" description="Start a topic to chat with members." />
      ) : (
        <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
          {items.map(cv => (
            <Link key={cv.id} href={`/conversation/${cv.id}`} className="flex items-center gap-3 p-4 hover:bg-divider/50">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-pale text-primary"><MessageSquare size={18} /></div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-text">{cv.topic}</p>
                <p className="truncate text-sm text-text-muted">{cv.last_message ? `${cv.last_message.sender}: ${cv.last_message.content}` : 'No messages yet'}</p>
              </div>
              {cv.unread_count > 0 && <span className="rounded-full bg-accent px-2 text-xs font-semibold text-white">{cv.unread_count}</span>}
            </Link>
          ))}
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="New topic">
        <div className="flex flex-col gap-4">
          <Input label="Topic" value={topic} onChange={e => setTopic(e.target.value)} placeholder="e.g. Monthly meeting" autoFocus />
          <Button onClick={create} loading={saving} fullWidth>Create</Button>
        </div>
      </Modal>
    </div>
  )
}

function ContributionsTab({ communityId }: { communityId: string }) {
  const router = useRouter()
  const [items, setItems] = useState<Contribution[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    contributions.forCommunity(communityId).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [communityId])
  useEffect(() => { load() }, [load])

  if (loading) return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>

  return (
    <div>
      <div className="mb-3 flex justify-end"><Button size="sm" onClick={() => router.push(`/contribution/new?community=${communityId}`)}><Plus size={15} /> New contribution</Button></div>
      {items.length === 0 ? (
        <EmptyState icon={Coins} title="No contributions yet" description="Create a contribution pool for this community." />
      ) : (
        <div className="grid gap-3">
          {items.map(ct => (
            <Link key={ct.id} href={`/contribution/${ct.id}`} className="rounded-lg border border-border bg-surface p-4 hover:shadow-card">
              <div className="flex items-center justify-between">
                <p className="font-semibold text-text">{ct.title}</p>
                <Badge tone={ct.status === 'active' ? 'success' : 'neutral'}>{ct.status}</Badge>
              </div>
              <p className="mt-1 text-sm text-text-muted">{ct.participant_count} members · {ct.frequency}</p>
              <p className="mt-2 text-lg font-bold text-primary">{formatMoney(ct.current_amount)}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function MembersTab({ communityId, community }: { communityId: string; community: Community }) {
  const myPhone = useAuthStore(s => s.user?.phone_number)
  const [items, setItems] = useState<CommunityMember[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<CommunityMember | null>(null)

  const load = useCallback(() => {
    communities.members(communityId).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [communityId])
  useEffect(() => { load() }, [load])

  const myRole = items.find(m => m.phone_number === myPhone)?.role
  const iAmAdmin = community.created_by === myPhone || myRole === 'admin'

  if (loading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
  if (items.length === 0) return <EmptyState title="No members" />

  return (
    <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
      {items.map(m => {
        const isOwner = m.phone_number === community.created_by
        const isSelf = m.phone_number === myPhone
        const canManage = iAmAdmin && !isOwner && !isSelf
        return (
          <div key={m.id} className="flex items-center gap-3 p-3.5">
            <Avatar name={m.name} src={m.profile_photo} size={40} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-text">{m.name}{isSelf && <span className="text-text-muted"> (you)</span>}</p>
              <p className="truncate text-sm text-text-muted">{m.phone_number}</p>
            </div>
            {isOwner ? (
              <Badge tone="warning"><Crown size={11} /> owner</Badge>
            ) : m.role !== 'member' ? (
              <Badge tone={m.role === 'admin' ? 'primary' : 'warning'}>{m.role === 'admin' && <Shield size={11} />}{m.role}</Badge>
            ) : null}
            {canManage && (
              <button onClick={() => setSelected(m)} className="rounded-lg p-1.5 text-text-muted hover:bg-divider hover:text-text" aria-label="Manage member">
                <Settings2 size={16} />
              </button>
            )}
          </div>
        )
      })}

      <ManageMemberModal
        member={selected}
        communityId={communityId}
        onClose={() => setSelected(null)}
        onChanged={load}
      />
    </div>
  )
}

const ROLE_OPTIONS: { role: 'admin' | 'treasurer' | 'member'; label: string; desc: string }[] = [
  { role: 'admin',     label: 'Admin',     desc: 'Manage members, contributions and settings' },
  { role: 'treasurer', label: 'Treasurer', desc: 'Manage contributions and approve payouts' },
  { role: 'member',    label: 'Member',    desc: 'Standard access' },
]

function ManageMemberModal({ member, communityId, onClose, onChanged }: {
  member: CommunityMember | null; communityId: string; onClose: () => void; onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)

  async function setRole(role: 'admin' | 'treasurer' | 'member') {
    if (!member || member.role === role) return
    setBusy(true)
    try { await communities.assignRole(communityId, member.id, role); toast.success(`${member.name} is now ${role}`); onChanged(); onClose() }
    catch (e) { toast.error(apiError(e)) } finally { setBusy(false) }
  }
  async function removeMember() {
    if (!member || !confirm(`Remove ${member.name} from this community?`)) return
    setBusy(true)
    try { await communities.removeMember(communityId, member.id); toast.success(`${member.name} removed`); onChanged(); onClose() }
    catch (e) { toast.error(apiError(e)) } finally { setBusy(false) }
  }

  return (
    <Modal open={!!member} onClose={onClose} title={member ? `Manage ${member.name}` : 'Manage member'}>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium text-text-secondary">Role</p>
        {ROLE_OPTIONS.map(opt => (
          <button key={opt.role} disabled={busy} onClick={() => setRole(opt.role)}
            className={cnRow(member?.role === opt.role)}>
            <div className="min-w-0">
              <p className="font-medium text-text">{opt.label}</p>
              <p className="text-sm text-text-muted">{opt.desc}</p>
            </div>
            {member?.role === opt.role && <Badge tone="success">Current</Badge>}
          </button>
        ))}
        <button disabled={busy} onClick={removeMember}
          className="mt-2 flex items-center justify-center gap-2 rounded-lg border border-error/30 bg-red-50 px-4 py-2.5 text-sm font-medium text-error hover:bg-red-100 disabled:opacity-50">
          <UserMinus size={16} /> Remove from community
        </button>
      </div>
    </Modal>
  )
}

function cnRow(active: boolean) {
  return [
    'flex items-center justify-between gap-3 rounded-lg border px-4 py-3 text-left transition-colors disabled:opacity-50',
    active ? 'border-primary bg-primary-pale/50' : 'border-border bg-surface hover:bg-divider/50',
  ].join(' ')
}
