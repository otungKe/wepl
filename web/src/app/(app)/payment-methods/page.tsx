'use client'
import { useCallback, useEffect, useState } from 'react'
import { Plus, Smartphone, CreditCard, Landmark, Star, Trash2, type LucideIcon } from 'lucide-react'
import { paymentMethodsApi, apiError, type PaymentMethod, type PaymentKind } from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Input } from '@/components/ui/Input'
import { EmptyState, ErrorState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

const KIND_ICON: Record<PaymentKind, LucideIcon> = {
  mpesa: Smartphone, card: CreditCard, bank: Landmark,
}

// Normalise a Kenyan number to 2547######## the way the auth screens do.
function normalizePhone(raw: string): string {
  const d = raw.replace(/\D/g, '')
  if (d.startsWith('0')) return '254' + d.slice(1)
  if (d.startsWith('7') || d.startsWith('1')) return '254' + d
  return d
}

export default function PaymentMethodsPage() {
  const [items, setItems] = useState<PaymentMethod[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)

  const [open, setOpen] = useState(false)
  const [phone, setPhone] = useState('')
  const [label, setLabel] = useState('')
  const [makeDefault, setMakeDefault] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setItems(await paymentMethodsApi.list()) }
    catch (e) { setError(apiError(e)) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  async function link(e: React.FormEvent) {
    e.preventDefault()
    const p = normalizePhone(phone)
    if (!/^2547\d{8}$/.test(p)) { toast.error('Enter a valid Kenyan M-Pesa number'); return }
    setSaving(true)
    try {
      await paymentMethodsApi.linkMpesa(p, { label: label.trim() || undefined, is_default: makeDefault })
      toast.success('M-Pesa number linked')
      setOpen(false); setPhone(''); setLabel(''); setMakeDefault(false)
      await load()
    } catch (e) { toast.error(apiError(e)) }
    finally { setSaving(false) }
  }

  async function setDefault(m: PaymentMethod) {
    setBusy(m.id)
    try { await paymentMethodsApi.setDefault(m.id); await load(); toast.success('Default updated') }
    catch (e) { toast.error(apiError(e)) }
    finally { setBusy(null) }
  }

  async function remove(m: PaymentMethod) {
    if (!window.confirm(`Remove ${m.display || m.label}?`)) return
    setBusy(m.id)
    try {
      await paymentMethodsApi.remove(m.id)
      setItems(prev => prev.filter(x => x.id !== m.id))
      toast.success('Payment method removed')
    } catch (e) { toast.error(apiError(e)) }
    finally { setBusy(null) }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Payment methods"
        subtitle="Where your payouts are sent"
        back="/settings"
        action={<Button onClick={() => setOpen(true)}><Plus size={16} /> Link M-Pesa</Button>}
      />

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border border-border p-4">
              <Skeleton className="h-10 w-10 rounded-lg" />
              <div className="flex-1 space-y-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-3 w-1/4" /></div>
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState description={error} onRetry={load} retrying={loading} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Smartphone}
          title="No payment methods yet"
          description="Link your M-Pesa number so payouts and disbursements reach you."
          action={<Button onClick={() => setOpen(true)}><Plus size={16} /> Link M-Pesa</Button>}
        />
      ) : (
        <div className="space-y-3">
          {items.map(m => {
            const Icon = KIND_ICON[m.kind] ?? Smartphone
            const unavailable = m.status === 'unavailable'
            return (
              <div key={m.id} className={cn('flex items-center gap-3 rounded-lg border border-border bg-surface p-4', unavailable && 'opacity-60')}>
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-semibold text-text">{m.display || m.label || m.kind_label}</p>
                    {m.is_default && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-primary-pale px-2 py-0.5 text-[11px] font-semibold text-primary">
                        <Star size={11} /> Default
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-text-muted">{m.kind_label}{m.label && m.display !== m.label ? ` · ${m.label}` : ''}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {!m.is_default && !unavailable && (
                    <Button variant="ghost" size="sm" loading={busy === m.id} onClick={() => setDefault(m)}>
                      Make default
                    </Button>
                  )}
                  <button
                    onClick={() => remove(m)}
                    disabled={busy === m.id}
                    title="Remove"
                    className="rounded-lg p-1.5 text-text-muted hover:bg-divider hover:text-error disabled:opacity-50"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="Link M-Pesa number">
        <form onSubmit={link} className="space-y-4">
          <Input label="M-Pesa phone number" type="tel" inputMode="numeric" autoFocus
            value={phone} onChange={e => setPhone(e.target.value)} placeholder="07XX XXX XXX" />
          <Input label="Label (optional)" value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. My Safaricom line" />
          <label className="flex items-center gap-2 text-sm text-text-secondary">
            <input type="checkbox" checked={makeDefault} onChange={e => setMakeDefault(e.target.checked)} className="h-4 w-4 rounded border-border text-primary" />
            Set as default payout method
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Link number</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
