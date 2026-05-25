import API from "./client";

export type Activity = {
  id: number;
  user: string;
  activity_type: string;
  message: string;
  created_at: string;
};

export type ActivityPage = {
  count: number;
  results: Activity[];
  has_more: boolean;
};

export const getActivity = async (params?: {
  type?: string;
  limit?: number;
  offset?: number;
}): Promise<ActivityPage> => {
  const r = await API.get("activity/", { params });
  return r.data;
};

export const getFinancialSummary = async () => {
  const r = await API.get("users/financial-summary/");
  return r.data as {
    total_contributed:    number;
    total_received:       number;
    active_contributions: number;
    total_contributions:  number;
    pending_advances:     number;
    advance_balance_due:  number;
    this_month:           number;
    last_month:           number;
    monthly_trend:        { month: string; amount: number }[];
    tx_count:             number;
    member_since:         string;
    kyc_status:           'approved' | 'pending' | 'rejected' | 'not_submitted';
  };
};
