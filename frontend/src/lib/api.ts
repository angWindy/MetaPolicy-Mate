import { apiRequest } from "./api/index";
import { ApiClientError } from "./api/index";
import type {
  ChatResponse,
  ChatSession,
  ChatSessionWithTurns,
  Document,
  DocumentStats,
  IngestResponse,
  MetadataPreview,
  VersionStatusResponse,
} from "./types";

export { ApiClientError, apiRequest };

/** Wrapper functions gọi qua apiRequest (lib/api/client) - thay thế các hàm cũ dùng fetch+hardcode headers.
 *  URL đã được sửa cho khớp với backend hiện tại (/api/v1/*). */

export async function sendChatMessage(
  message: string,
  sessionId?: string | null,
): Promise<ChatResponse> {
  return apiRequest<ChatResponse>("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      session_id: sessionId || undefined,
    }),
  });
}

export async function listChatSessions(): Promise<ChatSession[]> {
  return apiRequest<ChatSession[]>("/api/v1/chat/sessions");
}

export async function getChatSession(
  sessionId: string,
): Promise<ChatSessionWithTurns> {
  return apiRequest<ChatSessionWithTurns>(
    `/api/v1/chat/sessions/${sessionId}`,
  );
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  return apiRequest(`/api/v1/chat/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function reportAnswer(
  turnId: string,
  comment?: string,
): Promise<{ feedback_id: string; turn_id: string; feedback_type: string }> {
  return apiRequest(`/api/v1/chat/turns/${turnId}/report`, {
    method: "POST",
    body: JSON.stringify({ comment: comment || undefined }),
  });
}

export async function getDocuments(): Promise<Document[]> {
  const res = await apiRequest<{ items: Document[]; total: number }>(
    "/api/v1/regulatory-documents?page=1&page_size=100",
  );
  return res.items;
}

export async function getStats(): Promise<DocumentStats> {
  return apiRequest<DocumentStats>("/api/v1/admin/stats");
}

export async function ingestDocument(file: File): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  // Use the clean-arch upload endpoint which persists the file in the
  // tenant database. The legacy RAG `/admin/documents/ingest` route uses
  // a separate schema (legacy ``document_versions`` columns) that hasn't
  // been migrated into the tenant DB, so going through it from the UI would
  // surface a 500. See WORKLOG.md "Bugfix đợt 6" for the analysis.
  return apiRequest<IngestResponse>("/api/v1/regulatory-documents/upload", {
    method: "POST",
    body: formData,
  });
}

export async function approveVersion(versionId: string): Promise<unknown> {
  return apiRequest(`/api/v1/admin/documents/${versionId}/approve`, {
    method: "POST",
  });
}

export async function indexVersion(versionId: string): Promise<unknown> {
  return apiRequest(`/api/v1/admin/documents/${versionId}/index`, {
    method: "POST",
  });
}

export async function publishVersion(versionId: string): Promise<unknown> {
  return apiRequest(`/api/v1/admin/documents/${versionId}/publish`, {
    method: "POST",
  });
}

export async function previewMetadata(file: File): Promise<MetadataPreview> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<MetadataPreview>("/api/v1/admin/documents/preview-metadata", {
    method: "POST",
    body: formData,
  });
}

export async function fetchVersionStatus(versionId: string): Promise<VersionStatusResponse> {
  return apiRequest<VersionStatusResponse>(`/api/v1/admin/documents/${versionId}/status`);
}

export async function deleteVersion(versionId: string): Promise<{ version_id: string; document_id: string; document_deleted: boolean }> {
  return apiRequest(`/api/v1/admin/documents/${versionId}`, {
    method: "DELETE",
  });
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export interface RegisterResponse {
  access_token: string;
  refresh_token: string;
  expires_at: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  department: string | null;
}

export interface RegisterError {
  detail?: string;
  message?: string;
}

export async function registerUser(
  email: string,
  password: string,
  fullName: string,
  schoolCode: string,
): Promise<RegisterResponse> {
  return apiRequest<RegisterResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      full_name: fullName,
      school_code: schoolCode,
    }),
  });
}
