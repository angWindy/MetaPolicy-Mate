import { apiRequest } from "../lib/api";
import type { DocumentListResponse } from "../types/api";
import type { PolicyDocument } from "../types/documents";

export type DocumentListParams = {
  query?: string;
  category?: string;
  status?: string;
};

function toQueryString(params: DocumentListParams): string {
  const query = new URLSearchParams();
  if (params.query) query.set("query", params.query);
  if (params.category) query.set("category", params.category);
  if (params.status) query.set("status", params.status);
  const value = query.toString();
  return value ? `?${value}` : "";
}

export const documentService = {
  list(
    params: DocumentListParams = {},
    signal?: AbortSignal,
  ): Promise<DocumentListResponse> {
    return apiRequest<DocumentListResponse>(
      `/api/v1/documents${toQueryString(params)}`,
      { signal },
    );
  },

  getById(id: string, signal?: AbortSignal): Promise<PolicyDocument> {
    return apiRequest<PolicyDocument>(
      `/api/v1/documents/${encodeURIComponent(id)}`,
      { signal },
    );
  },
};

