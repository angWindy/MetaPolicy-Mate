import { apiRequest } from "../lib/api";
import type { PaginatedResponse } from "../types/api";
import type { UserResponse } from "../types/api";

export type { UserResponse };

export type ListUsersParams = {
  page?: number;
  page_size?: number;
  query?: string;
  is_active?: boolean;
  department_id?: string;
};

export interface CreateUserRequest {
  email: string;
  password: string;
  full_name: string;
  department_id: string | null;
}

export interface UpdateUserRequest {
  email: string;
  full_name: string;
  department_id: string | null;
}

export interface UpdateUserStatusRequest {
  is_active: boolean;
}

export interface RoleSummary {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  created_at: string | null;
}

export interface PermissionSummary {
  id: string;
  code: string;
  name: string;
  module: string;
  description: string | null;
}

function toQueryString(params: ListUsersParams): string {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  if (params.query) query.set("search", params.query);
  if (typeof params.is_active === "boolean") query.set("is_active", String(params.is_active));
  if (params.department_id) query.set("department_id", params.department_id);
  const value = query.toString();
  return value ? `?${value}` : "";
}

export const userService = {
  list(
    params: ListUsersParams = {},
    signal?: AbortSignal,
  ): Promise<PaginatedResponse<UserResponse>> {
    return apiRequest<PaginatedResponse<UserResponse>>(
      `/api/v1/users${toQueryString(params)}`,
      { signal },
    );
  },
  getById(id: string, signal?: AbortSignal): Promise<UserResponse> {
    return apiRequest<UserResponse>(`/api/v1/users/${id}`, { signal });
  },
  create(data: CreateUserRequest, signal?: AbortSignal): Promise<UserResponse> {
    return apiRequest<UserResponse>(`/api/v1/users`, {
      method: "POST",
      body: JSON.stringify(data),
      signal,
    });
  },
  update(
    id: string,
    data: UpdateUserRequest,
    signal?: AbortSignal,
  ): Promise<UserResponse> {
    return apiRequest<UserResponse>(`/api/v1/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      signal,
    });
  },
  updateStatus(
    id: string,
    data: UpdateUserStatusRequest,
    signal?: AbortSignal,
  ): Promise<UserResponse> {
    return apiRequest<UserResponse>(`/api/v1/users/${id}/status`, {
      method: "PUT",
      body: JSON.stringify(data),
      signal,
    });
  },
  /** Hard-delete a user. Returns 204 on success.
   * Cascades through refresh_tokens, user_roles, chat_sessions. */
  delete(id: string, signal?: AbortSignal): Promise<void> {
    return apiRequest<void>(`/api/v1/users/${id}`, {
      method: "DELETE",
      signal,
    });
  },
  /**
   * List roles assigned to a user.
   * Used by the "Phân quyền" drawer in the admin UI.
   */
  listRoles(userId: string, signal?: AbortSignal): Promise<RoleSummary[]> {
    return apiRequest<RoleSummary[]>(`/api/v1/rbac/users/${userId}/roles`, { signal });
  },
  /**
   * Replace a user's role assignment with the provided list of role ids.
   */
  updateRoles(
    userId: string,
    roleIds: string[],
    signal?: AbortSignal,
  ): Promise<RoleSummary[]> {
    return apiRequest<RoleSummary[]>(`/api/v1/rbac/users/${userId}/roles`, {
      method: "PUT",
      body: JSON.stringify({ role_ids: roleIds }),
      signal,
    });
  },
  /**
   * Resolve the user's effective permissions (through roles).
   * Read-only — used by the "Quyền hiệu lực" drawer.
   */
  getPermissions(
    userId: string,
    signal?: AbortSignal,
  ): Promise<PermissionSummary[]> {
    return apiRequest<PermissionSummary[]>(
      `/api/v1/rbac/users/${userId}/permissions`,
      { signal },
    );
  },
};
