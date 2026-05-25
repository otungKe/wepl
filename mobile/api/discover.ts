import API from "./client";

export type Campaign = {
  id: number;
  title: string;
  description: string | null;
  target_amount: number | null;
  current_amount: number;
  progress_pct: number | null;
  days_left: number | null;
  contributor_count: number;
  frequency: string;
  amount_type: string;
  fixed_amount: number | null;
  community: string | null;
  community_id: number | null;
  created_by: string;
  is_joined: boolean;
  invite_code: string;
  created_at: string;
};

export type CampaignPage = {
  count: number;
  has_more: boolean;
  results: Campaign[];
};

export const getCampaigns = async (params?: {
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<CampaignPage> => {
  const r = await API.get("contributions/campaigns/", { params });
  return r.data;
};
