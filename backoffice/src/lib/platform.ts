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
