import API from "./client";

export type JoinPolicy            = 'open' | 'request' | 'invite_only';
export type InvitePermission      = 'admins' | 'members' | 'creator';
export type ContributionPermission = 'admins' | 'members';
export type MemberListVisibility  = 'all' | 'admins';

export type Community = {
  id: number;
  name: string;
  description: string | null;
  community_photo: string | null;
  is_private: boolean;
  invite_code: string;
  has_welfare_fund: boolean;
  has_shares_fund: boolean;
  category: string;
  location: string;
  created_by: string;
  created_by_name: string;
  member_count: number;
  is_member: boolean;
  join_request_status: 'PENDING' | 'APPROVED' | 'REJECTED' | null;
  created_at: string;
  // Section A governance
  join_policy:             JoinPolicy;
  invite_permission:       InvitePermission;
  contribution_permission: ContributionPermission;
  member_list_visibility:  MemberListVisibility;
  max_members:             number | null;
  cooling_off_days:        number;
};

export type CommunityMember = {
  id: number;
  phone_number: string | null;
  name: string;
  profile_photo: string | null;
  role: 'admin' | 'member' | 'treasurer';
  is_active: boolean;
  is_online: boolean | null;   // null = user has opted out of showing status
};

export const getMyCommunities = async (): Promise<Community[]> => {
  const r = await API.get("communities/");
  return r.data;
};

export type DiscoverCommunitiesPage = {
  count: number;
  has_more: boolean;
  results: Community[];
};

export const discoverCommunities = async (params?: {
  q?: string;
  category?: string;
  location?: string;
  limit?: number;
  offset?: number;
}): Promise<DiscoverCommunitiesPage> => {
  const r = await API.get("communities/discover/", { params });
  return r.data;
};

export const getCommunity = async (id: number): Promise<Community> => {
  const r = await API.get(`communities/${id}/`);
  return r.data;
};

export const createCommunity = async (data: {
  name: string;
  description?: string;
  is_private?: boolean;
  has_welfare_fund?: boolean;
  has_shares_fund?: boolean;
  share_price?: number;
  category?: string;
  location?: string;
}): Promise<Community> => {
  const r = await API.post("communities/create/", data);
  return r.data;
};

export const joinCommunity = async (id: number) => {
  const r = await API.post(`communities/${id}/join/`);
  return r.data;
};

export const leaveCommunity = async (id: number) => {
  const r = await API.post(`communities/${id}/leave/`);
  return r.data;
};

export const getCommunityMembers = async (id: number): Promise<CommunityMember[]> => {
  const r = await API.get(`communities/${id}/members/`);
  return r.data;
};

export const deleteCommunity = async (id: number) => {
  await API.delete(`communities/${id}/delete/`);
};

export const getCommunityByInviteCode = async (code: string): Promise<Community> => {
  const r = await API.get(`communities/invite/${code}/`);
  return r.data;
};

export const requestToJoinCommunity = async (code: string): Promise<{ id: number; status: string }> => {
  const r = await API.post(`communities/invite/${code}/request/`);
  return r.data;
};

/** Request to join by community ID — used when invite_code is not available (non-members). */
export const requestToJoinById = async (communityId: number): Promise<{ id: number; status: string }> => {
  const r = await API.post(`communities/${communityId}/request/`);
  return r.data;
};

export type PendingRequest = {
  id: number;
  community_id: number;
  community_name: string;
  community_photo: string | null;
  member_count: number;
  created_at: string;
};

/** Returns all of the current user's pending community join requests. */
export const getMyJoinRequests = async (): Promise<PendingRequest[]> => {
  const r = await API.get("communities/my-requests/");
  return r.data;
};

export const actionJoinRequest = async (reqId: number, action: 'approve' | 'reject') => {
  const r = await API.post(`communities/join-requests/${reqId}/action/`, { action });
  return r.data;
};

export const assignMemberRole = async (
  communityId: number,
  membershipId: number,
  role: 'admin' | 'member' | 'treasurer',
): Promise<CommunityMember> => {
  const r = await API.post(`communities/${communityId}/members/${membershipId}/role/`, { role });
  return r.data;
};

export const removeMember = async (communityId: number, membershipId: number): Promise<void> => {
  await API.delete(`communities/${communityId}/members/${membershipId}/`);
};

export const updateCommunity = async (
  id: number,
  data: { name?: string; description?: string; is_private?: boolean },
): Promise<Community> => {
  const r = await API.patch(`communities/${id}/update/`, data);
  return r.data;
};
