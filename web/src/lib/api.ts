import axios from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'
const WS_URL   = process.env.NEXT_PUBLIC_WS_URL  ?? 'ws://localhost:8000'

export { WS_URL }

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Inject auth token
api.interceptors.request.use(cfg => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) cfg.headers['Authorization'] = `Bearer ${token}`
  }
  return cfg
})

// Auto-refresh on 401
api.interceptors.response.use(
  res => res,
  async err => {
    const orig = err.config
    if (err.response?.status === 401 && !orig._retry) {
      orig._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/token/refresh/`, { refresh })
          localStorage.setItem('access_token', data.access)
          orig.headers['Authorization'] = `Bearer ${data.access}`
          return api(orig)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(err)
  }
)

// ── Auth ─────────────────────────────────────────────────────────────────────
export const auth = {
  requestOtp:    (phone_number: string) => api.post('/auth/request-otp/', { phone_number }),
  verifyOtp:     (phone_number: string, otp: string) => api.post('/auth/otp-verify/', { phone_number, otp }),
  setPin:        (pin: string) => api.post('/auth/pin/', { pin }),
  login:         (phone_number: string, pin: string) => api.post('/auth/login/', { phone_number, pin }),
  profile:       () => api.get('/auth/profile/'),
  kycSubmit:     (data: FormData) => api.post('/users/kyc/', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
}

// ── Communities ───────────────────────────────────────────────────────────────
export const communities = {
  list:           () => api.get('/communities/'),
  discover:       () => api.get('/communities/discover/'),
  get:            (id: string) => api.get(`/communities/${id}/`),
  create:         (data: unknown) => api.post('/communities/', data),
  join:           (code: string) => api.post('/communities/join/', { invite_code: code }),
  members:        (id: string) => api.get(`/communities/${id}/members/`),
  conversations:  (id: string) => api.get(`/communities/${id}/conversations/`),
  joinRequests:   (id: string) => api.get(`/communities/${id}/join-requests/`),
  approveRequest: (id: string, userId: string) => api.post(`/communities/${id}/join-requests/${userId}/approve/`),
}

// ── Contributions ─────────────────────────────────────────────────────────────
export const contributions = {
  list:          (communityId?: string) => api.get('/contributions/', { params: communityId ? { community: communityId } : {} }),
  get:           (id: string) => api.get(`/contributions/${id}/`),
  create:        (data: unknown) => api.post('/contributions/', data),
  join:          (id: string) => api.post(`/contributions/${id}/join/`),
  leave:         (id: string) => api.post(`/contributions/${id}/leave/`),
  transactions:  (id: string) => api.get(`/contributions/${id}/transactions/`),
  members:       (id: string) => api.get(`/contributions/${id}/members/`),
  disbursements: (id: string) => api.get(`/contributions/${id}/disbursements/`),
  amendments:    (id: string) => api.get(`/contributions/${id}/amendments/`),
  requestPayout: (id: string, data: unknown) => api.post(`/contributions/${id}/request-payout/`, data),
  proposeAmend:  (id: string, data: unknown) => api.post(`/contributions/${id}/propose-amendment/`, data),
  voteDisbursement: (id: string, disbId: string, vote: 'APPROVE'|'REJECT') =>
    api.post(`/contributions/${id}/disbursements/${disbId}/vote/`, { vote }),
}

// ── Conversations ─────────────────────────────────────────────────────────────
export const conversations = {
  get:     (id: string) => api.get(`/conversations/${id}/`),
  messages:(id: string, cursor?: string) => api.get(`/conversations/${id}/messages/`, { params: cursor ? { cursor } : {} }),
  send:    (id: string, data: unknown) => api.post(`/conversations/${id}/send/`, data),
  react:   (id: string, msgId: string, emoji: string) => api.post(`/conversations/${id}/messages/${msgId}/react/`, { emoji }),
  markRead:(id: string) => api.post(`/conversations/${id}/mark-read/`),
}

// ── Welfare & Shares ──────────────────────────────────────────────────────────
export const welfare = {
  get:       (communityId: string) => api.get(`/communities/${communityId}/welfare-fund/`),
  claims:    (communityId: string) => api.get(`/communities/${communityId}/welfare-fund/claims/`),
  submitClaim:(communityId: string, data: unknown) => api.post(`/communities/${communityId}/welfare-fund/claims/`, data),
}

export const shares = {
  get:    (communityId: string) => api.get(`/communities/${communityId}/shares-fund/`),
  buy:    (communityId: string, quantity: number) => api.post(`/communities/${communityId}/shares-fund/buy/`, { quantity }),
}

// ── Payments ──────────────────────────────────────────────────────────────────
export const payments = {
  stkPush:    (data: unknown) => api.post('/mpesa/stk-push/', data),
  checkStatus:(ref: string)   => api.get(`/mpesa/check-status/${ref}/`),
}

// ── Notifications ─────────────────────────────────────────────────────────────
export const notificationsApi = {
  list: () => api.get('/notifications/'),
  markRead: (id: string) => api.post(`/notifications/${id}/mark-read/`),
}
