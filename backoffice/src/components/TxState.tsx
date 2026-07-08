export function TxState({ state }: { state: string }) {
  const m: Record<string, string> = {
    SUCCESS: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
    PENDING: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    PROCESSING: 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
    FAILED: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400',
    REVERSED: 'bg-slate-200 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300',
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${m[state] ?? 'bg-slate-100 text-slate-600'}`}>
      {state.toLowerCase()}
    </span>
  )
}
