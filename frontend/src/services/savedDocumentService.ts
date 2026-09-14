import { apiRequest } from "../lib/api";

export interface SavedDocument {
  id: string;
  document_id: string;
  created_at: string;
}

export interface SavedDocumentListResponse {
  items: SavedDocument[];
  total: number;
  page: number;
  page_size: number;
}

export const savedDocumentService = {
  list(
    page: number = 1,
    pageSize: number = 20,
    signal?: AbortSignal,
  ): Promise<SavedDocumentListResponse> {
    return apiRequest<SavedDocumentListResponse>(
      `/api/v1/saved-documents?page=${page}&page_size=${pageSize}`,
      { signal },
    );
  },

  save(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<SavedDocument> {
    return apiRequest<SavedDocument>(
      `/api/v1/saved-documents/${encodeURIComponent(documentId)}`,
      { method: "POST", signal },
    );
  },

  unsave(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<void> {
    return apiRequest<void>(
      `/api/v1/saved-documents/${encodeURIComponent(documentId)}`,
      { method: "DELETE", signal },
    );
  },
};
