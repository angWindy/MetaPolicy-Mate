import { apiRequest } from "@/lib/api";

export type ActivityLog = {
  id: string;
  school_id: string | null;
  user_id: string | null;
  request_name: string;
  status: string;
  trace_id: string | null;
  ip_address: string | null;
  device_id: string | null;
  user_agent: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type ActivityLogList = {
  items: ActivityLog[];
  total: number;
  page: number;
  page_size: number;
};

export const systemService = {
  activityLogs: (signal?: AbortSignal): Promise<ActivityLogList> => apiRequest<ActivityLogList>("/api/v1/activity-logs?page=1&page_size=100", { signal }),
};
