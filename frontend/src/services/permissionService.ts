import { apiRequest } from "../lib/api";
import type { RoleSummary, PermissionSummary } from "./userService";

export interface CreateRoleRequest {
  code: string;
  name: string;
  description?: string | null;
}

export interface UpdateRoleRequest {
  name: string;
  description?: string | null;
}

export const permissionService = {
  /** List all roles (system + custom). */
  listRoles(signal?: AbortSignal): Promise<RoleSummary[]> {
    return apiRequest<RoleSummary[]>(`/api/v1/roles`, { signal });
  },
  getRole(roleId: string, signal?: AbortSignal): Promise<RoleSummary> {
    return apiRequest<RoleSummary>(`/api/v1/roles/${roleId}`, { signal });
  },
  createRole(
    data: CreateRoleRequest,
    signal?: AbortSignal,
  ): Promise<RoleSummary> {
    return apiRequest<RoleSummary>(`/api/v1/roles`, {
      method: "POST",
      body: JSON.stringify(data),
      signal,
    });
  },
  updateRole(
    roleId: string,
    data: UpdateRoleRequest,
    signal?: AbortSignal,
  ): Promise<RoleSummary> {
    return apiRequest<RoleSummary>(`/api/v1/roles/${roleId}`, {
      method: "PUT",
      body: JSON.stringify(data),
      signal,
    });
  },
  /** Hard-delete a custom (non-system) role. Returns 204 on success.
   * System roles return 409 Conflict from the backend. */
  deleteRole(roleId: string, signal?: AbortSignal): Promise<void> {
    return apiRequest<void>(`/api/v1/roles/${roleId}`, {
      method: "DELETE",
      signal,
    });
  },
  /** List all permissions (optionally filtered by module). */
  listPermissions(
    module?: string,
    signal?: AbortSignal,
  ): Promise<PermissionSummary[]> {
    const query = module ? `?module=${encodeURIComponent(module)}` : "";
    return apiRequest<PermissionSummary[]>(`/api/v1/rbac/permissions${query}`, {
      signal,
    });
  },
  /** List permissions currently assigned to a role. */
  getRolePermissions(
    roleId: string,
    signal?: AbortSignal,
  ): Promise<PermissionSummary[]> {
    return apiRequest<PermissionSummary[]>(
      `/api/v1/rbac/roles/${roleId}/permissions`,
      { signal },
    );
  },
  /** Replace a role's permission set. */
  updateRolePermissions(
    roleId: string,
    permissionIds: string[],
    signal?: AbortSignal,
  ): Promise<PermissionSummary[]> {
    return apiRequest<PermissionSummary[]>(
      `/api/v1/rbac/roles/${roleId}/permissions`,
      {
        method: "PUT",
        body: JSON.stringify({ permission_ids: permissionIds }),
        signal,
      },
    );
  },
};
