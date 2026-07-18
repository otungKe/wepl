import API from "./client";

export type TenureType   = 'open' | 'date' | 'period';
export type Frequency    = 'daily' | 'weekly' | 'monthly' | 'anytime';
export type AmountType   = 'fixed' | 'open';
export type VotingThreshold = 'admins' | '50' | '100' | string; // string also covers custom %

export type ContributionStatus = 'active' | 'closed' | 'archived';

export type Contribution = {
  id: number;
  title: string;
  description: string | null;
  visibility: 'closed' | 'open';
  created_by: string;
  community: number | null;
  invite_code: string;
  target_amount:        string | null;
  member_target_amount:          string | null;
  current_amount:                string;
  // Section C governance
  transaction_visibility:        'all' | 'own' | 'admins_all';
  amendment_proposer:            'creator' | 'admins' | 'members';
  amendment_voting_threshold:    string;
  late_contribution_policy:      'open' | 'strict' | 'grace';
  late_contribution_grace_days:  number;
  // Term
  tenure_type: TenureType;
  end_date: string | null;
  period_months: number | null;
  // Schedule
  frequency: Frequency;
  amount_type: AmountType;
  fixed_amount: string | null;
  // Governance
  voting_threshold: VotingThreshold;
  voting_label: string;
  governance_locked_until: string | null;
  // ROSCA — current user's rotation slot (null when no rotation set up)
  my_rosca_slot: {
    slot_order: number;
    cycle_number: number;
    has_received: boolean;
    payout_amount: string | null;
    received_at: string | null;
  } | null;
  // Legacy
  min_approvals: number;
  is_active: boolean;
  status: ContributionStatus;
  participant_count: number;
  user_balance: string | null;
  is_admin: boolean;
  is_participant?: boolean;  // server-derived: creator or active participant
  created_at: string;
};

export type Participant = {
  id: number;
  phone_number: string;
  name: string | null;
  is_active: boolean;
  balance:      string;        // "45000.00" — how much this member has contributed
  progress_pct: number | null; // 0–100+, null if no member_target set
};

export type Transaction = {
  id: number;
  phone_number: string;
  name: string | null;
  contribution: number;
  contribution_title: string;
  amount: string;
  transaction_type: 'CONTRIBUTION' | 'WITHDRAWAL' | 'ADVANCE' | 'REPAYMENT';
  note: string | null;
  mpesa_receipt: string | null;
  platform_ref: string;
  created_at: string;
};

export type ROSCASlot = {
  id: number;
  slot_order: number;
  cycle_number: number;
  phone_number: string;
  has_received: boolean;
  received_at: string | null;
  payout_amount: string | null;
};

export type DisbursementVote = {
  id: number;
  voter_phone: string;
  vote: 'APPROVE' | 'REJECT';
  voted_at: string;
};

export type DisbursementRequest = {
  id: number;
  contribution: number;
  required_approvals: number;
  requested_by_phone: string;
  amount: string;
  reason: string;
  recipient_phone: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED';
  approve_count: number;
  reject_count: number;
  votes: DisbursementVote[];
  created_at: string;
  executed_at: string | null;
};

export type PoolActionRequest = {
  id: number;
  contribution: number;
  action: 'EXPENSE' | 'DISTRIBUTION';
  amount: string;
  apportion: 'pro_rata' | 'per_capita';
  memo: string;
  status: 'PENDING' | 'EXECUTED' | 'REJECTED' | 'CANCELLED';
  requested_by: number;
  requested_by_name: string;
  approval_count: number;
  decision_note: string;
  platform_ref: string | null;
  created_at: string;
  updated_at: string;
};

export type ShareHolding = {
  id: number;
  phone_number: string;
  name: string;
  shares_count: string;
  total_contributed: string;
  ownership_pct: string;
};

export type SharesFund = {
  id: number;
  name: string;
  share_price: string;
  total_pool: string;
  total_shares: string;
  holdings: ShareHolding[];
  created_at: string;
};

export type WelfareFund = {
  id: number;
  community: number | null;
  name: string;
  balance: string;
  monthly_contribution: string;
  created_at: string;
  is_admin?: boolean; // server-derived; use instead of URL param
};

