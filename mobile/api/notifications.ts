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
