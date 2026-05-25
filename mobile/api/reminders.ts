import API from "./client";

export type ReminderType =
  | 'contribution_due'
  | 'welfare_contrib'
  | 'advance_repayment'
  | 'standing_order'
  | 'custom';

export type Recurrence = 'none' | 'daily' | 'weekly' | 'monthly';

export type Reminder = {
  id: number;
  reminder_type: ReminderType;
  title: string;
  note: string;
  contribution_id: number | null;
  community_id: number | null;
  scheduled_for: string;
  recurrence: Recurrence;
  next_fire_at: string;
  is_active: boolean;
  last_sent_at: string | null;
  send_count: number;
  is_overdue: boolean;
  created_at: string;
};

export type CreateReminderPayload = {
  reminder_type: ReminderType;
  title: string;
  note?: string;
  contribution_id?: number | null;
  community_id?: number | null;
  scheduled_for: string;   // ISO8601
  recurrence: Recurrence;
};

export const getReminders = async (active = true): Promise<Reminder[]> => {
  const r = await API.get("reminders/", { params: { active } });
  return r.data;
};

export const getUpcomingReminders = async (limit = 5): Promise<Reminder[]> => {
  const r = await API.get("reminders/upcoming/", { params: { limit } });
  return r.data;
};

export const createReminder = async (data: CreateReminderPayload): Promise<Reminder> => {
  const r = await API.post("reminders/", data);
  return r.data;
};

export const updateReminder = async (
  id: number,
  data: Partial<{ title: string; note: string; scheduled_for: string; recurrence: Recurrence; is_active: boolean }>,
): Promise<Reminder> => {
  const r = await API.patch(`reminders/${id}/`, data);
  return r.data;
};

export const deleteReminder = async (id: number): Promise<void> => {
  await API.delete(`reminders/${id}/`);
};
