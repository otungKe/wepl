'use client'
import { useCallback, useEffect, useState } from 'react'
import { Monitor, Smartphone, Laptop, LogOut, ShieldCheck } from 'lucide-react'
import { sessionsApi, apiError, type UserSession } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState, ErrorState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { formatRelative, cn } from '@/lib/utils'
import { toast } from 'sonner'

function deviceIcon(label: string) {
  const l = (label || '').toLowerCase()
  if (/iphone|android|phone|mobile/.test(l)) return Smartphone
  if (/mac|windows|linux|laptop/.test(l)) return Laptop
  return Monitor
}

export default function SessionsPage() {
  const [items, setItems] = useState<UserSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null) // sid being revoked, or 'others'

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await sessionsApi.list())
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function revoke(s: UserSession) {
    if (!window.confirm(`Sign out “${s.device_label || 'this device'}”? It will need to log in again.`)) return
    setBusy(s.sid)
    try {
      await sessionsApi.revoke(s.sid)
      setItems(prev => prev.filter(x => x.sid !== s.sid))
      toast.success('Device signed out')
    } catch (e) {
      toast.error(apiError(e))
    } finally {
      setBusy(null)
    }
  }

  async function revokeOthers() {
    if (!window.confirm('Sign out of every other device? Only this device will stay signed in.')) return
    setBusy('others')
    try {
      const n = await sessionsApi.revokeOthers()
      toast.success(n ? `Signed out ${n} other device${n === 1 ? '' : 's'}.` : 'No other devices were signed in.')
      await load()
    } catch (e) {
      toast.error(apiError(e))
    } finally {
      setBusy(null)
    }
  }

  // Current device first, then most-recently-seen.
  const sorted = [...items].sort((a, b) => {
    if (a.is_current !== b.is_current) return a.is_current ? -1 : 1
    return new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime()
  })
  const others = items.filter(s => !s.is_current).length

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Active devices" subtitle="Where your account is signed in" back="/settings" />

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border border-border p-4">
              <Skeleton className="h-10 w-10 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState description={error} onRetry={load} retrying={loading} />
      ) : sorted.length === 0 ? (
        <EmptyState icon={ShieldCheck} title="No active sessions" description="Nothing is signed in right now." />
      ) : (
        <>
          <div className="space-y-3">
            {sorted.map(s => {
              const Icon = deviceIcon(s.device_label)
              return (
                <div
                  key={s.sid}
                  className={cn(
                    'flex items-center gap-3 rounded-lg border p-4',
                    s.is_current ? 'border-primary/40 bg-primary-pale/40' : 'border-border bg-surface',
                  )}
                >
                  <div className={cn(
                    'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                    s.is_current ? 'bg-primary/10 text-primary' : 'bg-divider text-text-secondary',
                  )}>
                    <Icon size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate font-semibold text-text">{s.device_label || 'Unknown device'}</p>
                      {s.is_current && (
                        <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-semibold text-white">This device</span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-text-muted">
                      {s.ip_address ? `${s.ip_address} · ` : ''}Active {formatRelative(s.last_seen_at)}
                    </p>
                  </div>
                  {!s.is_current && (
                    <Button variant="ghost" size="sm" loading={busy === s.sid} onClick={() => revoke(s)}>
                      <LogOut size={15} /> Sign out
                    </Button>
                  )}
                </div>
              )
            })}
          </div>

          {others > 0 && (
            <div className="mt-5 border-t border-divider pt-5">
              <Button variant="danger" loading={busy === 'others'} onClick={revokeOthers}>
                <LogOut size={16} /> Sign out all other devices
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
