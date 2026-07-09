'use client'
// Step-up (TOTP) gate for destructive levers (OP-3).
//
// useStepUp() returns { request, modal }. Call request() right before a flagged
// action; it resolves with a short-lived elevation token to pass to the API, or
// rejects if the operator cancels. On first use it walks the operator through
// enrolling an authenticator (secret + recovery codes); thereafter it just asks
// for a live code. The token authorises exactly one action and expires in minutes.
import { useCallback, useRef, useState } from 'react'
import { KeyRound, Loader2, ShieldCheck, X } from 'lucide-react'
import { apiError, isNotEnrolled, ops } from '@/lib/ops'

type Phase = 'idle' | 'prompt' | 'enroll' | 'recovery'

export function useStepUp() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [code, setCode] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [enroll, setEnroll] = useState<{ uri: string; secret: string; account: string } | null>(null)
  const [recovery, setRecovery] = useState<string[] | null>(null)
  const resolver = useRef<{ resolve: (t: string) => void; reject: (e: unknown) => void } | null>(null)

  const reset = () => { setCode(''); setErr(''); setBusy(false); setEnroll(null); setRecovery(null) }

  const request = useCallback((): Promise<string> => {
    reset(); setPhase('prompt')
    return new Promise<string>((resolve, reject) => { resolver.current = { resolve, reject } })
  }, [])

  const cancel = () => {
    resolver.current?.reject(new Error('step-up cancelled'))
    resolver.current = null
    setPhase('idle'); reset()
  }

  const finish = (token: string) => {
    resolver.current?.resolve(token)
    resolver.current = null
    setPhase('idle'); reset()
  }

  // Enrolled path: exchange a live code for an elevation token.
  const submitStepUp = async () => {
    setBusy(true); setErr('')
    try {
      const r = await ops.stepUp(code.trim())
      finish(r.data.token)
    } catch (e) {
      if (isNotEnrolled(e)) {
        try {
          const s = await ops.totpSetup()
          setEnroll({ uri: s.data.provisioning_uri, secret: s.data.secret, account: s.data.account })
          setCode(''); setPhase('enroll')
        } catch (e2) { setErr(apiError(e2)) }
      } else {
        setErr(apiError(e, "That code isn't valid."))
      }
    } finally { setBusy(false) }
  }

  // Enrolment: confirm the authenticator is in sync, then reveal recovery codes.
  const submitEnroll = async () => {
    setBusy(true); setErr('')
    try {
      const r = await ops.totpConfirm(code.trim())
      setRecovery(r.data.recovery_codes); setCode(''); setPhase('recovery')
    } catch (e) { setErr(apiError(e, "That code didn't match. Check your device clock.")) }
    finally { setBusy(false) }
  }

  const modal = phase === 'idle' ? null : (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-4 flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          <h2 className="text-base font-semibold">
            {phase === 'recovery' ? 'Save your recovery codes'
              : phase === 'enroll' ? 'Set up your authenticator'
              : 'Confirm it’s you'}
          </h2>
          <button onClick={cancel} className="ml-auto text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {phase === 'prompt' && (
          <>
            <p className="mb-4 text-sm text-slate-500">
              This action needs a fresh code from your authenticator app.
            </p>
            <CodeInput value={code} onChange={setCode} onEnter={submitStepUp} />
            {err && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{err}</p>}
            <Actions onCancel={cancel} onSubmit={submitStepUp} busy={busy} disabled={code.trim().length < 6} label="Verify" />
          </>
        )}

        {phase === 'enroll' && enroll && (
          <>
            <p className="mb-3 text-sm text-slate-500">
              Add this key to your authenticator app (Enter a setup key manually),
              then type the 6-digit code it shows.
            </p>
            <div className="mb-3">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Account</p>
              <p className="mb-2 text-sm text-slate-700 dark:text-slate-200">{enroll.account}</p>
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Setup key</p>
              <code className="block break-all rounded-lg bg-slate-100 px-3 py-2 font-mono text-sm tracking-wider text-slate-800 dark:bg-slate-800 dark:text-slate-100">
                {enroll.secret}
              </code>
            </div>
            <CodeInput value={code} onChange={setCode} onEnter={submitEnroll} />
            {err && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{err}</p>}
            <Actions onCancel={cancel} onSubmit={submitEnroll} busy={busy} disabled={code.trim().length < 6} label="Confirm" />
          </>
        )}

        {phase === 'recovery' && recovery && (
          <>
            <p className="mb-3 text-sm text-slate-500">
              Store these one-time codes somewhere safe. Each works once if you lose
              your authenticator. They won’t be shown again.
            </p>
            <div className="mb-4 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
              {recovery.map((c) => (
                <code key={c} className="font-mono text-sm text-slate-800 dark:text-slate-100">{c}</code>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => { setPhase('prompt'); setCode(''); setErr('') }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-blue-700">
                <KeyRound className="h-4 w-4" /> I’ve saved them
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )

  return { request, modal }
}

function CodeInput({ value, onChange, onEnter }: { value: string; onChange: (v: string) => void; onEnter: () => void }) {
  return (
    <input
      autoFocus inputMode="numeric" maxLength={8} value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, ''))}
      onKeyDown={(e) => { if (e.key === 'Enter' && value.trim().length >= 6) onEnter() }}
      placeholder="123456"
      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-center font-mono text-lg tracking-[0.4em] outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950"
    />
  )
}

function Actions({ onCancel, onSubmit, busy, disabled, label }: {
  onCancel: () => void; onSubmit: () => void; busy: boolean; disabled: boolean; label: string
}) {
  return (
    <div className="mt-4 flex justify-end gap-2">
      <button onClick={onCancel} disabled={busy}
        className="rounded-lg px-3.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
        Cancel
      </button>
      <button onClick={onSubmit} disabled={busy || disabled}
        className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}{label}
      </button>
    </div>
  )
}
