import API from "./client";

export type Notification = {
  id: number;
  notification_type: string;
  title: string;
  message: string;
  is_read: boolean;
  community_id: number | null;
  conversation_id: number | null;
  contribution_id: number | null;
  join_request_id: number | null;
  join_request_status: 'PENDING' | 'APPROVED' | 'REJECTED' | null;
  created_at: string;
};

export const getNotifications = async (): Promise<Notification[]> => {
  const r = await API.get("notifications/");
  return r.data;
};

export const getUnreadCount = async (): Promise<number> => {
  const r = await API.get("notifications/unread-count/");
  return r.data.unread_count;
};

export const markRead = async (id: number) => {
  await API.post(`notifications/${id}/read/`);
};

export const markAllRead = async () => {
  await API.post("notifications/read-all/");
};

export const deleteNotification = async (id: number) => {
  await API.delete(`notifications/${id}/delete/`);
};

export const deleteAllNotifications = async () => {
  await API.delete("notifications/delete-all/");
};

/** Register or refresh an FCM device token with the backend (Issue 19). */
export const registerDevice = async (
  fcmToken: string,
  platform: "android" | "ios"
): Promise<void> => {
  await API.post("notifications/devices/", { fcm_token: fcmToken, platform });
};

/** Unregister a device token on logout so stale tokens don't accumulate. */
export const unregisterDevice = async (fcmToken: string): Promise<void> => {
  await API.delete("notifications/devices/", { data: { fcm_token: fcmToken } });
};

export type NotifPrefs = {
  push_enabled:  boolean;
  payments:      boolean;
  contributions: boolean;
  reminders:     boolean;
  communities:   boolean;
  advances:      boolean;
  security:      boolean;  // read-only, mandatory (server never lets it turn off)
};

/** Fetch the user's server-side notification preferences. */
export const getNotifPrefs = async (): Promise<NotifPrefs> => {
  const r = await API.get("notifications/preferences/");
  return r.data;
};

/** Persist one or more preference flags to the server. */
export const updateNotifPrefs = async (patch: Partial<NotifPrefs>): Promise<NotifPrefs> => {
  const r = await API.patch("notifications/preferences/", patch);
  return r.data;
};
