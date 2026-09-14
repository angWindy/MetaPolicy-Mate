export type SuggestedQuestion = {
  id: string;
  text: string;
};

export type PolicyTopic = {
  id: string;
  title: string;
  description: string;
  href: string;
  icon?: string;
  shortLabel?: string;
};

export type RecentDocumentStatus = "active" | "updated" | "expired";

export type RecentDocument = {
  id: string;
  title: string;
  type?: string;
  documentNumber?: string;
  version?: string;
  updatedAt: string;
  updatedLabel: string;
  status: RecentDocumentStatus;
  statusLabel: string;
  href: string;
};

export type SearchStatus = "answered" | "processing" | "failed";

export type RecentSearch = {
  id: string;
  question: string;
  searchedAt: string;
  timeLabel: string;
  href: string;
  status?: SearchStatus;
  statusLabel?: string;
};

