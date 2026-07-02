'use client'
import { useEffect, useRef, useState } from 'react'
import { ShieldCheck, Clock, Upload, CheckCircle2 } from 'lucide-react'
import { auth, apiError } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { PageHeader } from '@/components/app/PageHeader'
import { Input, Select } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { PageLoader } from '@/components/ui/Spinner'
import { toast } from 'sonner'

interface Choices {
  status: string
  counties: string[]
  income_bands: { value: string; label: string }[]
  income_sources: { value: string; label: string }[]
}

export default function KycPage() {
  const setUser = useAuthStore(s => s.setUser)
  const [choices, setChoices] = useState<Choices | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    given_names: '', surname: '', id_number: '', date_of_birth: '', email: '',
    physical_address: '', county: '', occupation: '', source_of_income: '', expected_monthly_income: '',
  })
  const idFront = useRef<HTMLInputElement | null>(null)
  const selfie = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    auth.kycStatus().then(r => setChoices(r.data)).catch(e => toast.error(apiError(e))).finally(() => setLoading(false))
  }, [])

  function set<K extends keyof typeof form>(k: K, v: string) { setForm(f => ({ ...f, [k]: v })) }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!idFront.current?.files?.[0]) return toast.error('Upload the front of your ID')
    const fd = new FormData()
    Object.entries(form).forEach(([k, v]) => v && fd.append(k, v))
    fd.append('id_front', idFront.current.files[0])
    if (selfie.current?.files?.[0]) fd.append('selfie', selfie.current.files[0])
    setSaving(true)
    try {
      await auth.kycSubmit(fd)
      const p = await auth.profile(); setUser(p.data)
      toast.success('Identity submitted for review')
      setChoices(c => c ? { ...c, status: 'pending' } : c)
    } catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }

  if (loading) return <PageLoader />
  const status = choices?.status

  if (status === 'approved') {
    return <StatusCard icon={CheckCircle2} tone="text-primary" title="Identity verified"
      desc="Your identity has been verified. You have full access to payments, contributions and community features." />
  }
  if (status === 'pending') {
    return <StatusCard icon={Clock} tone="text-accent" title="Verification in review"
      desc="We’ve received your documents and are reviewing them. You’ll be notified once a decision is made." />
  }

  return (
    <div className="max-w-lg">
      <PageHeader title="Verify your identity" subtitle="Required for payments and contributions (KYC)" />
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Given names" value={form.given_names} onChange={e => set('given_names', e.target.value)} required />
          <Input label="Surname" value={form.surname} onChange={e => set('surname', e.target.value)} required />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="National ID number" value={form.id_number} onChange={e => set('id_number', e.target.value)} required />
          <Input label="Date of birth" type="date" value={form.date_of_birth} onChange={e => set('date_of_birth', e.target.value)} required />
        </div>
        <Input label="Email" type="email" value={form.email} onChange={e => set('email', e.target.value)} required hint="Used to send a verification link." />
        <Input label="Physical address" value={form.physical_address} onChange={e => set('physical_address', e.target.value)} required />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="County" value={form.county} onChange={e => set('county', e.target.value)}>
            <option value="">Select county</option>
            {choices?.counties.map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
          <Input label="Occupation" value={form.occupation} onChange={e => set('occupation', e.target.value)} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Source of income" value={form.source_of_income} onChange={e => set('source_of_income', e.target.value)}>
            <option value="">Select source</option>
            {choices?.income_sources.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </Select>
          <Select label="Monthly income" value={form.expected_monthly_income} onChange={e => set('expected_monthly_income', e.target.value)}>
            <option value="">Select band</option>
            {choices?.income_bands.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
          </Select>
        </div>

        <FileField label="ID front (required)" inputRef={idFront} />
        <FileField label="Selfie (optional)" inputRef={selfie} />

        <Button type="submit" size="lg" loading={saving}><ShieldCheck size={16} /> Submit for verification</Button>
      </form>
    </div>
  )
}

function FileField({ label, inputRef }: { label: string; inputRef: React.RefObject<HTMLInputElement | null> }) {
  const [name, setName] = useState('')
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-text-secondary">{label}</span>
      <button type="button" onClick={() => inputRef.current?.click()}
        className="flex h-11 items-center gap-2 rounded-lg border border-dashed border-border bg-surface px-3.5 text-sm text-text-muted hover:bg-divider/40">
        <Upload size={16} /> {name || 'Choose an image'}
      </button>
      <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={e => setName(e.target.files?.[0]?.name ?? '')} />
    </div>
  )
}

function StatusCard({ icon: Icon, tone, title, desc }: { icon: typeof Clock; tone: string; title: string; desc: string }) {
  return (
    <div className="max-w-lg">
      <PageHeader title="Identity verification" />
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-surface px-6 py-12 text-center">
        <Icon size={44} className={tone} />
        <p className="text-lg font-bold text-text">{title}</p>
        <p className="max-w-sm text-sm text-text-muted">{desc}</p>
      </div>
    </div>
  )
}
