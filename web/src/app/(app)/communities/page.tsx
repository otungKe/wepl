'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Users, Plus, Search, Lock, Coins } from 'lucide-react'
import { communities, apiError, type Community } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { toast } from 'sonner'

export default function CommunitiesPage() {
  const [items, setItems] = useState<Community[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [joinOpen, setJoinOpen] = useState(false)

  async function load() {
    setLoading(true)
    try { setItems(await communities.mine()) }
    catch (err) { toast.error(apiError(err)) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const filtered = items.filter(c => c.name.toLowerCase().includes(q.toLowerCase()))

  return (
    <div>
      <PageHeader title="Communities" subtitle="Your savings groups and chamas"
        action={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setJoinOpen(true)}>Join</Button>
            <Button size="sm" onClick={() => setCreateOpen(true)}><Plus size={16} /> New</Button>
          </div>
        } />

      {items.length > 0 && (
        <div className="relative mb-4">
          <Search size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search communities"
            className="h-11 w-full rounded-lg border border-border bg-white pl-10 pr-3 text-base focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20" />
        </div>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState icon={Users} title="No communities yet"
          description="Create a community or join one with an invite to get started."
          action={<Button onClick={() => setCreateOpen(true)}><Plus size={16} /> Create community</Button>} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {filtered.map(c => (
            <Link key={c.id} href={`/community/${c.id}`}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface p-4 transition-shadow hover:shadow-card">
              <Avatar name={c.name} src={c.community_photo} size={48} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <p className="truncate font-semibold text-text">{c.name}</p>
                  {c.is_private && <Lock size={13} className="shrink-0 text-text-muted" />}
                </div>
                <p className="truncate text-sm text-text-muted">{c.member_count} members{c.location ? ` · ${c.location}` : ''}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {c.has_welfare_fund && <Badge tone="success">Welfare</Badge>}
                  {c.has_shares_fund && <Badge tone="warning"><Coins size={11} /> Shares</Badge>}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      <CreateModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={load} />
      <JoinModal open={joinOpen} onClose={() => setJoinOpen(false)} onJoined={load} />
    </div>
  )
}

function CreateModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPrivate, setIsPrivate] = useState(false)
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!name.trim()) return toast.error('Enter a community name')
    setLoading(true)
    try {
      await communities.create({ name, description, is_private: isPrivate })
      toast.success('Community created'); onClose(); setName(''); setDescription(''); onCreated()
    } catch (err) { toast.error(apiError(err)) } finally { setLoading(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="New community">
      <div className="flex flex-col gap-4">
        <Input label="Name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Westlands Chama" autoFocus />
        <Input label="Description" value={description} onChange={e => setDescription(e.target.value)} placeholder="What is this group about?" />
        <label className="flex items-center gap-2 text-sm text-text-secondary">
          <input type="checkbox" checked={isPrivate} onChange={e => setIsPrivate(e.target.checked)} className="h-4 w-4 accent-primary" />
          Private (join by invite only)
        </label>
        <Button onClick={submit} loading={loading} fullWidth>Create community</Button>
      </div>
    </Modal>
  )
}

function JoinModal({ open, onClose, onJoined }: { open: boolean; onClose: () => void; onJoined: () => void }) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!code.trim()) return toast.error('Enter an invite code')
    setLoading(true)
    try {
      await communities.requestByInvite(code.trim())
      toast.success('Request sent'); onClose(); setCode(''); onJoined()
    } catch (err) { toast.error(apiError(err, 'Invalid invite code')) } finally { setLoading(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Join with invite code">
      <div className="flex flex-col gap-4">
        <Input label="Invite code" value={code} onChange={e => setCode(e.target.value)} placeholder="e.g. AB12CD" autoFocus />
        <Button onClick={submit} loading={loading} fullWidth>Request to join</Button>
      </div>
    </Modal>
  )
}
