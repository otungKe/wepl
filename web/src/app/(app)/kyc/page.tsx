'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { auth } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ArrowLeft, ArrowRight, Check, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

const STEPS = [
  { id: 1, label: 'Personal Info' },
  { id: 2, label: 'Photo' },
  { id: 3, label: 'Documents' },
  { id: 4, label: 'Review' },
]

export default function KycPage() {
  const router = useRouter()
  const { user, setUser } = useAuthStore()
  const [step, setStep]   = useState(1)
  const [loading, setLoading] = useState(false)

  const [form, setForm] = useState({
    first_name: '', last_name: '', id_number: '', date_of_birth: '',
    selfie: null as File | null, id_front: null as File | null, id_back: null as File | null,
  })

  const upd = (k: string, v: string | File | null) => setForm(f => ({ ...f, [k]: v }))

  async function handleSubmit() {
    setLoading(true)
    try {
      const fd = new FormData()
      Object.entries(form).forEach(([k, v]) => {
        if (v !== null) fd.append(k, v as string | Blob)
      })
      const { data } = await auth.kycSubmit(fd)
      if (user) setUser({ ...user, kyc_status: 'pending' })
      toast.success('Verification submitted! We\'ll review within 24 hours.')
      router.push('/profile')
    } catch {
      toast.error('Submission failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (user?.kyc_status === 'approved') {
    return (
      <div className="max-w-md mx-auto px-4 py-16 text-center">
        <div className="w-16 h-16 rounded-full bg-primary-pale flex items-center justify-center mx-auto mb-4">
          <ShieldCheck size={28} className="text-primary" />
        </div>
        <h1 className="text-2xl font-bold text-text mb-2">You&apos;re verified!</h1>
        <p className="text-text-secondary mb-6">Your identity has been successfully verified. You have full access to all WEPL features.</p>
        <Button onClick={() => router.push('/communities')}>Go to Communities</Button>
      </div>
    )
  }

  return (
    <div className="max-w-lg mx-auto px-4 py-6">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => step > 1 ? setStep(s => s - 1) : router.back()}
          className="p-1.5 rounded-lg hover:bg-divider text-text-secondary">
          <ArrowLeft size={18} />
        </button>
        <h1 className="text-xl font-bold text-text">Identity Verification</h1>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-0 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center flex-1">
            <div className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold flex-shrink-0 transition-colors',
              s.id < step ? 'bg-primary text-white'
                : s.id === step ? 'bg-primary text-white'
                : 'bg-divider text-text-muted'
            )}>
              {s.id < step ? <Check size={14} /> : s.id}
            </div>
            {i < STEPS.length - 1 && (
              <div className={cn('flex-1 h-0.5', s.id < step ? 'bg-primary' : 'bg-divider')} />
            )}
          </div>
        ))}
      </div>

      <p className="text-text-secondary mb-6 text-sm">{STEPS[step-1].label}</p>

      {step === 1 && (
        <div className="flex flex-col gap-4">
          <Input label="First name" value={form.first_name} onChange={e => upd('first_name', e.target.value)} autoFocus />
          <Input label="Last name" value={form.last_name} onChange={e => upd('last_name', e.target.value)} />
          <Input label="National ID number" value={form.id_number} onChange={e => upd('id_number', e.target.value)} />
          <Input label="Date of birth" type="date" value={form.date_of_birth} onChange={e => upd('date_of_birth', e.target.value)} />
          <Button className="mt-2" onClick={() => setStep(2)}>
            Next <ArrowRight size={16} />
          </Button>
        </div>
      )}

      {step === 2 && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-text">Selfie photo</label>
            <p className="text-sm text-text-secondary">Take a clear photo of your face.</p>
            <label className="flex flex-col items-center justify-center border-2 border-dashed border-border rounded-lg p-8 cursor-pointer hover:bg-primary-pale transition-colors">
              {form.selfie
                ? <p className="text-sm text-primary font-medium">{form.selfie.name}</p>
                : <>
                    <div className="w-12 h-12 rounded-full bg-primary-pale flex items-center justify-center mb-2">
                      <ShieldCheck size={22} className="text-primary" />
                    </div>
                    <p className="text-sm text-text-secondary">Click to upload selfie</p>
                  </>
              }
              <input type="file" accept="image/*" className="hidden"
                onChange={e => upd('selfie', e.target.files?.[0] ?? null)} />
            </label>
          </div>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(1)}>Back</Button>
            <Button onClick={() => setStep(3)} disabled={!form.selfie}>Next <ArrowRight size={16} /></Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="flex flex-col gap-4">
          {(['id_front', 'id_back'] as const).map(field => (
            <div key={field} className="flex flex-col gap-2">
              <label className="text-sm font-medium text-text">
                {field === 'id_front' ? 'ID / Passport — Front' : 'ID / Passport — Back'}
              </label>
              <label className="flex flex-col items-center justify-center border-2 border-dashed border-border rounded-lg p-6 cursor-pointer hover:bg-primary-pale transition-colors">
                {form[field]
                  ? <p className="text-sm text-primary font-medium">{form[field]!.name}</p>
                  : <p className="text-sm text-text-secondary">Click to upload</p>
                }
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => upd(field, e.target.files?.[0] ?? null)} />
              </label>
            </div>
          ))}
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(2)}>Back</Button>
            <Button onClick={() => setStep(4)} disabled={!form.id_front || !form.id_back}>
              Next <ArrowRight size={16} />
            </Button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="flex flex-col gap-4">
          <div className="bg-primary-pale rounded-lg p-5">
            <p className="font-semibold text-primary mb-3">Review your submission</p>
            <div className="space-y-2 text-sm text-text-secondary">
              <p>Name: <span className="text-text font-medium">{form.first_name} {form.last_name}</span></p>
              <p>ID: <span className="text-text font-medium">{form.id_number}</span></p>
              <p>DOB: <span className="text-text font-medium">{form.date_of_birth}</span></p>
              <p>Selfie: <span className="text-text font-medium">{form.selfie?.name}</span></p>
              <p>ID docs: <span className="text-text font-medium">2 files attached</span></p>
            </div>
          </div>
          <p className="text-sm text-text-muted">
            By submitting, you confirm that all information is accurate and the documents belong to you.
          </p>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(3)}>Back</Button>
            <Button loading={loading} onClick={handleSubmit}>Submit Verification</Button>
          </div>
        </div>
      )}
    </div>
  )
}
