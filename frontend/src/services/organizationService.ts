import { apiRequest, ApiClientError } from "@/lib/api";

export interface DepartmentResponse {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}

export interface CreateDepartmentRequest {
  code: string;
  name: string;
}

export interface UpdateDepartmentRequest {
  name?: string;
  is_active?: boolean;
}

export const organizationService = {
  async list(signal?: AbortSignal): Promise<DepartmentResponse[]> {
    return apiRequest<DepartmentResponse[]>("/api/v1/departments", { signal });
  },

  async create(
    data: CreateDepartmentRequest,
    signal?: AbortSignal,
  ): Promise<DepartmentResponse> {
    return apiRequest<DepartmentResponse>("/api/v1/departments", {
      method: "POST",
      body: JSON.stringify(data),
      signal,
    });
  },

  async update(
    id: string,
    data: UpdateDepartmentRequest,
    signal?: AbortSignal,
  ): Promise<DepartmentResponse> {
    return apiRequest<DepartmentResponse>(`/api/v1/departments/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
      signal,
    });
  },
};
