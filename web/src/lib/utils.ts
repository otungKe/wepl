import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Where to send a user after sign-in / registration. Verified (Tier 1) users
 * land in Communities; unverified (Tier 0) users land on Profile — the only
 * surface open to them until they verify (ADR-0022). Keeps post-auth redirects
 * from bouncing off the app-layout tier guard.
 */
export function landingPath(kycStatus?: string): string {
  return kycStatus === 'approved' ? '/communities' : '/profile'
}

export function formatMoney(amount: number | string, currency = 'KES'): string {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount
  return `${currency} ${n.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
}

export function formatRelative(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1)   return 'just now'
  if (minutes < 60)  return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24)    return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7)      return `${days}d ago`
  return formatDate(dateStr)
}

export function truncate(str: string, len: number): string {
  return str.length > len ? str.slice(0, len) + '…' : str
}
