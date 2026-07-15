'use client'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Plus, Wallet, Heart, TrendingUp, Repeat, Pencil, Trash2, Bell,
  Power, type LucideIcon,
} from 'lucide-react'
import {
  reminders as remindersApi, apiError,
  type Reminder, type ReminderType, type Recurrence,
} from '@/lib/api'
import { PageHeader } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Input, Textarea, Select } from '@/components/ui/Input'
import { EmptyState, ErrorState } from '@/components/ui/EmptyState'
import { Skeleton } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

// ── Type presentation (mirrors the mobile reminders screen) ───────────────────
type Tone = 'success' | 'danger' | 'warning' | 'info' | 'neutral'

const TONE_CLASSES: Record<Tone, string> = {
  success: 'bg-primary-pale text-primary',
  danger:  'bg-error/10 text-error',
  warning: 'bg-accent-pale text-accent',
  info:    'bg-info/10 text-info',
  neutral: 'bg-divider text-text-secondary',
}

const TYPE_META: Record<ReminderType, { icon: LucideIcon; tone: Tone; label: string }> = {
  contribution_due:  { icon: Wallet,     tone: 'success', label: 'Contribution' },
  welfare_contrib:   { icon: Heart,      tone: 'danger',  label: 'Welfare' },
  advance_repayment: { icon: TrendingUp, tone: 'warning', label: 'Repayment' },
  standing_order:    { icon: Repeat,     tone: 'info',    label: 'Standing order' },
  custom:            { icon: Pencil,     tone: 'neutral', label: 'Custom' },
}

const TYPE_OPTS = Object.entries(TYPE_META).map(([value, m]) => ({ value: value as ReminderType, label: m.label }))

