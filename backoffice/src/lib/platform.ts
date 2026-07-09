import { api, stepUpConfig } from './ops'

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
  communityLifecycle: (id: number | string, action: 'suspend' | 'unsuspend', reason: string, stepUpToken: string) =>
    api.post<{ id: number; status: string }>(
      `/ops/communities/${id}/lifecycle/`, { action, reason }, stepUpConfig(stepUpToken)),
  audit: (params: Record<string, string | number> = {}) =>
    api.get<{ results: AuditRow[]; count: number; has_more: boolean }>('/ops/audit/', { params }),
}

/* ── Users ops module ────────────────────────────────────────────────── */

export interface UserRow {
  id: number
  member_number: string | null
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
  status: (id: number | string, action: 'deactivate' | 'reactivate', reason: string, stepUpToken: string) =>
    api.post<{ id: number; is_active: boolean }>(
      `/ops/users/${id}/status/`, { action, reason }, stepUpConfig(stepUpToken)),
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

/* ── Transactions (money movements) ──────────────────────────────────── */

export interface TxRow {
  id: number
  reference: string
  op_type: string
  state: string
  amount: string
  initiated_by_id: number | null
  initiated_by: string
  recipient_phone: string
  fund: string | null
  community_id: number | null
  mpesa_receipt: string | null
  created_at: string
}

export interface Tx360 {
  movement: {
    id: number; reference: string; op_type: string; op_type_label: string; state: string
    amount: string; idempotency_key: string; note: string
    failure_reason: string; created_at: string; updated_at: string
  }
  parties: {
    initiated_by_id: number | null; initiated_by: string
    initiated_by_phone: string | null; recipient_phone: string
  }
  context: {
    fund: string | null; community_id: number | null
    community_name: string | null; trigger_type: string; trigger_id: number | null
  }
  rail: { mpesa_checkout_id: string | null; mpesa_conversation_id: string | null; mpesa_receipt: string | null }
  controls: { decision: string; reason: string; rule: string | null; at: string }[]
  journal?: {
    id: number; narration: string; posted_at: string | null; reverses_id: number | null
    lines: { account_code: string; account_name: string; direction: string; amount: string }[]
  }[]
}

export const transactions = {
  list: (params: { state?: string; op_type?: string; q?: string; offset?: number } = {}) =>
    api.get<{ results: TxRow[]; count: number; has_more: boolean
              by_state: Record<string, number>
              op_types: { value: string; label: string }[] }>('/ops/transactions/', { params }),
  tx360: (id: number | string) => api.get<Tx360>(`/ops/transactions/${id}/`),
}

/* ── FinOps (payment recovery levers, OP-1) ──────────────────────────────── */

export interface FinopsRow extends TxRow {
  updated_at: string
  failure_reason: string
  conversation_id: string | null
}

export interface FinopsQueues {
  threshold_minutes: number
  counts: { stuck_payouts: number; failed_payouts: number; stuck_payins: number }
  stuck_payouts: FinopsRow[]
  failed_payouts: FinopsRow[]
}

export interface FinopsActionResult {
  result: { outcome: string; state: string; detail: string }
}

export const finops = {
  queues: (minutes = 30) =>
    api.get<FinopsQueues>('/ops/finops/', { params: { minutes } }),
  action: (ftId: number | string, action: 'requery' | 'mark_failed' | 'retry_payout', reason: string, stepUpToken: string) =>
    api.post<FinopsRow & FinopsActionResult>(
      `/ops/finops/transactions/${ftId}/action/`, { action, reason }, stepUpConfig(stepUpToken)),
  reverseRequest: (ftId: number | string, reason: string, stepUpToken: string) =>
    api.post<{ approval_id: number; status: string; detail: string }>(
      `/ops/finops/transactions/${ftId}/reverse-request/`, { reason }, stepUpConfig(stepUpToken)),
}

/* ── Approvals (maker-checker inbox, OP-3 Part 2) ────────────────────────── */

export interface ApprovalRow {
  id: number
  action: string
  summary: string
  reason: string
  status: string
  target_type: string
  target_id: string
  requested_by: string
  requested_by_email: string
  requested_at: string
  expires_at: string
  decided_by: string | null
  decided_at: string | null
  decision_note: string
  result: Record<string, unknown>
}

export const approvals = {
  list: (status = 'pending') =>
    api.get<{ results: ApprovalRow[]; counts: { pending: number } }>(
      '/ops/approvals/', { params: { status } }),
  detail: (id: number | string) =>
    api.get<ApprovalRow & { params: Record<string, unknown> }>(`/ops/approvals/${id}/`),
  decide: (id: number | string, decision: 'approve' | 'reject', note: string, stepUpToken: string) =>
    api.post<ApprovalRow>(`/ops/approvals/${id}/decide/`, { decision, note }, stepUpConfig(stepUpToken)),
}

/* ── System Health + alert bell (OP-2) ───────────────────────────────────── */

export interface Heartbeat {
  task: string; last_seen: string | null; age_seconds: number | null
  window_seconds: number; stale: boolean; never_seen: boolean
}

export interface HealthOverview {
  outbox: { pending: number; dead: number; oldest_pending_seconds: number | null }
  heartbeats: Heartbeat[]
  queues: Record<string, number | null>
}

export interface OutboxRow {
  id: number; event_type: string; status: string; attempts: number
  last_error: string; payload: Record<string, unknown>
  created_at: string; processed_at: string | null
}

export interface Notice {
  id: number; key: string; level: string; title: string; message: string; created_at: string
}

export const health = {
  overview: () => api.get<HealthOverview>('/ops/health/'),
  outbox: (status = 'DEAD', offset = 0) =>
    api.get<{ results: OutboxRow[]; count: number; has_more: boolean }>(
      '/ops/health/outbox/', { params: { status, offset } }),
  requeue: (id: number | string) =>
    api.post<{ id: number; status: string }>(`/ops/health/outbox/${id}/requeue/`),
}

export const notices = {
  list: () => api.get<{ results: Notice[]; count: number; critical: number }>('/ops/notices/'),
  dismiss: (id: number | string) =>
    api.post<{ id: number; dismissed: boolean }>(`/ops/notices/${id}/dismiss/`),
}
