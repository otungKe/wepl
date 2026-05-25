import API from "./client";

export type Conversation = {
  id: number;
  community: number;
  topic: string;
  photo: string | null;
  created_by: string;
  created_at: string;
  message_count: number;
  unread_count: number;
  last_message: {
    content: string;
    sender: string;
    created_at: string;
    message_type: string;
  } | null;
};

export type ReplyTo = {
  id: number;
  deleted: boolean;
  sender: string;
  content: string;
  message_type: 'text' | 'image' | 'voice' | 'video' | 'system';
  attachment: string | null;
};

export type Reactions = Record<string, string[]>; // emoji → [phone, ...]

export type Message = {
  id: number;
  sender: string;
  sender_phone: string;
  content: string;
  message_type: 'text' | 'image' | 'voice' | 'video' | 'system';
  attachment: string | null;
  reply_to: ReplyTo | null;
  reactions: Reactions;
  is_edited: boolean;
  created_at: string;
};

export const getCommunityConversations = async (communityId: number): Promise<Conversation[]> => {
  const r = await API.get(`conversations/community/${communityId}/`);
  return r.data;
};

export const createConversation = async (
  communityId: number,
  data: { topic: string }
): Promise<Conversation> => {
  const r = await API.post(`conversations/community/${communityId}/`, data);
  return r.data;
};

export const getConversation = async (id: number): Promise<Conversation> => {
  const r = await API.get(`conversations/${id}/`);
  return r.data;
};

export const deleteConversation = async (id: number) => {
  await API.delete(`conversations/${id}/`);
};

export const getMessages = async (conversationId: number): Promise<Message[]> => {
  const r = await API.get(`conversations/${conversationId}/messages/`);
  return r.data;
};

export const sendMessage = async (
  conversationId: number,
  content: string,
  attachmentUri?: string,
  replyToId?: number,
  mediaType: 'image' | 'video' = 'image',
): Promise<Message> => {
  if (attachmentUri) {
    const form = new FormData();
    if (content) form.append('content', content);
    if (replyToId) form.append('reply_to_id', String(replyToId));
    form.append('message_type', mediaType);
    const filename = attachmentUri.split('/').pop() ?? 'photo.jpg';
    const ext = filename.split('.').pop()?.toLowerCase() ?? 'jpg';
    const mimeMap: Record<string, string> = {
      jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif',
      mp4: 'video/mp4', mov: 'video/quicktime', avi: 'video/x-msvideo',
    };
    const mime = mimeMap[ext] ?? 'image/jpeg';
    form.append('attachment', { uri: attachmentUri, name: filename, type: mime } as any);
    const r = await API.post(`conversations/${conversationId}/messages/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return r.data;
  }
  const r = await API.post(`conversations/${conversationId}/messages/`, { content, reply_to_id: replyToId });
  return r.data;
};

export const sendVoiceMessage = async (
  conversationId: number,
  audioUri: string,
  replyToId?: number,
): Promise<Message> => {
  const form = new FormData();
  form.append('message_type', 'voice');
  if (replyToId) form.append('reply_to_id', String(replyToId));
  const filename = audioUri.split('/').pop() ?? 'voice.m4a';
  form.append('attachment', { uri: audioUri, name: filename, type: 'audio/m4a' } as any);
  const r = await API.post(`conversations/${conversationId}/messages/`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return r.data;
};

export const deleteMessage = async (messageId: number) => {
  await API.delete(`conversations/messages/${messageId}/delete/`);
};

export const bulkDeleteMessages = async (conversationId: number, ids: number[]): Promise<number[]> => {
  const r = await API.post(`conversations/${conversationId}/messages/bulk-delete/`, { ids });
  return r.data.deleted;
};

export const editMessage = async (messageId: number, content: string): Promise<void> => {
  await API.patch(`conversations/messages/${messageId}/edit/`, { content });
};

export const reactToMessage = async (messageId: number, emoji: string): Promise<{ action: string }> => {
  const r = await API.post(`conversations/messages/${messageId}/react/`, { emoji });
  return r.data;
};

export const markConversationRead = async (conversationId: number) => {
  await API.post(`conversations/${conversationId}/read/`);
};

export type UnreadSummary = {
  total: number;
  by_community: Record<string, number>;
};

export const getUnreadSummary = async (): Promise<UnreadSummary> => {
  const r = await API.get('conversations/unread/');
  return r.data;
};