const RECURRENCE_OPTS: { value: Recurrence; label: string }[] = [
  { value: 'none',    label: 'Once' },
  { value: 'daily',   label: 'Daily' },
  { value: 'weekly',  label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
]
const RECURRENCE_LABEL: Record<Recurrence, string> = {
  none: 'Once', daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly',
}

// ── Datetime helpers (bridge ISO ↔ <input type="datetime-local">) ─────────────
const pad = (n: number) => String(n).padStart(2, '0')

function isoToLocalInput(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function localInputToISO(local: string): string {
  return new Date(local).toISOString()
}
function fmtDateTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-KE', {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}
function defaultSchedule(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  d.setHours(9, 0, 0, 0)
  return isoToLocalInput(d.toISOString())
}

// ── Form state ────────────────────────────────────────────────────────────────
type FormState = {
  reminder_type: ReminderType
  title: string
  note: string
  scheduledLocal: string
  recurrence: Recurrence
}
const EMPTY_FORM: FormState = {
  reminder_type: 'custom', title: '', note: '', scheduledLocal: defaultSchedule(), recurrence: 'none',
}

export default function RemindersPage() {
  const [items, setItems] = useState<Reminder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Reminder | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await remindersApi.list(false)) // false = include inactive
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Soonest first; overdue (past next_fire_at) naturally sorts to the top.
  const sorted = useMemo(
    () => [...items].sort((a, b) => new Date(a.next_fire_at).getTime() - new Date(b.next_fire_at).getTime()),
    [items],
  )

  function openCreate() {
    setEditing(null)
    setForm({ ...EMPTY_FORM, scheduledLocal: defaultSchedule() })
    setOpen(true)
  }
  function openEdit(r: Reminder) {
    setEditing(r)
    setForm({
      reminder_type: r.reminder_type,
      title: r.title,
      note: r.note ?? '',
      scheduledLocal: isoToLocalInput(r.scheduled_for),
      recurrence: r.recurrence,
    })
    setOpen(true)
  }

  async function submit() {
    if (!form.title.trim()) { toast.error('Give the reminder a title.'); return }
    if (!form.scheduledLocal) { toast.error('Pick a date and time.'); return }
    setSaving(true)
    try {
      const scheduled_for = localInputToISO(form.scheduledLocal)
      if (editing) {
        await remindersApi.update(editing.id, {
          title: form.title.trim(),
          note: form.note.trim(),
          scheduled_for,
          recurrence: form.recurrence,
        })
        toast.success('Reminder updated')
      } else {
        await remindersApi.create({
          reminder_type: form.reminder_type,
          title: form.title.trim(),
          note: form.note.trim() || undefined,
          scheduled_for,
          recurrence: form.recurrence,
        })
        toast.success('Reminder created')
      }
      setOpen(false)
      await load()
    } catch (e) {
      toast.error(apiError(e))
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive(r: Reminder) {
    setBusyId(r.id)
    // Optimistic flip; revert on failure.
    setItems(prev => prev.map(x => (x.id === r.id ? { ...x, is_active: !x.is_active } : x)))
    try {
      await remindersApi.update(r.id, { is_active: !r.is_active })
    } catch (e) {
      setItems(prev => prev.map(x => (x.id === r.id ? { ...x, is_active: r.is_active } : x)))
      toast.error(apiError(e))
    } finally {
      setBusyId(null)
    }
  }

  async function remove(r: Reminder) {
    if (!window.confirm(`Delete “${r.title}”?`)) return
    setBusyId(r.id)
    try {
      await remindersApi.remove(r.id)
      setItems(prev => prev.filter(x => x.id !== r.id))
      toast.success('Reminder deleted')
    } catch (e) {
      toast.error(apiError(e))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Reminders"
        subtitle="Nudges for contributions, repayments and your own to-dos"
        action={<Button onClick={openCreate}><Plus size={16} /> New reminder</Button>}
      />

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-start gap-3 rounded-lg border border-border p-4">
              <Skeleton className="h-10 w-10 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-2/3" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState description={error} onRetry={load} retrying={loading} />
      ) : sorted.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No reminders yet"
          description="Create a reminder so WEPL nudges you before a contribution is due or a repayment lands."
          action={<Button onClick={openCreate}><Plus size={16} /> New reminder</Button>}
        />
      ) : (
        <div className="space-y-3">
          {sorted.map(r => {
            const meta = TYPE_META[r.reminder_type] ?? TYPE_META.custom
            const Icon = meta.icon
            const overdue = r.is_overdue && r.is_active
            return (
              <div
                key={r.id}
                className={cn(
                  'flex items-start gap-3 rounded-lg border p-4 transition-colors',
                  overdue ? 'border-error/40 bg-error/5' : 'border-border bg-surface',
                  !r.is_active && 'opacity-60',
                )}
              >
                <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-lg', TONE_CLASSES[meta.tone])}>
                  <Icon size={18} />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-semibold text-text">{r.title}</p>
                    {overdue && (
                      <span className="rounded-full bg-error/10 px-2 py-0.5 text-[11px] font-semibold text-error">Overdue</span>
                    )}
                    {!r.is_active && (
                      <span className="rounded-full bg-divider px-2 py-0.5 text-[11px] font-semibold text-text-muted">Paused</span>
                    )}
                  </div>
                  {r.note && <p className="mt-0.5 text-sm text-text-secondary">{r.note}</p>}
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
                    <span className="font-medium text-text-secondary">{meta.label}</span>
                    <span>{fmtDateTime(r.scheduled_for)}</span>
                    {r.recurrence !== 'none' && <span>· {RECURRENCE_LABEL[r.recurrence]}</span>}
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => toggleActive(r)}
                    disabled={busyId === r.id}
                    title={r.is_active ? 'Pause' : 'Resume'}
                    className={cn(
                      'rounded-lg p-1.5 hover:bg-divider disabled:opacity-50',
                      r.is_active ? 'text-primary' : 'text-text-muted',
                    )}
                  >
                    <Power size={16} />
                  </button>
                  <button
                    onClick={() => openEdit(r)}
                    title="Edit"
                    className="rounded-lg p-1.5 text-text-muted hover:bg-divider hover:text-text"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => remove(r)}
                    disabled={busyId === r.id}
                    title="Delete"
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

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? 'Edit reminder' : 'New reminder'}>
        <form
          className="space-y-4"
          onSubmit={e => { e.preventDefault(); submit() }}
        >
          {!editing && (
            <Select
              label="Type"
              value={form.reminder_type}
              onChange={e => setForm(f => ({ ...f, reminder_type: e.target.value as ReminderType }))}
            >
              {TYPE_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          )}
          <Input
            label="Title"
            required
            autoFocus
            value={form.title}
            onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            placeholder="e.g. Pay monthly contribution"
          />
          <Textarea
            label="Note"
            value={form.note}
            onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
            placeholder="Optional details"
            rows={2}
          />
          <Input
            label="When"
            type="datetime-local"
            required
            value={form.scheduledLocal}
            onChange={e => setForm(f => ({ ...f, scheduledLocal: e.target.value }))}
          />
          <Select
            label="Repeat"
            value={form.recurrence}
            onChange={e => setForm(f => ({ ...f, recurrence: e.target.value as Recurrence }))}
          >
            {RECURRENCE_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>{editing ? 'Save changes' : 'Create reminder'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
