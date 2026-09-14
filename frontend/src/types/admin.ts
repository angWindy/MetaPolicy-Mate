export type AdminDocumentStatus =
  | "CHO_XU_LY_NOI_DUNG"
  | "DANG_HIEU_LUC"
  | "BI_THAY_THE"
  | "HET_HIEU_LUC"
  | "BAN_NHAP";

export type AdminDocument = {
  id: string;
  documentNumber: string;
  title: string;
  documentType: string;
  version: string;
  status: AdminDocumentStatus;
  issuedDate: string;
  effectiveDate: string;
  issuer: string;
  updatedAt: string | null;
  updatedBy: string;
  createdAt: string | null;
  /**
   * Latest ``document_version.id`` row. Used by AdminDocuments.tsx to poll
   * status and call the per-version delete endpoint.
   */
  versionId?: string | null;
  /** Raw processing_status string from the RAG pipeline. */
  processingStatus?: string;
};

export type AdminStats = {
  totalDocuments: number;
  activeDocuments: number;
  pendingDocuments: number;
  expiredDocuments: number;
  users: number;
  questionsToday: number;
  asOf?: string;
};
