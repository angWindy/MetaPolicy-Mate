"use client";

import { useState } from "react";

import styles from "./AIAnswerActions.module.css";

export type AIAnswerActionsProps = {
  answerText: string;
  question?: string;
};

type Feedback = "saved" | "copied" | "shared" | "reported" | "error" | null;

function appendLocalRecord(key: string, record: object) {
  const current = localStorage.getItem(key);
  const records = current ? JSON.parse(current) : [];
  const safeRecords = Array.isArray(records) ? records : [];
  localStorage.setItem(key, JSON.stringify([...safeRecords, record]));
}

export function AIAnswerActions({
  answerText,
  question,
}: AIAnswerActionsProps) {
  const [feedback, setFeedback] = useState<Feedback>(null);

  function saveAnswer() {
    try {
      appendLocalRecord("policymate.savedAnswers", {
        question,
        answer: answerText,
        savedAt: new Date().toISOString(),
      });
      setFeedback("saved");
    } catch {
      setFeedback("error");
    }
  }

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(answerText);
      setFeedback("copied");
    } catch {
      setFeedback("error");
    }
  }

  async function shareAnswer() {
    try {
      if (navigator.share) {
        await navigator.share({
          title: "Câu trả lời từ PolicyMate AI",
          text: answerText,
          url: window.location.href,
        });
        setFeedback("shared");
        return;
      }

      await navigator.clipboard.writeText(
        `${answerText}\n\n${window.location.href}`,
      );
      setFeedback("copied");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setFeedback("error");
    }
  }

  function reportAnswer() {
    try {
      appendLocalRecord("policymate.pendingReports", {
        question,
        answer: answerText,
        reportedAt: new Date().toISOString(),
        syncStatus: "local-only",
      });
      setFeedback("reported");
    } catch {
      setFeedback("error");
    }
  }

  const feedbackText = {
    saved: "Đã lưu trên thiết bị này.",
    copied: "Đã sao chép vào bộ nhớ tạm.",
    shared: "Đã mở trình chia sẻ.",
    reported: "Đã ghi nhận cục bộ, chưa gửi lên hệ thống.",
    error: "Không thể thực hiện. Vui lòng thử lại.",
  }[feedback ?? "saved"];

  return (
    <div className={styles.wrapper}>
      <div
        className={styles.actions}
        role="group"
        aria-label="Thao tác với câu trả lời"
      >
        <button type="button" onClick={saveAnswer}>
          Lưu câu trả lời
        </button>
        <button type="button" onClick={copyAnswer}>
          Sao chép
        </button>
        <button type="button" onClick={shareAnswer}>
          Chia sẻ
        </button>
        <button type="button" onClick={reportAnswer}>
          Báo cáo
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