export type WelfareClaim = {
  id: number;
  fund: number;
  claimant_phone: string;
  amount_requested: string;
  reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'DISBURSED';
  approve_count: number;
  votes: { id: number; voter_phone: string; vote: string; voted_at: string }[];
  created_at: string;
  approved_at: string | null;
  disbursed_at: string | null;
  mpesa_receipt: string | null;
};

export type WelfareActivity = {
  type: 'DEPOSIT' | 'WITHDRAWAL';
  amount: string;
  phone: string;
  name: string;
  mpesa_receipt: string | null;
  note: string;
  date: string;
  status?: string;
};

export type EmergencyAdvance = {
  id: number;
  contribution: number;
  borrower_phone: string;
  amount: string;
  interest_rate: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'DISBURSED' | 'REPAID';
  amount_repaid: string;
  total_due: string;
  balance_due: string;
  repayment_due: string | null;
  created_at: string;
};

export type StandingOrderSlot = {
  id: number;
  slot_order: number;
  phone_number: string;
  name: string;
  has_received: boolean;
  received_at: string | null;
};

export type StandingOrder = {
  id: number;
  contribution: number;
  created_by_phone: string;
  amount: string;
  frequency: 'daily' | 'weekly' | 'monthly';
  payee_type: 'fixed' | 'rotating';
  fixed_payee_phone: string | null;
  is_active: boolean;
  slots: StandingOrderSlot[];
  next_slot: StandingOrderSlot | null;
  created_at: string;
};

export type CreateStandingOrderPayload = {
  amount: number;
  frequency: 'daily' | 'weekly' | 'monthly';
  payee_type: 'fixed' | 'rotating';
  fixed_payee_phone?: string;
};

export type CreateContributionPayload = {
  title: string;
  description?: string;
  visibility: 'closed' | 'open';
  community?: number | null;
  target_amount?:        number | null;
  member_target_amount?: number | null;
  tenure_type: TenureType;
  end_date?: string | null;
  period_months?: number | null;
  frequency: Frequency;
  amount_type: AmountType;
  fixed_amount?: number | null;
  voting_threshold: VotingThreshold;
  member_phones?: string[];
  add_all_members?: boolean;
};

// ---------------------------------------------------------------------------
// Core
// ---------------------------------------------------------------------------

export const getMyContributions = async (active = true): Promise<Contribution[]> => {
  const r = await API.get(`contributions/?active=${active}`);
  return r.data?.results ?? r.data;
};

export const getOpenContributions = async (): Promise<Contribution[]> => {
  const r = await API.get("contributions/open/");
  return r.data?.results ?? r.data;
};

export const getCommunityContributions = async (communityId: number): Promise<Contribution[]> => {
  const r = await API.get(`contributions/community/${communityId}/`);
  return r.data?.results ?? r.data;
};

export const getContribution = async (id: number): Promise<Contribution> => {
  const r = await API.get(`contributions/${id}/`);
  return r.data;
};

export const getContributionByInvite = async (code: string): Promise<Contribution> => {
  const r = await API.get(`contributions/invite/${code}/`);
  return r.data;
};

export const createContribution = async (data: CreateContributionPayload): Promise<Contribution> => {
  const r = await API.post("contributions/create/", data);
  return r.data;
};

export const joinContribution = async (id: number) => {
  const r = await API.post(`contributions/${id}/join/`);
  return r.data;
};

export const leaveContribution = async (id: number) => {
  const r = await API.post(`contributions/${id}/leave/`);
  return r.data;
};

export const closeContribution = async (id: number): Promise<Contribution> => {
  const r = await API.post(`contributions/${id}/close/`);
  return r.data;
};

export const reopenContribution = async (id: number): Promise<Contribution> => {
  const r = await API.post(`contributions/${id}/reopen/`);
  return r.data;
};

export const archiveContribution = async (id: number): Promise<Contribution> => {
  const r = await API.post(`contributions/${id}/archive/`);
  return r.data;
};

export const deleteContribution = async (id: number): Promise<void> => {
  await API.delete(`contributions/${id}/delete/`);
};

