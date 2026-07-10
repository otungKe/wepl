// Back Office API client. Staff-only: a dedicated ops JWT (separate from the
// customer app), stored under its own key, sent as a Bearer token. On 401 the
// operator is sent back to sign in — staff tokens don't silently refresh.
import axios from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'
const TOKEN_KEY = 'ops_token'

export const getToken = () =>
  typeof window === 'undefined' ? null : localStorage.getItem(TOKEN_KEY)
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

export const api = axios.create({ baseURL: BASE_URL, headers: { 'Content-Type': 'application/json' } })

api.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers['Authorization'] = `Bearer ${t}`
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      clearToken()
      if (!window.location.pathname.startsWith('/login')) window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

// Download a CSV export. Exports are staff-authed, so a plain <a download> can't
// carry the token — fetch as a blob through the api client, then save it.
export async function downloadCsv(
  path: string,
  params: Record<string, string | number | undefined> = {},
  fallbackName = 'export.csv',
): Promise<void> {
  const res = await api.get(path, { params, responseType: 'blob' })
  const url = URL.createObjectURL(new Blob([res.data as BlobPart], { type: 'text/csv' }))
  const cd = res.headers['content-disposition'] as string | undefined
  const a = document.createElement('a')
  a.href = url
  a.download = cd?.match(/filename="?([^"]+)"?/)?.[1] || fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function apiError(err: unknown, fallback = 'Something went wrong.'): string {
  if (axios.isAxiosError(err)) {
    const d = err.response?.data as { detail?: string } | undefined
    if (d?.detail) return d.detail
    if (!err.response) return 'Cannot reach the server.'
  }
  return fallback
}

export interface OpsMe {
  id: number; email: string; name: string; is_superuser: boolean
  must_change_password: boolean; totp_enrolled: boolean; roles: string[]; capabilities: string[]
}

// Step-up elevation token (X-Ops-StepUp). Spread into an axios call config to
// authorise a single flagged action (see stepup.py, OP-3).
export const stepUpConfig = (token: string) => ({ headers: { 'X-Ops-StepUp': token } })

// True when a request failed only because the operator hasn't enrolled TOTP yet.
export function isNotEnrolled(err: unknown): boolean {
  return axios.isAxiosError(err) &&
    (err.response?.data as { code?: string } | undefined)?.code === 'not_enrolled'
}
export type OpsResultType = 'user' | 'transaction' | 'community' | 'verification' | 'journal'
export interface OpsSearchResult { type: OpsResultType; id: number; label: string; sublabel: string; url: string }

export const ops = {
  login: (email: string, password: string) =>
    api.post<{ token: string; must_change_password: boolean; email: string; name: string }>(
      '/ops/auth/login/', { email, password }),
  changePassword: (current_password: string, new_password: string) =>
    api.post('/ops/auth/change-password/', { current_password, new_password }),
  me: () => api.get<OpsMe>('/ops/me/'),
  search: (q: string) => api.get<{ query: string; results: OpsSearchResult[]; counts: Record<string, number> }>(
    '/ops/search/', { params: { q } }),
  // Step-up (TOTP): enrol an authenticator, then exchange a live code for a
  // short-lived elevation token used on the very next flagged action.
  totpSetup: () => api.post<{ provisioning_uri: string; secret: string; issuer: string; account: string }>(
    '/ops/auth/totp/setup/', {}),
  totpConfirm: (code: string) => api.post<{ recovery_codes: string[] }>(
    '/ops/auth/totp/confirm/', { code }),
  stepUp: (code: string) => api.post<{ token: string; expires_in: number }>(
    '/ops/auth/step-up/', { code }),
}
