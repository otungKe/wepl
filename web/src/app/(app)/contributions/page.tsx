'use client'
import { useCallback, useEffect, useState } from 'react'
import { Coins } from 'lucide-react'
import { contributions, apiError, type Contribution } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { ContributionCard } from '@/components/app/ContributionCard'
import { Tabs } from '@/components/ui/Tabs'
import { EmptyState, ErrorState } from '@/components/ui/EmptyState'
import { CardSkeleton } from '@/components/ui/Spinner'

type Tab = 'mine' | 'open'

export default function ContributionsPage() {
  const [tab, setTab] = useState<Tab>('mine')
  const [mine, setMine] = useState<Contribution[]>([])
  const [open, setOpen] = useState<Contribution[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [m, o] = await Promise.all([contributions.mine(), contributions.open()])
      setMine(m)
      setOpen(o)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const list = tab === 'mine' ? mine : open

  return (
    <div>
      <PageHeader title="Contributions" subtitle="Savings pools, ROSCAs and welfare you're part of" />

      <Tabs
        className="mb-4"
        active={tab}
        onChange={k => setTab(k as Tab)}
        tabs={[
          { key: 'mine', label: 'My pools', badge: mine.length || undefined },
          { key: 'open', label: 'Open to join' },
        ]}
      />

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : error ? (
        <ErrorState onRetry={() => { setLoading(true); load() }} />
      ) : list.length === 0 ? (
        <EmptyState
          icon={Coins}
          title={tab === 'mine' ? 'No contributions yet' : 'Nothing open right now'}
          description={tab === 'mine'
            ? 'Pools you join or create will appear here.'
            : 'There are no open pools to join at the moment.'}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {list.map(c => <ContributionCard key={c.id} c={c} />)}
        </div>
      )}
    </div>
  )
}
