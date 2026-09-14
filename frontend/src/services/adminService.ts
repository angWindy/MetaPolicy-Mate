import { apiRequest } from "@/lib/api";
import type { AdminDocument, AdminStats, AdminDocumentStatus } from "@/types/admin";
import type { PaginatedResponse } from "@/types/api";
import type { PolicyDocument } from "@/types/documents";

export interface AdminDocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  processing_status: string;
  source_filename: string;
  size_bytes: number;
  object_key: string;
  created_at: string | null;
}

export interface AdminDocumentDetail {
  id: string;
  document_number: string;
  title: string;
  issued_by: string;
  issued_date: string;
  effective_date: string;
  legal_status: string;
  access_scope: "PUBLIC" | "DEPARTMENT";
  status: string;
  updated_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface UpdateDocumentMetadataRequest {
  document_number: string;
  title: string;
  issued_by: string;
  issued_date: string;
  effective_date: string;
  legal_status?: string | null;
}

export interface DocumentSection {
  id: string;
  section_type: string | null;
  section_number: string | null;
  heading: string | null;
  heading_path: string[];
  page: number | null;
  sort_order: number;
}

export interface DocumentAccess {
  document_id: string;
  access_scope: string;
  department_ids: string[];
  department_codes: string[];
}

export interface UpdateDocumentAccessRequest {
  access_scope: "PUBLIC" | "DEPARTMENT";
  department_ids: string[];
}

/** Map display status from BE (item.status = "current" | "superseded" | "expired") to AdminDocumentStatus. */
function mapStatusFromResponse(item: PolicyDocument): AdminDocumentStatus {
  // BE now returns a pre-computed `status` field: "current" | "superseded" | "expired"
  switch (item.status) {
    case "current":
      return "DANG_HIEU_LUC";
    case "superseded":
      return "BI_THAY_THE";
    case "expired":
      return "HET_HIEU_LUC";
    default:
      return "BAN_NHAP";
  }
}

/** API mapping for the backend admin surface. Pages may use mock data in demo mode. */
export const adminService = {
  stats(signal?: AbortSignal): Promise<AdminStats> {
    return apiRequest<AdminStats>("/api/v1/admin/stats", { signal });
  },

  /**
   * List documents via the clean-arch `/regulatory-documents` endpoint.
   * This is the source of truth for the operator UI: each row in the
   * tenant DB has a status that the UI maps to our admin status enum.
   */
  listDocuments(
    signal?: AbortSignal,
  ): Promise<{ items: AdminDocument[]; total: number }> {
    return apiRequest<{ items: PolicyDocument[]; total: number }>(
      "/api/v1/regulatory-documents?page=1&page_size=100",
      { signal },
    ).then((res) => {
      const mapped = (res.items ?? []).map((item) => ({
        id: item.id,
        documentNumber: item.documentNumber,
        title: item.title,
        documentType: "",
        version: "1",
        status: mapStatusFromResponse(item),
        issuedDate: item.issuedDate ?? "",
        effectiveDate: item.effectiveDate ?? "",
        issuer: item.issuedBy ?? "",
        updatedAt: item.updatedAt ?? null,
        updatedBy: item.updatedBy ?? "—",
        createdAt: item.createdAt ?? null,
      }));
      return { items: mapped, total: res.total ?? mapped.length };
    });
  },

  /**
   * Fetch a single document's full metadata via the clean-arch
   * `/regulatory-documents/{id}` endpoint. Used by the edit drawer
   * to pre-fill the form with current values.
   */
  getDocument(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<AdminDocumentDetail> {
    return apiRequest<AdminDocumentDetail>(
      `/api/v1/regulatory-documents/${documentId}`,
      { signal },
    );
  },

  /**
   * Update document metadata via PUT /regulatory-documents/{id}.
   * The endpoint requires document_number (immutable identifier in
   * the contract) plus the other editable metadata fields.
   */
  updateDocument(
    documentId: string,
    data: UpdateDocumentMetadataRequest,
    signal?: AbortSignal,
  ): Promise<AdminDocumentDetail> {
    return apiRequest<AdminDocumentDetail>(
      `/api/v1/regulatory-documents/${documentId}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
        signal,
      },
    );
  },

  /**
   * List all versions of a document. Used to render workflow buttons
   * (approve / index / publish) per version row in the admin UI.
   */
  listDocumentVersions(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<AdminDocumentVersion[]> {
    return apiRequest<AdminDocumentVersion[]>(
      `/api/v1/admin/documents/${documentId}/versions`,
      { signal },
    );
  },

  /**
   * Upload a document via the clean-arch `/regulatory-documents/upload`
   * endpoint. This persists the file and the metadata in the tenant DB
   * so the row appears in the list. RAG ingestion (parse → chunk → embed
   * → Qdrant upsert) is NOT triggered from this path — the bridge to the
   * legacy RAG pipeline needs a separate schema-migration step that is
   * tracked in WORKLOG.md "Bugfix đợt 6".
   */
  uploadDocument(formData: FormData, signal?: AbortSignal): Promise<unknown> {
    return apiRequest("/api/v1/regulatory-documents/upload", {
      method: "POST",
      body: formData,
      signal,
    });
  },

  approveVersion(versionId: string, signal?: AbortSignal): Promise<unknown> {
    return apiRequest(`/api/v1/admin/documents/${versionId}/approve`, {
      method: "POST",
      signal,
    });
  },

  indexVersion(versionId: string, signal?: AbortSignal): Promise<unknown> {
    return apiRequest(`/api/v1/admin/documents/${versionId}/index`, {
      method: "POST",
      signal,
    });
  },

  publishVersion(versionId: string, signal?: AbortSignal): Promise<unknown> {
    return apiRequest(`/api/v1/admin/documents/${versionId}/publish`, {
      method: "POST",
      signal,
    });
  },

  deleteDocument(documentId: string, signal?: AbortSignal): Promise<void> {
    return apiRequest<void>(
      `/api/v1/regulatory-documents/${documentId}`,
      { method: "DELETE", signal },
    );
  },

  /**
   * Delete a single document version via the legacy admin endpoint.
   * The legacy endpoint takes ``version_id`` (not document_id) and hard-
   * deletes the version plus its chunks/sections when the version is in a
   * non-production terminal state (``failed`` or ``draft``).
   */
  deleteVersion(versionId: string, signal?: AbortSignal): Promise<void> {
    return apiRequest<void>(
      `/api/v1/admin/documents/${versionId}`,
      { method: "DELETE", signal },
    );
  },

  /** Poll a version's processing status while ingestion is in flight. */
  getVersionStatus(
    versionId: string,
    signal?: AbortSignal,
  ): Promise<{
    version_id: string;
    processing_status: string;
    chunk_count: number;
    in_flight: boolean;
  }> {
    return apiRequest(`/api/v1/admin/documents/${versionId}/status`, { signal });
  },

  /**
   * List the structural sections of a regulatory document
   * (Điều/Khoản/Chương) for the admin detail page.
   * Requires `document.read` and document access permission.
   */
  getDocumentSections(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<DocumentSection[]> {
    return apiRequest<DocumentSection[]>(
      `/api/v1/regulatory-documents/${documentId}/sections`,
      { signal },
    );
  },

  /**
   * Read the document's current access scope + assigned departments.
   * Returns the live access config from the tenant DB.
   */
  getDocumentAccess(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<DocumentAccess> {
    return apiRequest<DocumentAccess>(
      `/api/v1/regulatory-documents/${documentId}/access`,
      { signal },
    );
  },

  /**
   * Replace the document's access scope + assigned departments.
   * When `access_scope == PUBLIC` the department list is ignored.
   */
  updateDocumentAccess(
    documentId: string,
    data: UpdateDocumentAccessRequest,
    signal?: AbortSignal,
  ): Promise<void> {
    return apiRequest<void>(
      `/api/v1/regulatory-documents/${documentId}/access`,
      {
        method: "PUT",
        body: JSON.stringify(data),
        signal,
      },
    );
  },

  /**
   * URL used by the PDF iframe viewer to load the source PDF inline.
   * Caller is responsible for adding the auth token; the FE does this
   * via the apiRequest wrapper for non-iframe fetches. For iframe,
   * use a fetch+blob URL pattern instead — see DocumentPdfViewer.
   */
  getDocumentSourceUrl(documentId: string): string {
    return `/api/v1/regulatory-documents/${documentId}/source`;
  },
};

// Re-export Paginated type for convenience
export type { PaginatedResponse };
