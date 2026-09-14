export interface Citation {
  chunk_id: string;
  document_id: string;
  version_id: string;
  document_number: string;
  title: string;
  source: string;
  article: string | null;
  clause: string | null;
  point: string | null;
  section: string | null;
  page: number | null;
  source_url: string | null;
  excerpt: string;
  citation_kind: "winning" | "expanded";
  winning_chunk_id: string;
  rerank_score?: number | null;
}

export interface ChatResponse {
  /** The answer text from the RAG pipeline. May contain inline citation markers like [1], [2] */
  answer: string;
  citations: Citation[];
  warnings: string[];
  confidence: string;
  /** Session ID for continuing this conversation. */
  session_id?: string;
  /** Turn ID for this specific Q&A exchange. */
  turn_id?: string;
}

/** A chat session in the user's conversation list. */
export interface ChatSession {
  session_id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  turn_count: number;
}

/** A single turn (Q&A exchange) within a chat session. */
export interface ChatTurn {
  turn_id: string;
  question: string;
  answer: string;
  citations: Array<Record<string, unknown>>;
  created_at: string;
}

/** Full chat session with all its turns. */
export interface ChatSessionWithTurns {
  session_id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  turns: ChatTurn[];
}

/** Display message in the chat UI. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  timestamp: string;
  isLoading?: boolean;
  turn_id?: string;
}

export interface DocumentVersion {
  id: string;
  version_number: number;
  processing_status: string;
  legal_status: string;
  effective_from: string | null;
  effective_to: string | null;
}

export interface Document {
  id: string;
  title: string;
  document_number: string;
  owner_department: string;
  access_level: string;
  versions: DocumentVersion[];
}

export interface DocumentStats {
  documents: number;
  versions: number;
  chunks: number;
}

export interface IngestResponse {
  document_id: string;
  version_id: string;
  processing_status: string;
  section_count: number;
  chunk_count: number;
  warnings: string[];
  message?: string;
}

export interface VersionStatusResponse {
  version_id: string;
  document_id: string;
  processing_status: string;
  chunk_count: number;
  warnings: string[];
  error: string | null;
  job_status: string | null;
  in_flight: boolean;
}

export interface MetadataPreview {
  document_number: string | null;
  document_number_confidence: number;
  title: string | null;
  title_confidence: number;
  needs_human_review: boolean;
  rationale: string;
  warnings: string[];
}
