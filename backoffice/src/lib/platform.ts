import { api } from './ops'

/* ── Home dashboard metrics (capability-filtered blocks) ─────────────── */

export interface OpsMetrics {
  verification?: { kyc_pending: number; kyc_oldest_hours: number | null; edd_open: number }
  holds?: { open: number }
  outbox?: { pending: number; dead: number; oldest_pending_seconds: number | null }
  ledger?: { trial_balance_delta: string; balanced: boolean }
  communities?: { total: number; active: number; suspended: number }
  users?: { total: number; new_7d: number }
}

/* ── Communities ops module ──────────────────────────────────────────── */

export interface CommunityRow {
  id: number
  name: string
  category: string
  status: string
  is_private: boolean
  member_count: number | null
  owner_phone: string
  tenant: string | null
  created_at: string
}

export interface CommunityFile extends CommunityRow {
  description: string
  location: string
  owner_name: string
  members: { active: number; admins: number; treasurers: number; banned: number; max: number | null }
  settings: Record<string, string | number>
  finance: { contributions: number; welfare_funds: number; shares_funds: number; has_financial_history: boolean }
  pending_join_requests: number
  audit_trail: { action: string; actor: string; metadata: Record<string, unknown>; at: string }[]
}

/* ── Audit log ───────────────────────────────────────────────────────── */

export interface AuditRow {
  id: number
  action: string
  actor: string
  target_type: string
  target_id: string
  metadata: Record<string, unknown>
  ip_address: string | null
  at: string
}

export const platform = {
  metrics: () => api.get<OpsMetrics>('/ops/metrics/'),
  communities: (params: { q?: string; status?: string; offset?: number } = {}) =>
    api.get<{ results: CommunityRow[]; count: number; has_more: boolean }>(
      '/ops/communities/', { params }),
  community: (id: number | string) => api.get<CommunityFile>(`/ops/communities/${id}/`),
  communityLifecycle: (id: number | string, action: 'suspend' | 'unsuspend', reason: string) =>
    api.post<{ id: number; status: string }>(`/ops/communities/${id}/lifecycle/`, { action, reason }),
  audit: (params: Record<string, string | number> = {}) =>
    api.get<{ results: AuditRow[]; count: number; has_more: boolean }>('/ops/audit/', { params }),
}

/* ── Users ops module ────────────────────────────────────────────────── */

export interface UserRow {
  id: number
  phone_number: string
  name: string
  is_active: boolean
  phone_verified: boolean
  kyc_status: string
  tier: 0 | 1
  joined: string
  last_seen: string | null
}

export interface User360 {
  identity: UserRow & { last_seen: string | null }
  verification: {
    kyc_status: string
    email_verified?: boolean
    resubmission_requested?: string[]
    case: { reference: string; state: string } | null
    open_requests: number
  }
  communities: { id: number; name: string; role: string; community_status: string; joined: string }[]
  financial: {
    positions: { contribution_id: number; name: string; balance: string }[]
    total_position: string
    open_advances: number
    open_holds: number
    active_overrides: number
  }
  sessions: { active: number; latest_device: string | null; latest_seen: string | null }
  audit_trail: { action: string; actor: string; metadata: Record<string, unknown>; at: string }[]
}

export const opsUsers = {
  list: (params: { q?: string; state?: string; offset?: number } = {}) =>
    api.get<{ results: UserRow[]; count: number; has_more: boolean }>('/ops/users/', { params }),
  user360: (id: number | string) => api.get<User360>(`/ops/users/${id}/`),
  status: (id: number | string, action: 'deactivate' | 'reactivate', reason: string) =>
    api.post<{ id: number; is_active: boolean }>(`/ops/users/${id}/status/`, { action, reason }),
}

/* ── Support desk (verification requests) ────────────────────────────── */

export interface SupportRow {
  id: number
  user_id: number
  user_name: string
  phone_number: string
  kind: string
  title: string
  status: string
  has_document: boolean
  created_at: string
  responded_at: string | null
}

export interface SupportDetail extends SupportRow {
  detail: string
  response_note: string
  document_url: string | null
  review_note: string
  resolved_at: string | null
  kinds: { value: string; label: string }[]
}

export const support = {
  list: (params: { status?: string; q?: string; offset?: number } = {}) =>
    api.get<{ results: SupportRow[]; count: number; has_more: boolean; kinds: { value: string; label: string }[] }>(
      '/ops/support/requests/', { params }),
  raise: (body: { phone_number: string; kind: string; title: string; detail: string }) =>
    api.post<SupportDetail>('/ops/support/requests/', body),
  detail: (id: number | string) => api.get<SupportDetail>(`/ops/support/requests/${id}/`),
  resolve: (id: number | string, note: string) =>
    api.post<SupportDetail>(`/ops/support/requests/${id}/resolve/`, { note }),
}
