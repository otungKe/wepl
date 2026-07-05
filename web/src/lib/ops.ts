// Back Office (operations console) API client — talks to /api/ops/*.
// Reuses the shared axios instance (bearer token + refresh interceptor); the
// base URL already ends in /api, so paths here are relative to that.
import { api } from './api'

export interface OpsMe {
  id: number
  phone_number: string
  name: string
  is_superuser: boolean
  roles: string[]
  capabilities: string[]
}

export type OpsResultType = 'user' | 'community' | 'verification' | 'journal'

export interface OpsSearchResult {
  type: OpsResultType
  id: number
  label: string
  sublabel: string
  url: string
}

export interface OpsSearchResponse {
  query: string
  results: OpsSearchResult[]
  counts: Record<string, number>
}

export const ops = {
  me: () => api.get<OpsMe>('/ops/me/'),
  ping: () => api.get<{ ok: boolean }>('/ops/ping/'),
  search: (q: string) => api.get<OpsSearchResponse>('/ops/search/', { params: { q } }),
}
