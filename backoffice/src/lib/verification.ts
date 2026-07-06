import { api } from './ops'

export interface QueueRow {
  user_id: number
  name: string
  phone_number: string
  id_number: string
  status: string
  email_verified: boolean
  submitted_at: string | null
  age_hours: number | null
  ocr_mismatch: boolean
  ocr_detected: boolean | null
  resubmission_pending: boolean
  assignee: string | null
  sla: Sla | null
}

export interface Sla {
  target_hours: number
  remaining_hours: number
  overdue: boolean
}

export interface DocVersion {
  version: number
  url: string | null
  name: string
  source: string
  sha256: string
  at: string
}

export interface DocRef {
  available: boolean
  url: string | null
  name: string | null
  versions: DocVersion[]
}

export interface TimelineEvent {
  seq: number
  type: string
  actor: string
  actor_kind: 'customer' | 'staff' | 'system'
  at: string
  payload: Record<string, unknown>
}

export interface CaseNote {
  id: number
  author: string
  body: string
  at: string
}

export interface RejectionCode {
  code: string
  label: string
  customer_message: string
}

export interface VerificationStats {
  pending: number
  requires_info: number
  unassigned_open: number
  mine_open: number
  approved: number
  rejected: number
  decided_today: number
  decided_7d: number
  decided_total: number
  total_cases: number
  oldest_pending_hours: number | null
}

export interface CaseDetail {
  user_id: number
  case_id: string
  reference: string
  case_state: string
  case_opened_at: string | null
  case_closed_at: string | null
  assignee: string | null
  notes: CaseNote[]
  rejection_reasons: RejectionCode[]
  phone_number: string
  phone_verified: boolean
  status: string
  attempts: number
  sla: Sla | null
  applicant: Record<string, string | boolean | null>
  documents: { id_front: DocRef; id_back: DocRef; selfie: DocRef }
  checks: {
    provider: string; state: string; checked_at: string | null
    ocr: Record<string, unknown>
    duplicate_email: boolean
  }
  rejection_reason: string
  resubmission_requested: string[]
  resubmittable_items: Record<string, string>
  submitted_at: string | null
  age_hours: number | null
  timeline: TimelineEvent[]
}

export type Decision =
  | { action: 'approve' }
  | { action: 'reject'; reason?: string; reason_code?: string }
  | { action: 'request_resubmission'; items: string[] }

export const verification = {
  stats: () => api.get<VerificationStats>('/ops/verification/stats/'),
  queue: (status = 'pending', assigned?: 'me' | 'nobody') =>
    api.get<{ results: QueueRow[]; count: number }>('/ops/verification/queue/', { params: { status, ...(assigned ? { assigned } : {}) } }),
  case: (userId: number | string) => api.get<CaseDetail>(`/ops/verification/${userId}/`),
  decide: (userId: number | string, body: Decision) =>
    api.post<CaseDetail>(`/ops/verification/${userId}/decision/`, body),
  note: (userId: number | string, body: string) =>
    api.post<CaseDetail>(`/ops/verification/${userId}/notes/`, { body }),
  assign: (userId: number | string, action: 'claim' | 'release') =>
    api.post<CaseDetail>(`/ops/verification/${userId}/assign/`, { action }),
}
