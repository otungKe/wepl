import API from "./client";

export type UserSession = {
  sid: string;
  device_label: string;
  ip_address: string | null;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
};

/** Active sign-ins for this account (current device flagged). */
export const getSessions = async (): Promise<UserSession[]> => {
  const r = await API.get("users/sessions/");
  return r.data?.results ?? r.data;
};

/** Revoke a single session by its sid. */
export const revokeSession = async (sid: string): Promise<void> => {
  await API.post(`users/sessions/${sid}/revoke/`);
};

/** Sign out of every session except this device. Returns how many were revoked. */
export const revokeOtherSessions = async (): Promise<number> => {
  const r = await API.post("users/sessions/revoke-others/");
  return r.data?.revoked ?? 0;
};
