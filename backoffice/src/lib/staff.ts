/** Human, first-name representation of a staff member anywhere the console
 * greets or displays one. Accepts a display name ("Harry Onyango"), a
 * corporate email (harry.otung@wepl.co.ke) or an ops actor label
 * (ops:harry.otung@wepl.co.ke) and returns "Harry". */
export function staffFirstName(raw?: string | null): string {
  if (!raw) return ''
  const cleaned = raw.replace(/^ops:/, '').trim()
  const base = cleaned.includes('@') ? cleaned.split('@')[0] : cleaned
  const first = base.split(/[\s._-]+/)[0] || base
  return first ? first.charAt(0).toUpperCase() + first.slice(1) : ''
}
