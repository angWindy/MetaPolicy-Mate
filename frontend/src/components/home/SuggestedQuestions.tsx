"use client";

import { MessageCircle } from "lucide-react";
import type { SuggestedQuestion } from "../../types/home";
import styles from "./SuggestedQuestions.module.css";

export type SuggestedQuestionsProps = {
  questions: SuggestedQuestion[];
  onSelect?: (question: SuggestedQuestion) => void;
};

export function SuggestedQuestions({
  questions,
  onSelect,
}: SuggestedQuestionsProps) {
  if (questions.length === 0) return null;

  return (
    <section className={styles.section} aria-labelledby="suggested-questions-title">
      <h2 id="suggested-questions-title" className={styles.srOnly}>
        Câu hỏi gợi ý
      </h2>
      <div className={styles.list}>
        {questions.map((question) => (
          <button
            key={question.id}
            type="button"
            className={styles.question}
            onClick={() => onSelect?.(question)}
          >
            <MessageCircle className={styles.sparkle} size={14} aria-hidden="true" />
            <span>{question.text}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
