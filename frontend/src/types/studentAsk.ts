export type StudentAnswerCitation = {
  id: string;
  sourceId: string;
  label: string;
  article: string;
  page: number;
  href: string;
};

export type StudentSourceValidity = "current" | "superseded" | "expired";

export type StudentAnswerSource = {
  id: string;
  title: string;
  documentType: string;
  validity: StudentSourceValidity;
  validityLabel: string;
  article: string;
  page: number;
  version: string;
  effectiveDate: string;
  effectiveDateLabel: string;
  confidence: number;
  preview: string;
  href: string;
};

export type StudentAnswerCondition = {
  id: string;
  text: string;
  citationIds: string[];
};

export type StudentAskMock = {
  question: string;
  followUpQuestions: string[];
  answer: {
    conclusion: string;
    conditions: StudentAnswerCondition[];
    note: string;
    confidence: number;
    citations: StudentAnswerCitation[];
  };
  sources: StudentAnswerSource[];
};