// Direct cosmetic-only edit (title, description)
export const updateContribution = async (
  id: number,
  data: { title?: string; description?: string },
): Promise<Contribution> => {
  const r = await API.patch(`contributions/${id}/update/`, data);
  return r.data;
};

// Sensitive field amendment types
export type AmendmentChanges = {
  fixed_amount?: number | string | null;
  target_amount?: number | string | null;
  voting_threshold?: VotingThreshold;
  end_date?: string | null;
  period_months?: number | null;
  visibility?: 'closed' | 'open';
};

export type AmendmentVoteRecord = {
  id: number;
  voter_phone: string;
  voter_name: string;
  vote: 'APPROVE' | 'REJECT';
  voted_at: string;
};

export type ChangeDisplay = { field: string; from: string; to: string };

export type ContributionAmendment = {
  id: number;
  contribution: number;
  proposed_by_phone: string;
  proposed_by_name: string;
  changes: Record<string, string>;
  changes_display: ChangeDisplay[];
  reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'WITHDRAWN';
  approve_count: number;
  reject_count: number;
  required_approvals: number;
  votes: AmendmentVoteRecord[];
  created_at: string;
  resolved_at: string | null;
};

export const getAmendments = async (contributionId: number): Promise<ContributionAmendment[]> => {
  const r = await API.get(`contributions/${contributionId}/amendments/`);
  return r.data;
};

export const proposeAmendment = async (
  contributionId: number,
  data: { changes: AmendmentChanges; reason?: string },
): Promise<ContributionAmendment> => {
  const r = await API.post(`contributions/${contributionId}/amendments/`, data);
  return r.data;
};

export const voteAmendment = async (
  amendmentId: number,
  vote: 'APPROVE' | 'REJECT',
): Promise<ContributionAmendment> => {
  const r = await API.post(`contributions/amendments/${amendmentId}/vote/`, { vote });
  return r.data;
};

export const withdrawAmendment = async (amendmentId: number): Promise<ContributionAmendment> => {
  const r = await API.post(`contributions/amendments/${amendmentId}/withdraw/`);
  return r.data;
};

// ---------------------------------------------------------------------------
// Join Requests & Invitations
// ---------------------------------------------------------------------------

export type ContributionJoinRequest = {
  id: number;
  contribution: number;
  phone_number: string;
  name: string | null;
  request_type: 'REQUEST' | 'INVITE';
  invited_by_phone: string | null;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  created_at: string;
  reviewed_at: string | null;
};

export const requestJoinContribution = async (contributionId: number): Promise<ContributionJoinRequest> => {
  const r = await API.post(`contributions/${contributionId}/join-requests/`);
  return r.data;
};

export const getPendingJoinRequests = async (contributionId: number): Promise<ContributionJoinRequest[]> => {
  const r = await API.get(`contributions/${contributionId}/join-requests/`);
  return r.data;
};

export const actionJoinRequest = async (
  requestId: number,
  action: 'approve' | 'reject',
): Promise<ContributionJoinRequest> => {
  const r = await API.post(`contributions/join-requests/${requestId}/action/`, { action });
  return r.data;
};

export const inviteMemberToContribution = async (
  contributionId: number,
  phone: string,
): Promise<ContributionJoinRequest> => {
  const r = await API.post(`contributions/${contributionId}/invite/`, { phone });
  return r.data;
};

export const respondToContributionInvite = async (
  requestId: number,
  action: 'accept' | 'decline',
): Promise<ContributionJoinRequest> => {
  const r = await API.post(`contributions/invitations/${requestId}/respond/`, { action });
  return r.data;
};

export const getMyContributionJoinRequest = async (contributionId: number): Promise<ContributionJoinRequest | null> => {
  const r = await API.get(`contributions/${contributionId}/my-join-request/`);
  return r.data ?? null;
};

export const getMyContributionInvite = async (contributionId: number): Promise<ContributionJoinRequest | null> => {
  const r = await API.get(`contributions/${contributionId}/my-invite/`);
  return r.data ?? null;
};

export const getParticipants = async (id: number): Promise<Participant[]> => {
  const r = await API.get(`contributions/${id}/participants/`);
  return r.data;
};

