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

export interface CaseDetail {
  user_id: number
  case_id: string
  case_state: string
  phone_number: string
  status: string
  applicant: Record<string, string | boolean | null>
  documents: { id_front: DocRef; id_back: DocRef; selfie: DocRef }
  checks: {
    provider: string; state: string; checked_at: string | null
    ocr: Record<string, unknown>
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
  | { action: 'reject'; reason: string }
  | { action: 'request_resubmission'; items: string[] }

export const verification = {
  queue: (status = 'pending') =>
    api.get<{ results: QueueRow[]; count: number }>('/ops/verification/queue/', { params: { status } }),
  case: (userId: number | string) => api.get<CaseDetail>(`/ops/verification/${userId}/`),
  decide: (userId: number | string, body: Decision) =>
    api.post<CaseDetail>(`/ops/verification/${userId}/decision/`, body),
}
