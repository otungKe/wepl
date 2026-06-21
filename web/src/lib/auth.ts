import { jwtDecode } from 'jwt-decode'

interface TokenPayload {
  stage: 'active' | 'otp_verified' | 'otp_recovery'
  user_id: string
  exp: number
  phone_number?: string
}

export function decodeToken(token: string): TokenPayload | null {
  try { return jwtDecode<TokenPayload>(token) } catch { return null }
}

export function getStage(token: string): TokenPayload['stage'] | null {
  return decodeToken(token)?.stage ?? null
}

export function isTokenValid(token: string): boolean {
  const payload = decodeToken(token)
  if (!payload) return false
  return payload.exp * 1000 > Date.now()
}

export function saveTokens(access: string, refresh: string) {
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
}

export function clearTokens() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('access_token')
}

export function isAuthenticated(): boolean {
  const token = getAccessToken()
  return !!token && isTokenValid(token)
}
