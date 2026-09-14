import type { AIAnswerBlock } from "../../types/aiAnswer";
import { AIAnswerActions } from "./AIAnswerActions";
import styles from "./AIAnswerCard.module.css";

export type AIAnswerCardProps = {
  blocks: AIAnswerBlock[];
  question?: string;
  title?: string;
  confidence?: number;
  note?: string;
  emptyMessage?: string;
};

export function AIAnswerCard({
  blocks,
  question,
  title = "Câu trả lời từ PolicyMate AI",
  confidence,
  note,
  emptyMessage = "Chưa có câu trả lời.",
}: AIAnswerCardProps) {
  const answerText = blocks
    .map((block) =>
      block.type === "list" ? block.items.join("\n") : block.text,
    )
    .join("\n\n");
  const confidencePercent =
    confidence === undefined
      ? null
      : Math.round(Math.min(1, Math.max(0, confidence)) * 100);
  const confidenceLevel =
    confidencePercent === null
      ? null
      : confidencePercent >= 85
        ? "high"
        : confidencePercent >= 65
          ? "medium"
          : "low";
  const confidenceLabel =
    confidenceLevel === "high"
      ? "Tin cậy cao"
      : confidenceLevel === "medium"
        ? "Tin cậy khá"
        : "Cần kiểm tra thêm";

  return (
    <section className={styles.card} aria-labelledby="ai-answer-title">
      <div className={styles.heading}>
        <span aria-hidden="true">✦</span>
        <h2 id="ai-answer-title">{title}</h2>
        {confidencePercent !== null && confidenceLevel && (
          <span
            className={`${styles.confidence} ${styles[confidenceLevel]}`}
            aria-label={`Độ tin cậy ${confidencePercent} phần trăm`}
          >
            {confidenceLabel} · {confidencePercent}%
          </span>
        )}
      </div>

      {question && <p className={styles.question}>{question}</p>}

      {blocks.length > 0 ? (
        <div className={styles.content}>
          {blocks.map((block) => {
            if (block.type === "heading") {
              return <h3 key={block.id}>{block.text}</h3>;
            }

            if (block.type === "list") {
              return (
                <ul key={block.id}>
                  {block.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              );
            }

            return <p key={block.id}>{block.text}</p>;
          })}
          {note && <small>{note}</small>}
          <AIAnswerActions answerText={answerText} question={question} />
        </div>
      ) : (
        <p className={styles.empty}>{emptyMessage}</p>
      )}
    </section>
  );
}
