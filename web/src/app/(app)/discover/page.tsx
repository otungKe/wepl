'use client'
import { useEffect, useState, useCallback } from 'react'
import { communities as commApi } from '@/lib/api'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageLoader } from '@/components/ui/Spinner'
import { Input } from '@/components/ui/Input'
import { Compass, Globe } from 'lucide-react'
import { toast } from 'sonner'
import Link from 'next/link'

interface Community {
  id: string; name: string; description: string; member_count: number; community_photo?: string
}

export default function DiscoverPage() {
  const [list, setList]       = useState<Community[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch]   = useState('')
  const [joining, setJoining] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const { data } = await commApi.discover()
      setList(data.results ?? data)
    } catch { toast.error('Failed to load communities') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = list.filter(c => c.name.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <div className="flex items-center gap-3 mb-6">
        <Globe size={22} className="text-primary" />
        <h1 className="text-2xl font-bold text-text">Discover</h1>
      </div>

      <Input
        placeholder="Search public communities…"
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="mb-4"
      />

      {loading ? <PageLoader /> : filtered.length === 0 ? (
        <EmptyState icon={Compass} title="No communities found" description="Try a different search term." />
      ) : (
        <div className="space-y-3">
          {filtered.map(c => (
            <div key={c.id} className="flex items-center gap-4 bg-white rounded-lg px-4 py-4 shadow-card">
              <Avatar name={c.name} src={c.community_photo} size="lg" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-text">{c.name}</p>
                {c.description && <p className="text-sm text-text-secondary mt-0.5 line-clamp-2">{c.description}</p>}
                <p className="text-xs text-text-muted mt-1">{c.member_count} members</p>
              </div>
              <Button
                size="sm" variant="secondary"
                loading={joining === c.id}
                onClick={async () => {
                  setJoining(c.id)
                  try {
                    // Public discovery join uses community id
                    await commApi.join(c.id)
                    toast.success('Join request sent!')
                  } catch { toast.error('Could not send request') }
                  finally { setJoining(null) }
                }}
              >
                Request
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
