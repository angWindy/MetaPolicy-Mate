export const SAVED_DOCUMENTS_KEY = "policymate.savedDocuments";
export const SAVED_ANSWERS_KEY = "policymate.savedAnswers";
export const NOTIFICATIONS_KEY = "policymate.notifications";
export const LOCAL_DATA_CHANGED_EVENT = "policymate:local-data-changed";

export type SavedAnswerRecord = {
  id: string;
  turnId?: string;
  question?: string;
  answer: string;
  savedAt: string;
};

export type LocalNotification = {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  read: boolean;
  href?: string;
};

function storage(): Storage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

function readArray(key: string): unknown[] {
  try {
    const raw = storage()?.getItem(key);
    const value: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function write(key: string, value: unknown): void {
  const target = storage();
  if (!target) return;
  target.setItem(key, JSON.stringify(value));
  window.dispatchEvent(new CustomEvent(LOCAL_DATA_CHANGED_EVENT, { detail: { key } }));
}

export const localData = {
  savedDocumentIds(): string[] {
    return Array.from(new Set(readArray(SAVED_DOCUMENTS_KEY).filter((item): item is string => typeof item === "string" && Boolean(item.trim()))));
  },
  setSavedDocumentIds(ids: string[]): void {
    write(SAVED_DOCUMENTS_KEY, Array.from(new Set(ids.filter(Boolean))));
  },
  savedAnswers(): SavedAnswerRecord[] {
    return readArray(SAVED_ANSWERS_KEY).flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const value = item as Partial<SavedAnswerRecord>;
      if (typeof value.answer !== "string" || !value.answer.trim()) return [];
      return [{
        id: typeof value.id === "string" ? value.id : value.turnId || `saved-${value.savedAt || value.answer.slice(0, 24)}`,
        turnId: typeof value.turnId === "string" ? value.turnId : undefined,
        question: typeof value.question === "string" ? value.question : undefined,
        answer: value.answer,
        savedAt: typeof value.savedAt === "string" ? value.savedAt : new Date(0).toISOString(),
      }];
    });
  },
  setSavedAnswers(items: SavedAnswerRecord[]): void {
    write(SAVED_ANSWERS_KEY, items);
  },
  notifications(): LocalNotification[] {
    return readArray(NOTIFICATIONS_KEY).flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const value = item as Partial<LocalNotification>;
      if (typeof value.id !== "string" || typeof value.title !== "string" || typeof value.body !== "string") return [];
      return [{
        id: value.id,
        title: value.title,
        body: value.body,
        createdAt: typeof value.createdAt === "string" ? value.createdAt : new Date(0).toISOString(),
        read: Boolean(value.read),
        href: typeof value.href === "string" ? value.href : undefined,
      }];
    });
  },
  setNotifications(items: LocalNotification[]): void {
    write(NOTIFICATIONS_KEY, items);
  },
};
