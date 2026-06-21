'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { communities as commApi, contributions as contribApi } from '@/lib/api'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Tabs } from '@/components/ui/Tabs'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { ArrowLeft, MessageSquare, Users, Plus, DollarSign, HeartHandshake, TrendingUp, Settings, Lock, Globe } from 'lucide-react'
import Link from 'next/link'
import { toast } from 'sonner'
import { truncate, formatRelative } from '@/lib/utils'

const TABS = [
  { id: 'conversations', label: 'Chats' },
  { id: 'contributions', label: 'Contributions' },
  { id: 'members',       label: 'Members' },
]

export default function CommunityPage() {
  const { id }   = useParams<{ id: string }>()
  const router   = useRouter()
  const [community, setCommunity]     = useState<Record<string, unknown> | null>(null)
  const [conversations, setConversations] = useState<unknown[]>([])
  const [contributions, setContributions] = useState<unknown[]>([])
  const [members, setMembers]             = useState<unknown[]>([])
  const [activeTab, setActiveTab]         = useState('conversations')
  const [loading, setLoading]             = useState(true)
  const [showContrib, setShowContrib]     = useState(false)

  const load = useCallback(async () => {
    try {
      const [comm, convs, contribs, mems] = await Promise.all([
        commApi.get(id),
        commApi.conversations(id),
        contribApi.list(id),
        commApi.members(id),
      ])
      setCommunity(comm.data)
      setConversations(convs.data.results ?? convs.data)
      setContributions(contribs.data.results ?? contribs.data)
      setMembers(mems.data.results ?? mems.data)
    } catch {
      toast.error('Failed to load community')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  if (loading) return <PageLoader />
  if (!community) return null

  const comm = community as {
    name: string; description: string; is_private: boolean; community_photo?: string;
    member_count: number; is_admin: boolean; welfare_fund?: boolean | null; shares_fund?: boolean | null
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-divider px-6 py-4 flex items-center gap-4 sticky top-0 z-10">
        <button onClick={() => router.back()} className="p-1.5 rounded-lg hover:bg-divider text-text-secondary">
          <ArrowLeft size={18} />
        </button>
        <Avatar name={comm.name} src={comm.community_photo} size="md" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="font-semibold text-text">{comm.name}</h1>
            {comm.is_private
              ? <Lock size={13} className="text-text-muted" />
              : <Globe size={13} className="text-text-muted" />
            }
          </div>
          <p className="text-sm text-text-secondary">{comm.member_count} members</p>
        </div>
        <div className="flex items-center gap-2">
          {comm.welfare_fund && (
            <Link href={`/welfare/${id}`} title="Welfare Fund">
              <Button variant="ghost" size="sm"><HeartHandshake size={16} /></Button>
            </Link>
          )}
          {comm.shares_fund && (
            <Link href={`/shares/${id}`} title="Shares Fund">
              <Button variant="ghost" size="sm"><TrendingUp size={16} /></Button>
            </Link>
          )}
          {comm.is_admin && (
            <Link href={`/community/${id}/settings`} title="Settings">
              <Button variant="ghost" size="sm"><Settings size={16} /></Button>
            </Link>
          )}
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} className="bg-white px-4 sticky top-[73px] z-10" />

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'conversations' && (
          <ConversationsList convs={conversations as ConvItem[]} communityId={id} />
        )}
        {activeTab === 'contributions' && (
          <>
            <div className="flex justify-between items-center mb-4">
              <p className="text-sm text-text-secondary">{(contributions as unknown[]).length} contribution pools</p>
              <Button size="sm" onClick={() => setShowContrib(true)}>
                <Plus size={14} /> New
              </Button>
            </div>
            <ContributionsList contribs={contributions as ContribItem[]} />
          </>
        )}
        {activeTab === 'members' && (
          <MembersList members={members as MemberItem[]} />
        )}
      </div>

      {/* Create contribution modal */}
      <Modal open={showContrib} onClose={() => setShowContrib(false)} title="New Contribution Pool" size="lg">
        <CreateContributionForm communityId={id} onSuccess={() => { setShowContrib(false); load() }} />
      </Modal>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface ConvItem {
  id: string; name: string; last_message?: { content: string; created_at: string }; unread_count: number
}

function ConversationsList({ convs, communityId }: { convs: ConvItem[]; communityId: string }) {
  if (!convs.length) return (
    <EmptyState icon={MessageSquare} title="No conversations yet" description="Start a group chat to communicate with members." />
  )
  return (
    <div className="space-y-1">
      {convs.map(c => (
        <Link key={c.id} href={`/conversation/${c.id}`}>
          <div className="flex items-center gap-3 bg-white rounded-lg px-4 py-3 hover:shadow-card transition-shadow cursor-pointer">
            <div className="w-10 h-10 rounded-full bg-primary-pale flex items-center justify-center flex-shrink-0">
              <MessageSquare size={18} className="text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-text">{c.name}</p>
              {c.last_message && (
                <p className="text-sm text-text-secondary truncate">{truncate(c.last_message.content, 50)}</p>
              )}
            </div>
            <div className="text-right shrink-0">
              {c.last_message && <p className="text-xs text-text-muted">{formatRelative(c.last_message.created_at)}</p>}
              {c.unread_count > 0 && (
                <span className="inline-flex items-center justify-center bg-primary text-white text-xs font-bold rounded-full min-w-[18px] h-[18px] px-1 mt-1">
                  {c.unread_count}
                </span>
              )}
            </div>
          </div>
        </Link>
      ))}
    </div>
  )
}

interface ContribItem {
  id: string; title: string; amount_type: string; fixed_amount?: string; frequency: string; member_count?: number
}

function ContributionsList({ contribs }: { contribs: ContribItem[] }) {
  if (!contribs.length) return (
    <EmptyState icon={DollarSign} title="No contributions yet" description="Create the first contribution pool for this community." />
  )
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {contribs.map(c => (
        <Link key={c.id} href={`/contribution/${c.id}`}>
          <div className="bg-white rounded-lg p-4 shadow-card hover:shadow-md transition-shadow cursor-pointer">
            <div className="flex items-start justify-between gap-2 mb-2">
              <p className="font-semibold text-text">{c.title}</p>
              <Badge variant="approved">{c.frequency}</Badge>
            </div>
            <p className="text-sm text-text-secondary">
              {c.amount_type === 'fixed' && c.fixed_amount
                ? `KES ${Number(c.fixed_amount).toLocaleString()} per member`
                : 'Open amount'}
            </p>
            {c.member_count !== undefined && (
              <p className="text-xs text-text-muted mt-2">{c.member_count} participants</p>
            )}
          </div>
        </Link>
      ))}
    </div>
  )
}

interface MemberItem {
  id: string; name: string; phone_number: string; role: string; profile_photo?: string; kyc_status: string
}

function MembersList({ members }: { members: MemberItem[] }) {
  if (!members.length) return (
    <EmptyState icon={Users} title="No members" description="Members appear here once they join." />
  )
  return (
    <div className="space-y-1">
      {members.map(m => (
        <div key={m.id} className="flex items-center gap-3 bg-white rounded-lg px-4 py-3">
          <Avatar name={m.name} src={m.profile_photo} size="md" />
          <div className="flex-1 min-w-0">
            <p className="font-medium text-text truncate">{m.name}</p>
            <p className="text-sm text-text-muted truncate">{m.phone_number}</p>
          </div>
          <div className="flex items-center gap-2">
            {m.role === 'admin' && <Badge variant="approved">Admin</Badge>}
            {m.kyc_status !== 'approved' && <Badge variant="pending">Unverified</Badge>}
          </div>
        </div>
      ))}
    </div>
  )
}

function CreateContributionForm({ communityId, onSuccess }: { communityId: string; onSuccess: () => void }) {
  const [data, setData] = useState({
    title: '', description: '', amount_type: 'fixed', fixed_amount: '',
    frequency: 'monthly', voting_threshold: 'admins', visibility: 'closed',
    tenure_type: 'open',
  })
  const [loading, setLoading] = useState(false)

  const upd = (k: string, v: string) => setData(d => ({ ...d, [k]: v }))

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await contribApi.create({ ...data, community: communityId })
      toast.success('Contribution pool created!')
      onSuccess()
    } catch {
      toast.error('Failed to create contribution')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
      <div className="col-span-2">
        <Input label="Title" value={data.title} onChange={e => upd('title', e.target.value)} placeholder="e.g. Monthly chama" autoFocus />
      </div>
      <div className="col-span-2">
        <Input label="Description (optional)" value={data.description} onChange={e => upd('description', e.target.value)} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium">Amount type</label>
        <select value={data.amount_type} onChange={e => upd('amount_type', e.target.value)}
          className="rounded border border-border px-3 py-3 text-base focus:outline-none focus:border-primary">
          <option value="fixed">Fixed amount</option>
          <option value="open">Open amount</option>
        </select>
      </div>

      {data.amount_type === 'fixed' && (
        <Input label="Amount (KES)" type="number" value={data.fixed_amount} onChange={e => upd('fixed_amount', e.target.value)} placeholder="5000" />
      )}

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium">Frequency</label>
        <select value={data.frequency} onChange={e => upd('frequency', e.target.value)}
          className="rounded border border-border px-3 py-3 text-base focus:outline-none focus:border-primary">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
          <option value="anytime">Anytime</option>
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium">Payout approval</label>
        <select value={data.voting_threshold} onChange={e => upd('voting_threshold', e.target.value)}
          className="rounded border border-border px-3 py-3 text-base focus:outline-none focus:border-primary">
          <option value="admins">Admins only</option>
          <option value="50">50% of members</option>
          <option value="100">All members</option>
        </select>
      </div>

      <div className="col-span-2 flex justify-end gap-3 pt-2">
        <Button type="submit" loading={loading}>Create Pool</Button>
      </div>
    </form>
  )
}
