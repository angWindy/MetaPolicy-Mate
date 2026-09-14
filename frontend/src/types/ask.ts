import type { AIAnswerBlock } from "./aiAnswer";

export type SourceValidityStatus = "current" | "expired" | "superseded";

export type ReferenceSource = {
  id: string;
  title: string;
  documentType: string;
  reference: string;
  page: number;
  version: string;
  effectiveDate: string;
  effectiveDateLabel: string;
  validityStatus: SourceValidityStatus;
  validityLabel: string;
  excerpt: string;
  href: string;
};

export type MockAskResponse = {
  answer: AIAnswerBlock[];
  confidence: number;
  sources: ReferenceSource[];
};

