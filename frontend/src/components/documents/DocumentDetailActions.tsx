"use client";

import { useState, useEffect } from "react";

import { savedDocumentService } from "@/services/savedDocumentService";
import { ApiClientError } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";

import styles from "./DocumentDetailActions.module.css";

export type DocumentDetailActionsProps = {
  documentId: string;
  documentTitle: string;
};

type ActionFeedback = "saved" | "unsaved" | "copied" | "error" | null;

export function DocumentDetailActions({
  documentId,
  documentTitle,
}: DocumentDetailActionsProps) {
  const currentUser = useCurrentUser();
  const [feedback, setFeedback] = useState<ActionFeedback>(null);
  const [isSaved, setIsSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const isAuthed = currentUser.isAuthenticated;

  // Load current saved state (best effort — server doesn't expose a single-doc
  // lookup; we use the list and check membership).
  useEffect(() => {
    let cancelled = false;
    if (!isAuthed) {
      setIsSaved(false);
      return;
    }
    (async () => {
      try {
        const res = await savedDocumentService.list(1, 100);
        if (cancelled) return;
        setIsSaved(res.items.some((s) => s.document_id === documentId));
      } catch {
        // Silent: showing default "unsaved" state is fine if list fails.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, isAuthed]);

  async function toggleSave() {
    if (!isAuthed) {
      setFeedback("error");
      return;
    }
    setBusy(true);
    try {
      if (isSaved) {
        await savedDocumentService.unsave(documentId);
        setIsSaved(false);
        setFeedback("unsaved");
      } else {
        await savedDocumentService.save(documentId);
        setIsSaved(true);
        setFeedback("saved");
      }
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 409) {
        setIsSaved(true);
        setFeedback("saved");
      } else {
        setFeedback("error");
      }
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setFeedback("copied");
    } catch {
      setFeedback("error");
    }
  }

  const feedbackText =
    feedback === "saved"
      ? "Đã lưu văn bản."
      : feedback === "unsaved"
        ? "Đã bỏ lưu văn bản."
        : feedback === "copied"
          ? "Đã sao chép liên kết."
          : "Không thể thực hiện. Vui lòng thử lại.";

  return (
    <div className={styles.wrapper}>
      <div
        className={styles.actions}
        role="group"
        aria-label={`Thao tác với ${documentTitle}`}
      >
        <button type="button" onClick={toggleSave} disabled={busy}>
          {busy ? "..." : isSaved ? "Bỏ lưu" : "Lưu văn bản"}
        </button>
        <button type="button" onClick={copyLink}>
          Sao chép liên kết
        </button>
      </div>
      {feedback && (
        <p className={feedback === "error" ? styles.error : ""} aria-live="polite">
          {feedbackText}
        </p>
      )}
    </div>
  );
}
