"use client";

import { useState } from "react";

import { askService } from "../../services/askService";
import type { AskQuestionResponse } from "../../types/api";
import type { AIAnswerBlock } from "../../types/aiAnswer";
import type { ReferenceSource } from "../../types/ask";
import { AskAiComposer } from "../home";
import { AIAnswerCard } from "./AIAnswerCard";
import { SourceCitationCard } from "./SourceCitationCard";
import styles from "./AskPageContent.module.css";

export type AskPageContentProps = {
  documentId?: string;
  initialQuestion?: string;
};

type CitationSource = ReferenceSource;

type PageState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; question: string; answer: AIAnswerBlock[]; sources: CitationSource[]; confidence: number; warnings: string[] }
  | { kind: "error"; question: string; message: string };

function responseToBlocks(response: string): AIAnswerBlock[] {
  const paragraphs = response
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (paragraphs.length === 0) return [];
  return paragraphs.map((text, index) => ({
    id: `block-${index}`,
    type: "paragraph" as const,
    text,
  }));
}

function confidenceToNumber(value: string | undefined | null): number {
  if (!value) return 0;
  const v = value.toLowerCase();
  if (v === "high") return 0.9;
  if (v === "medium") return 0.7;
  if (v === "low") return 0.4;
  const numeric = Number(v);
  return Number.isFinite(numeric) ? numeric : 0;
}

function citationToSource(citation: NonNullable<AskQuestionResponse["citations"]>[number], idx: number): CitationSource {
  const article = citation.article ?? citation.section ?? citation.clause ?? citation.point ?? "—";
  return {
    id: citation.chunk_id ?? `citation-${idx}`,
    title: citation.title ?? "Văn bản",
    documentType: "Quy chế / Quy định",
    // 2026-09-06 UX update: show ONLY article/clause + document number,
    // no inline numeric index chip.
    reference: article,
    page: citation.page ?? 0,
    version: "1",
    effectiveDate: "",
    effectiveDateLabel: "—",
    validityStatus: "current",
    validityLabel: "Đang hiệu lực",
    excerpt: citation.excerpt ?? "",
    // Prefer the canonical document-detail page so the chip deep-links
    // to the specific document instead of the library index.
    href:
      citation.document_id && citation.document_id.trim()
        ? `/documents/${citation.document_id}`
        : (citation.source_url ?? "/documents"),
  };
}

export function AskPageContent({ documentId, initialQuestion = "" }: AskPageContentProps) {
  const [question, setQuestion] = useState(initialQuestion);
  const [state, setState] = useState<PageState>({ kind: "idle" });

  async function handleSubmit(submitted: string) {
    if (!submitted.trim()) return;
    setState({ kind: "loading" });
    try {
      const res: AskQuestionResponse = await askService.ask({ message: submitted });
      const blocks = responseToBlocks(res.answer ?? "");
      const sources: CitationSource[] = (res.citations ?? []).map(citationToSource);
      setState({
        kind: "success",
        question: submitted,
        answer: blocks,
        sources,
        confidence: confidenceToNumber(res.confidence),
        warnings: res.warnings ?? [],
      });
    } catch (err) {
      setState({
        kind: "error",
        question: submitted,
        message: (err as Error).message ?? "Không nhận được phản hồi từ máy chủ",
      });
    }
  }

  return (
    <div className={styles.page}>
      <section className={styles.introduction}>
        <h2>Hỏi PolicyMate AI</h2>
        <p>
          Đặt câu hỏi về quy chế và nhận câu trả lời có nguồn tham khảo từ văn
          bản của nhà trường.
        </p>
        {documentId && (
          <p className={styles.documentContext}>
            Đang hỏi theo văn bản: <strong>{documentId}</strong>
          </p>
        )}
      </section>

      <AskAiComposer
        value={question}
        onValueChange={setQuestion}
        onSubmit={(q) => {
          setQuestion(q);
          void handleSubmit(q);
        }}
        placeholder="Nhập câu hỏi về tín chỉ, học phí, thi cử, học bổng hoặc tốt nghiệp..."
      />

      <div className={styles.resultGrid} aria-live="polite">
        {state.kind === "loading" && (
          <p className={styles.empty}>Đang truy xuất câu trả lời...</p>
        )}
        {state.kind === "error" && (
          <p className={styles.empty} role="alert">Lỗi: {state.message}</p>
        )}
        {state.kind === "success" && (
          <AIAnswerCard
            question={state.question}
            blocks={state.answer}
            confidence={state.confidence}
            note={
              state.warnings.length > 0
                ? `Cảnh báo: ${state.warnings.join("; ")}`
                : undefined
            }
            emptyMessage="Câu trả lời rỗng."
          />
        )}
        {state.kind === "idle" && (
          <AIAnswerCard
            blocks={[]}
            emptyMessage="Nhập câu hỏi phía trên để xem câu trả lời và nguồn tham khảo."
          />
        )}

        <aside className={styles.sourcesPanel} aria-labelledby="sources-title">
          <h2 id="sources-title">Nguồn tham khảo</h2>
          {state.kind === "success" ? (
            state.sources.length === 0 ? (
              <p className={styles.emptyState}>Không có nguồn tham khảo.</p>
            ) : (
              <ul>
                {state.sources.map((source) => (
                  <li key={source.id}>
                    <SourceCitationCard source={source} />
                  </li>
                ))}
              </ul>
            )
          ) : (
            <p className={styles.emptyState}>Nguồn sẽ xuất hiện cùng câu trả lời.</p>
          )}
        </aside>
      </div>
    </div>
  );
}