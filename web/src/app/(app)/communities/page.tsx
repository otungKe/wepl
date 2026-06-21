'use client'
import { useEffect, useState, useCallback } from 'react'
import { communities as communitiesApi } from '@/lib/api'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { KYCBanner } from '@/components/ui/KYCBanner'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { useAuthStore } from '@/store/auth'
import { Users, Plus, Hash, Lock, Globe } from 'lucide-react'
import Link from 'next/link'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface Community {
  id: string
  name: string
  description: string
  member_count: number
  is_private: boolean
  community_photo?: string
  unread_count?: number
  my_role?: string
}

export default function CommunitiesPage() {
  const user = useAuthStore(s => s.user)
  const [list, setList]         = useState<Community[]>([])
  const [loading, setLoading]   = useState(true)
  const [search, setSearch]     = useState('')
  const [showJoin, setShowJoin] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [inviteCode, setInviteCode] = useState('')
  const [joining, setJoining]   = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await communitiesApi.list()
      setList(data.results ?? data)
    } catch {
      toast.error('Failed to load communities')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleJoin() {
    if (!inviteCode.trim()) return
    setJoining(true)
    try {
      await communitiesApi.join(inviteCode.trim().toUpperCase())
      toast.success('Join request sent!')
      setShowJoin(false)
      setInviteCode('')
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg ?? 'Invalid invite code')
    } finally {
      setJoining(false)
    }
  }

  const filtered = list.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase())
  )

  const isVerified = user?.kyc_status === 'approved'

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-text">Communities</h1>
        {isVerified && (
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setShowJoin(true)}>
              <Hash size={15} /> Join
            </Button>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus size={15} /> New
            </Button>
          </div>
        )}
      </div>

      {/* KYC banner */}
      {user && user.kyc_status !== 'approved' && (
        <div className="mb-4">
          <KYCBanner status={user.kyc_status} />
        </div>
      )}

      {/* Search */}
      <Input
        placeholder="Search communities…"
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="mb-4"
      />

      {/* List */}
      {loading ? (
        <PageLoader />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No communities yet"
          description={isVerified ? 'Join with an invite code or create a new one.' : 'Complete verification to join or create communities.'}
          action={isVerified ? (
            <Button size="sm" onClick={() => setShowJoin(true)}>
              <Hash size={15} /> Join with code
            </Button>
          ) : undefined}
        />
      ) : (
        <div className="space-y-2">
          {filtered.map(c => (
            <Link key={c.id} href={`/community/${c.id}`}>
              <div className={cn(
                'flex items-center gap-4 bg-white rounded-lg px-4 py-3.5 shadow-card',
                'hover:shadow-md transition-shadow cursor-pointer'
              )}>
                <Avatar name={c.name} src={c.community_photo} size="md" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="font-semibold text-text truncate">{c.name}</p>
                    {c.is_private
                      ? <Lock size={12} className="text-text-muted flex-shrink-0" />
                      : <Globe size={12} className="text-text-muted flex-shrink-0" />
                    }
                  </div>
                  <p className="text-sm text-text-secondary truncate mt-0.5">{c.description || `${c.member_count} members`}</p>
                </div>
                {c.unread_count ? (
                  <span className="bg-primary text-white text-xs font-bold rounded-full min-w-[20px] h-5 flex items-center justify-center px-1.5">
                    {c.unread_count > 99 ? '99+' : c.unread_count}
                  </span>
                ) : null}
                <span className="text-xs text-text-muted">{c.member_count} members</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Join modal */}
      <Modal open={showJoin} onClose={() => setShowJoin(false)} title="Join a Community">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-secondary">Enter the invite code shared by the community admin.</p>
          <Input
            label="Invite code"
            placeholder="e.g. A3F9K2B1C0"
            value={inviteCode}
            onChange={e => setInviteCode(e.target.value.toUpperCase())}
            autoFocus
          />
          <div className="flex gap-3 justify-end">
            <Button variant="secondary" onClick={() => setShowJoin(false)}>Cancel</Button>
            <Button onClick={handleJoin} loading={joining}>Send Request</Button>
          </div>
        </div>
      </Modal>

      {/* Create modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New Community">
        <CreateCommunityForm onSuccess={() => { setShowCreate(false); load() }} />
      </Modal>
    </div>
  )
}

function CreateCommunityForm({ onSuccess }: { onSuccess: () => void }) {
  const [name, setName]         = useState('')
  const [desc, setDesc]         = useState('')
  const [isPrivate, setPrivate] = useState(true)
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    try {
      await communitiesApi.create({ name, description: desc, is_private: isPrivate })
      toast.success('Community created!')
      onSuccess()
    } catch {
      toast.error('Failed to create community')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input label="Name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Westlands Chama" autoFocus />
      <Input label="Description (optional)" value={desc} onChange={e => setDesc(e.target.value)} placeholder="What is this community about?" />
      <label className="flex items-center gap-3 cursor-pointer">
        <input type="checkbox" checked={isPrivate} onChange={e => setPrivate(e.target.checked)}
          className="w-4 h-4 accent-primary" />
        <span className="text-sm text-text">Private (invite-only)</span>
      </label>
      <div className="flex gap-3 justify-end pt-2">
        <Button type="submit" loading={loading}>Create</Button>
      </div>
    </form>
  )
}
