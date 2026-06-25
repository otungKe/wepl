import axios from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'
const WS_URL   = process.env.NEXT_PUBLIC_WS_URL  ?? 'ws://localhost:8000'

export { WS_URL }

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach the bearer token to every request.
api.interceptors.request.use(cfg => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) cfg.headers['Authorization'] = `Bearer ${token}`
  }
  return cfg
})

// Transparently refresh the access token once on 401.
api.interceptors.response.use(
  res => res,
  async err => {
    const orig = err.config
    if (err.response?.status === 401 && orig && !orig._retry) {
      orig._retry = true
      const refresh = typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : null
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/users/token/refresh/`, { refresh })
          localStorage.setItem('access_token', data.access)
          orig.headers['Authorization'] = `Bearer ${data.access}`
          return api(orig)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          if (typeof window !== 'undefined') window.location.href = '/login'
        }
      }
    }
    return Promise.reject(err)
  }
)

/** DRF list endpoints are sometimes paginated ({results}) and sometimes plain arrays. */
function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in (data as Record<string, unknown>)) {
    return (data as { results: T[] }).results
  }
  return []
}

/** Turn an axios error into a human-readable message (DRF error shapes). */
export function apiError(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (axios.isAxiosError(err)) {
    const d = err.response?.data as Record<string, unknown> | string | undefined
    if (typeof d === 'string') return d
    if (d) {
      if (typeof d.detail === 'string') return d.detail
      if (typeof d.error === 'string') return d.error
      if (typeof d.message === 'string') return d.message
      const first = Object.values(d)[0]
      if (Array.isArray(first) && typeof first[0] === 'string') return first[0]
      if (typeof first === 'string') return first
    }
    if (!err.response) return 'Cannot reach the server. Check your connection.'
  }
  return fallback
}

// ─────────────────────────────────────────────────────────────
// Types (mirror the backend serializers / mobile client)
// ─────────────────────────────────────────────────────────────

export interface User {
  id: number
  phone_number: string
  name: string
  bio?: string
  profile_photo: string | null
  is_phone_verified: boolean
  is_pin_set: boolean
  kyc_status: 'not_submitted' | 'pending' | 'approved' | 'rejected'
}

export interface Community {
  id: number
  name: string
  description: string | null
  community_photo: string | null
  is_private: boolean
  invite_code: string
  has_welfare_fund: boolean
  has_shares_fund: boolean
  category: string
  location: string
  created_by: string
  created_by_name: string
  member_count: number
  is_member: boolean
  join_request_status: 'PENDING' | 'APPROVED' | 'REJECTED' | null
  created_at: string
  join_policy: 'open' | 'request' | 'invite_only'
  invite_permission: 'admins' | 'members'
  contribution_permission: 'admins' | 'members'
  member_list_visibility: 'all' | 'admins'
  max_members: number | null
  cooling_off_days: number
}

export interface CommunityMember {
  id: number
  phone_number: string | null
  name: string
  profile_photo: string | null
  role: 'admin' | 'member' | 'treasurer'
  is_active: boolean
  is_online: boolean | null
}

export interface Contribution {
  id: number
  title: string
  description: string | null
  visibility: 'closed' | 'open'
  created_by: string
  community: number | null
  invite_code: string
  target_amount: string | null
  member_target_amount: string | null
  current_amount: string
  tenure_type: 'open' | 'date' | 'period'
  end_date: string | null
  period_months: number | null
  frequency: 'daily' | 'weekly' | 'monthly' | 'anytime'
  amount_type: 'fixed' | 'open'
  fixed_amount: string | null
  voting_threshold: string
  voting_label: string
  my_rosca_slot: {
    slot_order: number
    cycle_number: number
    has_received: boolean
    payout_amount: string | null
    received_at: string | null
  } | null
  is_active: boolean
  status: 'active' | 'closed' | 'archived'
  participant_count: number
  user_balance: string | null
  is_admin: boolean
  created_at: string
}

export interface Participant {
  id: number
  phone_number: string
  name: string | null
  is_active: boolean
  balance: string
  progress_pct: number | null
}

export interface Transaction {
  id: number
  phone_number: string
  name: string | null
  contribution: number
  contribution_title: string
  amount: string
  transaction_type: 'CONTRIBUTION' | 'WITHDRAWAL' | 'ADVANCE' | 'REPAYMENT'
  note: string | null
  mpesa_receipt: string | null
  platform_ref: string
  created_at: string
}

export interface DisbursementVote {
  id: number
  voter_phone: string
  vote: 'APPROVE' | 'REJECT'
  voted_at: string
}

export interface DisbursementRequest {
  id: number
  contribution: number
  required_approvals: number
  requested_by_phone: string
  amount: string
  reason: string
  recipient_phone: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED'
  approve_count: number
  reject_count: number
  votes: DisbursementVote[]
  created_at: string
  executed_at: string | null
}

export interface ChangeDisplay { field: string; from: string; to: string }

export interface ContributionAmendment {
  id: number
  contribution: number
  proposed_by_phone: string
  proposed_by_name: string
  changes: Record<string, string>
  changes_display: ChangeDisplay[]
  reason: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'WITHDRAWN'
  approve_count: number
  reject_count: number
  required_approvals: number
  votes: { id: number; voter_phone: string; voter_name: string; vote: 'APPROVE' | 'REJECT'; voted_at: string }[]
  created_at: string
  resolved_at: string | null
}

export interface ShareHolding {
  id: number
  phone_number: string
  name: string
  shares_count: string
  total_contributed: string
  ownership_pct: string
}

export interface SharesFund {
  id: number
  name: string
  share_price: string
  total_pool: string
  total_shares: string
  holdings: ShareHolding[]
  created_at: string
}

export interface WelfareFund {
  id: number
  community: number | null
  name: string
  balance: string
  monthly_contribution: string
  created_at: string
  is_admin?: boolean
}

export interface WelfareClaim {
  id: number
  fund: number
  claimant_phone: string
  amount_requested: string
  reason: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'DISBURSED'
  approve_count: number
  votes: { id: number; voter_phone: string; vote: string; voted_at: string }[]
  created_at: string
  approved_at: string | null
  disbursed_at: string | null
  mpesa_receipt: string | null
}

export interface Conversation {
  id: number
  community: number
  topic: string
  photo: string | null
  created_by: string
  created_at: string
  message_count: number
  unread_count: number
  last_message: { content: string; sender: string; created_at: string; message_type: string } | null
}

export interface Message {
  id: number
  sender: string
  sender_phone: string
  content: string
  message_type: 'text' | 'image' | 'voice' | 'video' | 'system'
  attachment: string | null
  reply_to: { id: number; deleted: boolean; sender: string; content: string; message_type: string; attachment: string | null } | null
  reactions: Record<string, string[]>
  is_edited: boolean
  created_at: string
}

export interface FinancialSummary {
  total_contributed: number
  total_received: number
  active_contributions: number
  total_contributions: number
  pending_advances: number
  advance_balance_due: number
  this_month: number
  last_month: number
  monthly_trend: { month: string; amount: number }[]
  tx_count: number
  member_since: string
  kyc_status: 'approved' | 'pending' | 'rejected' | 'not_submitted'
}

export interface MyJoinRequest {
  id: number
  community_id: number
  community_name: string
  community_photo: string | null
  member_count: number
  created_at: string
}

export interface Notification {
  id: number
  notification_type: string
  title: string
  message: string
  is_read: boolean
  community_id: number | null
  conversation_id: number | null
  contribution_id: number | null
  join_request_id: number | null
  join_request_status: 'PENDING' | 'APPROVED' | 'REJECTED' | null
  created_at: string
}

// ─────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────
export const auth = {
  requestOtp: (phone_number: string) => api.post('/users/otp/request/', { phone_number }),
  verifyOtp:  (phone_number: string, otp: string) => api.post('/users/otp/verify/', { phone_number, otp }),
  setPin:     (pin: string) => api.post('/users/pin/set/', { pin }),
  resetPin:   (pin: string) => api.post('/users/pin/reset/', { pin }),
  login:      (phone_number: string, pin: string) => api.post('/users/pin/login/', { phone_number, pin }),
  profile:    () => api.get<User>('/users/profile/'),
  updateProfile: (data: FormData | Partial<User>) =>
    api.patch<User>('/users/profile/', data,
      data instanceof FormData ? { headers: { 'Content-Type': 'multipart/form-data' } } : undefined),
  kycStatus:  () => api.get('/users/kyc/'),
  kycSubmit:  (data: FormData) => api.post('/users/kyc/', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
}

// ─────────────────────────────────────────────────────────────
// Communities
// ─────────────────────────────────────────────────────────────
export const communities = {
  mine:      async () => unwrap<Community>((await api.get('/communities/')).data),
  discover:  async (q?: string) => {
    const r = await api.get('/communities/discover/', { params: q ? { q } : {} })
    return (r.data.results ?? r.data) as Community[]
  },
  get:       (id: number | string) => api.get<Community>(`/communities/${id}/`),
  create:    (data: Record<string, unknown>) => api.post<Community>('/communities/create/', data),
  update:    (id: number | string, data: Record<string, unknown>) => api.patch<Community>(`/communities/${id}/update/`, data),
  join:      (id: number | string) => api.post(`/communities/${id}/join/`),
  requestJoin: (id: number | string) => api.post(`/communities/${id}/request/`),
  leave:     (id: number | string) => api.post(`/communities/${id}/leave/`),
  remove:    (id: number | string) => api.delete(`/communities/${id}/delete/`),
  members:   async (id: number | string) => unwrap<CommunityMember>((await api.get(`/communities/${id}/members/`)).data),
  byInvite:  (code: string) => api.get<Community>(`/communities/invite/${code}/`),
  requestByInvite: (code: string) => api.post(`/communities/invite/${code}/request/`),
  assignRole: (cid: number | string, mid: number, role: string) => api.post(`/communities/${cid}/members/${mid}/role/`, { role }),
  removeMember: (cid: number | string, mid: number) => api.delete(`/communities/${cid}/members/${mid}/`),
  myRequests: async () => unwrap<MyJoinRequest>((await api.get('/communities/my-requests/')).data),
  actionRequest: (reqId: number, action: 'approve' | 'reject') => api.post(`/communities/join-requests/${reqId}/action/`, { action }),
}

// ─────────────────────────────────────────────────────────────
// Reports / financial summary
// ─────────────────────────────────────────────────────────────
export const reports = {
  financialSummary: () => api.get<FinancialSummary>('/users/financial-summary/'),
}

// ─────────────────────────────────────────────────────────────
// Contributions
// ─────────────────────────────────────────────────────────────
export const contributions = {
  mine:      async (active = true) => unwrap<Contribution>((await api.get(`/contributions/?active=${active}`)).data),
  open:      async () => unwrap<Contribution>((await api.get('/contributions/open/')).data),
  myTransactions: async () => unwrap<Transaction>((await api.get('/contributions/transactions/')).data),
  forCommunity: async (cid: number | string) => unwrap<Contribution>((await api.get(`/contributions/community/${cid}/`)).data),
  get:       (id: number | string) => api.get<Contribution>(`/contributions/${id}/`),
  create:    (data: Record<string, unknown>) => api.post<Contribution>('/contributions/create/', data),
  join:      (id: number | string) => api.post(`/contributions/${id}/join/`),
  leave:     (id: number | string) => api.post(`/contributions/${id}/leave/`),
  participants: async (id: number | string) => unwrap<Participant>((await api.get(`/contributions/${id}/participants/`)).data),
  transactions: async (id: number | string) => unwrap<Transaction>((await api.get(`/contributions/${id}/transactions/`)).data),
  disbursements: async (id: number | string) => unwrap<DisbursementRequest>((await api.get(`/contributions/${id}/disbursements/`)).data),
  createDisbursement: (id: number | string, data: { amount: number | string; reason: string; recipient_phone?: string }) =>
    api.post<DisbursementRequest>(`/contributions/${id}/disbursements/`, data),
  voteDisbursement: (reqId: number, vote: 'APPROVE' | 'REJECT') => api.post(`/contributions/disbursements/${reqId}/vote/`, { vote }),
  amendments: async (id: number | string) => unwrap<ContributionAmendment>((await api.get(`/contributions/${id}/amendments/`)).data),
  proposeAmendment: (id: number | string, data: { changes: Record<string, unknown>; reason?: string }) =>
    api.post<ContributionAmendment>(`/contributions/${id}/amendments/`, data),
  voteAmendment: (aid: number, vote: 'APPROVE' | 'REJECT') => api.post(`/contributions/amendments/${aid}/vote/`, { vote }),
  // Pool join requests (admin review) & invites (invitee response)
  joinRequests: async (id: number | string) => unwrap<{ id: number; phone_number: string; name: string | null; created_at: string }>((await api.get(`/contributions/${id}/join-requests/`)).data),
  actionJoinRequest: (reqId: number, action: 'approve' | 'reject') => api.post(`/contributions/join-requests/${reqId}/action/`, { action }),
  respondInvite: (reqId: number, action: 'accept' | 'decline') => api.post(`/contributions/invitations/${reqId}/respond/`, { action }),
  // Emergency advances (admin review)
  actionAdvance: (advanceId: number, action: 'approve' | 'reject', amount?: number) => api.post(`/contributions/advances/${advanceId}/action/`, { action, ...(amount != null ? { amount } : {}) }),
}

// ─────────────────────────────────────────────────────────────
// Conversations / chat
// ─────────────────────────────────────────────────────────────
export const conversations = {
  forCommunity: async (cid: number | string) => unwrap<Conversation>((await api.get(`/conversations/community/${cid}/`)).data),
  create:    (cid: number | string, topic: string) => api.post<Conversation>(`/conversations/community/${cid}/`, { topic }),
  get:       (id: number | string) => api.get<Conversation>(`/conversations/${id}/`),
  messages:  async (id: number | string) => unwrap<Message>((await api.get(`/conversations/${id}/messages/`)).data),
  send:      (id: number | string, content: string, reply_to_id?: number) =>
    api.post<Message>(`/conversations/${id}/messages/`, { content, reply_to_id }),
  react:     (msgId: number, emoji: string) => api.post(`/conversations/messages/${msgId}/react/`, { emoji }),
  markRead:  (id: number | string) => api.post(`/conversations/${id}/read/`),
}

// ─────────────────────────────────────────────────────────────
// Welfare & Shares (community-scoped, under /contributions)
// ─────────────────────────────────────────────────────────────
export const welfare = {
  get:       (cid: number | string) => api.get<WelfareFund>(`/contributions/welfare/${cid}/`),
  contribute:(cid: number | string, amount: number) => api.post<WelfareFund>(`/contributions/welfare/${cid}/contribute/`, { amount }),
  claims:    async (cid: number | string) => unwrap<WelfareClaim>((await api.get(`/contributions/welfare/${cid}/claims/`)).data),
  submitClaim: (cid: number | string, data: { amount_requested: number | string; reason: string }) =>
    api.post<WelfareClaim>(`/contributions/welfare/${cid}/claims/`, data),
  voteClaim: (claimId: number, action: 'approve' | 'reject') => api.post(`/contributions/welfare/claims/${claimId}/vote/`, { action }),
}

export const shares = {
  get:       (cid: number | string) => api.get<SharesFund>(`/contributions/shares/${cid}/`),
  contribute:(cid: number | string, amount: number) => api.post<SharesFund>(`/contributions/shares/${cid}/contribute/`, { amount }),
}

// ─────────────────────────────────────────────────────────────
// Payments (M-PESA STK push)
// ─────────────────────────────────────────────────────────────
export const payments = {
  stkPush: (data: { payment_type?: 'contribution' | 'welfare' | 'shares'; contribution_id?: number; community_id?: number; amount: number; phone_number?: string }) =>
    api.post<{ message: string; checkout_request_id: string }>('/mpesa/stk/push/', data),
  status:  (checkoutRequestId: string) =>
    api.get<{ status: 'PENDING' | 'SUCCESS' | 'FAILED'; mpesa_receipt: string | null }>(`/mpesa/stk/status/${checkoutRequestId}/`),
}

// ─────────────────────────────────────────────────────────────
// Notifications
// ─────────────────────────────────────────────────────────────
export const notificationsApi = {
  list:      async () => unwrap<Notification>((await api.get('/notifications/')).data),
  unreadCount: async () => (await api.get('/notifications/unread-count/')).data.unread_count as number,
  markRead:  (id: number) => api.post(`/notifications/${id}/read/`),
  markAllRead: () => api.post('/notifications/read-all/'),
  remove:    (id: number) => api.delete(`/notifications/${id}/delete/`),
  prefs:     () => api.get('/notifications/preferences/'),
  updatePrefs: (patch: Record<string, boolean>) => api.patch('/notifications/preferences/', patch),
}
