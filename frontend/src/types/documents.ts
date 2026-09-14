export type LibraryDocumentStatus = "current" | "superseded" | "expired";

export type PolicyDocument = {
  id: string;
  documentNumber: string;
  title: string;
  category: string;
  categoryLabel: string;
  version: string;
  effectiveDate: string;
  effectiveDateLabel: string;
  status: LibraryDocumentStatus;
  statusLabel: string;
  href: string;
  /** From RegulatoryDocumentResponse */
  issuedBy?: string;
  issuedDate?: string;
  legalStatus?: string;
  accessScope?: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  updatedBy?: string;
};

export type DocumentContentSection = {
  id: string;
  heading: string;
  paragraphs: string[];
};