export const contribute = async (contributionId: number, amount: number, pin: string) => {
  const r = await API.post(
    "contributions/contribute/",
    { contribution_id: contributionId, amount },
    { headers: { "X-Pin": pin } },
  );
  return r.data;
};

export const getMyTransactions = async (): Promise<Transaction[]> => {
  const r = await API.get("contributions/transactions/");
  return r.data.results ?? r.data;
};

export const getContributionTransactions = async (contributionId: number): Promise<Transaction[]> => {
  const r = await API.get(`contributions/${contributionId}/transactions/`);
  return r.data.results ?? r.data;
};

// ---------------------------------------------------------------------------
// ROSCA
// ---------------------------------------------------------------------------

export const getROSCARotation = async (contributionId: number): Promise<ROSCASlot[]> => {
  const r = await API.get(`contributions/${contributionId}/rosca/`);
  return r.data;
};

export const initializeROSCA = async (contributionId: number): Promise<ROSCASlot[]> => {
  const r = await API.post(`contributions/${contributionId}/rosca/`);
  return r.data;
};

export const advanceROSCASlot = async (contributionId: number): Promise<ROSCASlot> => {
  const r = await API.post(`contributions/${contributionId}/rosca/advance/`);
  return r.data;
};

// ---------------------------------------------------------------------------
// Disbursements
// ---------------------------------------------------------------------------

export const getDisbursements = async (contributionId: number): Promise<DisbursementRequest[]> => {
  const r = await API.get(`contributions/${contributionId}/disbursements/`);
  return r.data.results ?? r.data;
};

export const createDisbursement = async (
  contributionId: number,
  data: { amount: number | string; reason: string; recipient_phone?: string }
): Promise<DisbursementRequest> => {
  const r = await API.post(`contributions/${contributionId}/disbursements/`, data);
  return r.data;
};

export const voteDisbursement = async (
  requestId: number,
  vote: 'APPROVE' | 'REJECT'
): Promise<DisbursementRequest> => {
  const r = await API.post(`contributions/disbursements/${requestId}/vote/`, { vote });
  return r.data;
};

export const cancelDisbursementRequest = async (requestId: number): Promise<DisbursementRequest> => {
  const r = await API.post(`contributions/disbursements/${requestId}/cancel/`);
  return r.data;
};

// ---------------------------------------------------------------------------
// Collective-fund actions (ADR-0027) — pool expense & surplus distribution are
// maker-checked; external income (money in) is a direct admin action.
// ---------------------------------------------------------------------------

export const recordExternalIncome = async (
  contributionId: number,
  data: { amount: number | string; source?: string }
): Promise<{ reference: string; id: number }> => {
  const r = await API.post(`contributions/${contributionId}/external-income/`, data);
  return r.data;
};

export const requestPoolExpense = async (
  contributionId: number,
  data: { amount: number | string; apportion?: string; reason?: string }
): Promise<PoolActionRequest> => {
  const r = await API.post(`contributions/${contributionId}/pool-expense/`, data);
  return r.data;
};

export const requestDistribution = async (
  contributionId: number,
  data: { amount: number | string; apportion?: string; reason?: string }
): Promise<PoolActionRequest> => {
  const r = await API.post(`contributions/${contributionId}/distribute/`, data);
  return r.data;
};

export const getPoolActions = async (contributionId: number): Promise<PoolActionRequest[]> => {
  const r = await API.get(`contributions/${contributionId}/pool-actions/`);
  return r.data.results ?? r.data;
};

export const approvePoolAction = async (requestId: number): Promise<PoolActionRequest> => {
  const r = await API.post(`contributions/pool-actions/${requestId}/approve/`);
  return r.data;
};

export const rejectPoolAction = async (
  requestId: number, reason?: string
): Promise<PoolActionRequest> => {
  const r = await API.post(`contributions/pool-actions/${requestId}/reject/`, { reason });
  return r.data;
};

export const cancelPoolAction = async (requestId: number): Promise<PoolActionRequest> => {
  const r = await API.post(`contributions/pool-actions/${requestId}/cancel/`);
  return r.data;
};

// ---------------------------------------------------------------------------
// Shares Fund (community-scoped)
// ---------------------------------------------------------------------------

