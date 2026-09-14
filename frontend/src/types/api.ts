import type { PolicyDocument } from "./documents";

export type AskQuestionRequest = {
  message: string;
  as_of_date?: string;
};

export type BackendCitation = {
  chunk_id: string;
  document_id: string;
  version_id: string;
  document_number: string;
  title: string;
  source: string;
  article?: string | null;
  clause?: string | null;
  point?: string | null;
  section?: string | null;
  page?: number | null;
  source_url?: string | null;
  excerpt?: string;
};

export type AskQuestionResponse = {
  answer: string;
  citations: BackendCitation[];
  warnings: string[];
  confidence: string;
  session_id?: string;
  turn_id?: string;
};

export type DocumentListResponse = {
  items: PolicyDocument[];
  total: number;
};

export type UserResponse = {
  id: string;
  email: string;
  full_name: string;
  department_id: string | null;
  token_version: number;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
