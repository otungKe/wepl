import API from "./client";

export type VerificationKind =
  | "transaction_docs"
  | "address_proof"
  | "kyc_supplement"
  | "clarification"
  | "other";

export type VerificationStatus = "open" | "submitted" | "resolved";

export type VerificationRequest = {
  id: number;
  kind: VerificationKind;
  kind_label: string;
  title: string;
  detail: string;
  status: VerificationStatus;
  status_label: string;
  response_note: string;
  document: string | null;
  review_note: string;
  created_at: string;
  responded_at: string | null;
  resolved_at: string | null;
};

/** The current user's ongoing verification requests (Verification Center). */
export const getVerificationRequests = async (): Promise<VerificationRequest[]> => {
  const r = await API.get("users/verification-requests/");
  return r.data?.results ?? r.data;
};

/** Answer an open request with a note and/or an attached document. */
export const respondToVerificationRequest = async (
  id: number,
  payload: { response_note?: string; document?: { uri: string; name: string; type: string } },
): Promise<VerificationRequest> => {
  const form = new FormData();
  if (payload.response_note) form.append("response_note", payload.response_note);
  if (payload.document) form.append("document", payload.document as any);
  const r = await API.post(`users/verification-requests/${id}/respond/`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return r.data;
};
