import API from "./client";

export type STKPushResult = {
  message: string;
  checkout_request_id: string;
};

export type STKStatus = {
  status: 'PENDING' | 'SUCCESS' | 'FAILED';
  mpesa_receipt: string | null;
};

export const initiateSTKPush = async (data: {
  payment_type?: 'contribution' | 'welfare' | 'shares';
  contribution_id?: number;
  community_id?: number;
  amount: number;
  phone_number?: string;
}): Promise<STKPushResult> => {
  const r = await API.post("mpesa/stk/push/", data);
  return r.data;
};

export const checkSTKStatus = async (checkoutRequestId: string): Promise<STKStatus> => {
  const r = await API.get(`mpesa/stk/status/${checkoutRequestId}/`);
  return r.data;
};