export const getCommunitySharesFund = async (communityId: number): Promise<SharesFund> => {
  const r = await API.get(`contributions/shares/${communityId}/`);
  return r.data;
};

export const addToShares = async (communityId: number, amount: number): Promise<SharesFund> => {
  const r = await API.post(`contributions/shares/${communityId}/contribute/`, { amount });
  return r.data;
};

// ---------------------------------------------------------------------------
// Welfare Fund (community-scoped)
// ---------------------------------------------------------------------------

export const getWelfareFund = async (communityId: number): Promise<WelfareFund> => {
  const r = await API.get(`contributions/welfare/${communityId}/`);
  return r.data;
};

export const contributeToWelfare = async (communityId: number, amount: number): Promise<WelfareFund> => {
  const r = await API.post(`contributions/welfare/${communityId}/contribute/`, { amount });
  return r.data;
};

export const getWelfareClaims = async (communityId: number): Promise<WelfareClaim[]> => {
  const r = await API.get(`contributions/welfare/${communityId}/claims/`);
  return r.data.results ?? r.data;
};

export const submitWelfareClaim = async (
  communityId: number,
  data: { amount_requested: number | string; reason: string }
): Promise<WelfareClaim> => {
  const r = await API.post(`contributions/welfare/${communityId}/claims/`, data);
  return r.data;
};

export const getWelfareActivity = async (communityId: number): Promise<WelfareActivity[]> => {
  const r = await API.get(`contributions/welfare/${communityId}/activity/`);
  return r.data;
};

export const voteWelfareClaim = async (
  claimId: number,
  action: 'approve' | 'reject'
): Promise<WelfareClaim> => {
  const r = await API.post(`contributions/welfare/claims/${claimId}/vote/`, { action });
  return r.data;
};

// ---------------------------------------------------------------------------
// Emergency Advances
// ---------------------------------------------------------------------------

export const getAdvances = async (contributionId: number): Promise<EmergencyAdvance[]> => {
  const r = await API.get(`contributions/${contributionId}/advances/`);
  return r.data.results ?? r.data;
};

export const getMyAdvances = async (): Promise<EmergencyAdvance[]> => {
  const r = await API.get("contributions/advances/mine/");
  return r.data.results ?? r.data;
};

export const requestAdvance = async (
  contributionId: number,
  data: { amount: number | string; interest_rate?: number | string; repayment_due?: string }
): Promise<EmergencyAdvance> => {
  const r = await API.post(`contributions/${contributionId}/advances/`, data);
  return r.data;
};

export const actionAdvance = async (
  advanceId: number,
  action: 'approve' | 'reject' | 'repay',
  amount?: number
): Promise<EmergencyAdvance> => {
  const r = await API.post(`contributions/advances/${advanceId}/action/`, { action, amount });
  return r.data;
};

// ---------------------------------------------------------------------------
// Standing Orders
// ---------------------------------------------------------------------------

export const getStandingOrders = async (contributionId: number): Promise<StandingOrder[]> => {
  const r = await API.get(`contributions/${contributionId}/standing-orders/`);
  return r.data;
};

export const createStandingOrder = async (contributionId: number, data: CreateStandingOrderPayload): Promise<StandingOrder> => {
  const r = await API.post(`contributions/${contributionId}/standing-orders/`, data);
  return r.data;
};

export const executeStandingOrder = async (orderId: number): Promise<StandingOrder> => {
  const r = await API.post(`contributions/standing-orders/${orderId}/execute/`);
  return r.data;
};

export const cancelStandingOrder = async (orderId: number): Promise<StandingOrder> => {
  const r = await API.post(`contributions/standing-orders/${orderId}/cancel/`);
  return r.data;
};

export type UpdateStandingOrderPayload = {
  amount?: number | string;
  frequency?: 'daily' | 'weekly' | 'monthly';
  fixed_payee_phone?: string | null;
};

export const updateStandingOrder = async (
  orderId: number,
  data: UpdateStandingOrderPayload,
): Promise<StandingOrder> => {
  const r = await API.patch(`contributions/standing-orders/${orderId}/update/`, data);
  return r.data;
};
