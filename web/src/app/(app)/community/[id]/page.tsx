'use client'
import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { MessageSquare, Coins, HeartHandshake, Plus, Copy, LogOut, Crown } from 'lucide-react'
import {
  communities, contributions, conversations, apiError,
  type Community, type CommunityMember, type Contribution, type Conversation,
} from '@/lib/api'
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
  const [c, setC] = useState<Community | null>(null)
  const [tab, setTab] = useState('chats')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    communities.get(id).then(r => setC(r.data)).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [id])

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
        action={<Button variant="ghost" size="sm" onClick={leave}><LogOut size={15} /> Leave</Button>} />

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
      {tab === 'members' && <MembersTab communityId={id} />}
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
  const [items, setItems] = useState<Contribution[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    contributions.forCommunity(communityId).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [communityId])
  useEffect(() => { load() }, [load])

  if (loading) return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>

  return (
    <div>
      <div className="mb-3 flex justify-end"><Button size="sm" onClick={() => setOpen(true)}><Plus size={15} /> New contribution</Button></div>
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
      <CreateContributionModal open={open} onClose={() => setOpen(false)} communityId={communityId} onCreated={load} />
    </div>
  )
}

function CreateContributionModal({ open, onClose, communityId, onCreated }: { open: boolean; onClose: () => void; communityId: string; onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [amount, setAmount] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit() {
    if (!title.trim()) return toast.error('Enter a title')
    setSaving(true)
    try {
      await contributions.create({
        title, community: Number(communityId), visibility: 'closed',
        tenure_type: 'open', frequency: 'monthly',
        amount_type: amount ? 'fixed' : 'open', fixed_amount: amount ? Number(amount) : null,
        voting_threshold: 'admins', add_all_members: true,
      })
      toast.success('Contribution created'); setTitle(''); setAmount(''); onClose(); onCreated()
    } catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="New contribution">
      <div className="flex flex-col gap-4">
        <Input label="Title" value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Monthly savings" autoFocus />
        <Input label="Fixed amount (optional)" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} placeholder="Leave blank for open amount" hint="Monthly · all community members added" />
        <Button onClick={submit} loading={saving} fullWidth>Create contribution</Button>
      </div>
    </Modal>
  )
}

function MembersTab({ communityId }: { communityId: string }) {
  const [items, setItems] = useState<CommunityMember[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    communities.members(communityId).then(setItems).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [communityId])

  if (loading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
  if (items.length === 0) return <EmptyState title="No members" />

  return (
    <div className="divide-y divide-divider overflow-hidden rounded-lg border border-border bg-surface">
      {items.map(m => (
        <div key={m.id} className="flex items-center gap-3 p-3.5">
          <Avatar name={m.name} src={m.profile_photo} size={40} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-text">{m.name}</p>
            <p className="truncate text-sm text-text-muted">{m.phone_number}</p>
          </div>
          {m.role !== 'member' && <Badge tone={m.role === 'admin' ? 'primary' : 'warning'}>{m.role === 'admin' && <Crown size={11} />}{m.role}</Badge>}
        </div>
      ))}
    </div>
  )
}
