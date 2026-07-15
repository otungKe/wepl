'use client'
import { useCallback, useEffect, useState } from 'react'
import { Download, ExternalLink, ShieldCheck } from 'lucide-react'
import { privacyApi, apiError, type PrivacyPreferences, type Visibility } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Select } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { PageLoader } from '@/components/ui/Spinner'
import { ErrorState } from '@/components/ui/EmptyState'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

const VIS_OPTS: { value: Visibility; label: string }[] = [
  { value: 'everyone', label: 'Everyone' },
  { value: 'members',  label: 'My communities only' },
  { value: 'nobody',   label: 'Only me' },
]

const VIS_ROWS: { key: keyof PrivacyPreferences; label: string; desc: string }[] = [
  { key: 'phone_visibility',        label: 'Phone number',        desc: 'Who can see your phone number' },
  { key: 'photo_visibility',        label: 'Profile photo',       desc: 'Who can see your profile photo' },
  { key: 'contribution_visibility', label: 'Contribution history', desc: 'Who can see what you contribute' },
]

function Toggle({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className={cn('relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50', on ? 'bg-primary' : 'bg-border')}>
      <span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform', on ? 'translate-x-[22px]' : 'translate-x-0.5')} />
    </button>
  )
}

export default function PrivacyPage() {
  const [prefs, setPrefs] = useState<PrivacyPreferences | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savingKey, setSavingKey] = useState<keyof PrivacyPreferences | null>(null)
  const [exporting, setExporting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setPrefs(await privacyApi.get()) }
    catch (e) { setError(apiError(e)) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  // Optimistic patch; revert on failure.
  async function update<K extends keyof PrivacyPreferences>(key: K, value: PrivacyPreferences[K]) {
    if (!prefs) return
    const prev = prefs
    setPrefs({ ...prefs, [key]: value })
    setSavingKey(key)
    try {
      const saved = await privacyApi.update({ [key]: value } as Partial<PrivacyPreferences>)
      setPrefs(saved)
    } catch (e) {
      setPrefs(prev)
      toast.error(apiError(e))
    } finally {
      setSavingKey(null)
    }
  }

  async function exportData() {
    setExporting(true)
    try {
      const data = await privacyApi.exportData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `wepl-data-export-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
      toast.success('Your data has been downloaded')
    } catch (e) {
      toast.error(apiError(e))
    } finally {
      setExporting(false)
    }
  }

  if (loading) return <PageLoader />
  if (error || !prefs) return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Privacy" back="/settings" />
      <ErrorState description={error ?? 'Could not load privacy settings.'} onRetry={load} />
    </div>
  )

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Privacy" subtitle="Control who sees what, and export your data" back="/settings" />

      {/* Visibility */}
      <h2 className="mb-3 font-semibold text-text">Who can see</h2>
      <div className="space-y-3">
        {VIS_ROWS.map(row => (
          <div key={row.key} className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface p-4">
            <div className="min-w-0">
              <p className="font-medium text-text">{row.label}</p>
              <p className="text-xs text-text-muted">{row.desc}</p>
            </div>
            <div className="w-48 shrink-0">
              <Select
                value={prefs[row.key] as Visibility}
                disabled={savingKey === row.key}
                onChange={e => update(row.key, e.target.value as Visibility)}
              >
                {VIS_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </div>
          </div>
        ))}
      </div>

      {/* Discovery & presence */}
      <h2 className="mb-3 mt-8 font-semibold text-text">Discovery &amp; presence</h2>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface p-4">
          <div className="min-w-0">
            <p className="font-medium text-text">Discoverable</p>
            <p className="text-xs text-text-muted">Let others find you to invite you to communities</p>
          </div>
          <Toggle on={prefs.discoverable} disabled={savingKey === 'discoverable'}
            onClick={() => update('discoverable', !prefs.discoverable)} />
        </div>
        <div className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface p-4">
          <div className="min-w-0">
            <p className="font-medium text-text">Show online status</p>
            <p className="text-xs text-text-muted">Show when you’re active in chats</p>
          </div>
          <Toggle on={prefs.show_online_status} disabled={savingKey === 'show_online_status'}
            onClick={() => update('show_online_status', !prefs.show_online_status)} />
        </div>
      </div>

      {/* Your data */}
      <h2 className="mb-3 mt-8 font-semibold text-text">Your data</h2>
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldCheck size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-medium text-text">Download my data</p>
            <p className="text-xs text-text-muted">Get a JSON copy of everything WEPL holds about you.</p>
          </div>
          <Button variant="secondary" size="sm" loading={exporting} onClick={exportData}>
            <Download size={15} /> Export
          </Button>
        </div>
        <a href="https://wepl.app/privacy" target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
          <ExternalLink size={14} /> Read our privacy policy
        </a>
      </div>
    </div>
  )
}
