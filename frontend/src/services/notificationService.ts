import { apiRequest } from "../lib/api";

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  related_document_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
}

export const notificationService = {
  list(
    page: number = 1,
    pageSize: number = 20,
    unreadOnly: boolean = false,
    signal?: AbortSignal,
  ): Promise<NotificationListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (unreadOnly) params.set("unread_only", "true");
    return apiRequest<NotificationListResponse>(
      `/api/v1/notifications?${params.toString()}`,
      { signal },
    );
  },

  unreadCount(signal?: AbortSignal): Promise<{ unread_count: number }> {
    return apiRequest<{ unread_count: number }>(
      `/api/v1/notifications/unread-count`,
      { signal },
    );
  },

  markRead(
    notificationId: string,
    signal?: AbortSignal,
  ): Promise<{ success: boolean; unread_count: number }> {
    return apiRequest<{ success: boolean; unread_count: number }>(
      `/api/v1/notifications/${encodeURIComponent(notificationId)}/read`,
      { method: "POST", signal },
    );
  },

  markAllRead(signal?: AbortSignal): Promise<{ marked_count: number }> {
    return apiRequest<{ marked_count: number }>(
      `/api/v1/notifications/read-all`,
      { method: "POST", signal },
    );
  },
};
