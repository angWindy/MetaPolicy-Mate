"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { suggestedQuestions } from "@/data/suggestedQuestions";
import { policyTopics } from "@/data/policyTopics";
import { MotionReveal } from "@/components/motion";

import { AskAiComposer } from "./AskAiComposer";
import { EvidencePreview } from "./EvidencePreview";
import { PersonalSpace } from "./PersonalSpace";
import { PolicyMateStory } from "./PolicyMateStory";
import { RecentDocumentsSection } from "./RecentDocumentsSection";
import { SuggestedQuestions } from "./SuggestedQuestions";
import { TopicsSection } from "./TopicsSection";
import { WelcomeSection } from "./WelcomeSection";
import styles from "./HomeDashboard.module.css";

type ApiDocument = {
  id: string;
  document_number: string;
  title: string;
  issued_by?: string;
  effective_date?: string | null;
  legal_status?: string;
};

type RecentDocumentItem = {
  id: string;
  title: string;
  type?: string;
  documentNumber: string;
  version: string;
  status: "active" | "updated" | "expired";
  statusLabel: string;
  updatedAt: string;
  updatedLabel: string;
  href: string;
};

const LEGAL_STATUSES: Record<
  string,
  { status: "active" | "updated" | "expired"; statusLabel: string }
> = {
  DANG_HIEU_LUC: { status: "active", statusLabel: "Đang hiệu lực" },
  CHO_XU_LY_NOI_DUNG: { status: "updated", statusLabel: "Mới cập nhật" },
  HET_HIEU_LUC: { status: "expired", statusLabel: "Hết hiệu lực" },
  BI_THAY_THE: { status: "expired", statusLabel: "Bị thay thế" },
  BAN_NHAP: { status: "updated", statusLabel: "Bản nháp" },
};

function mapRecentDocument(item: ApiDocument): RecentDocumentItem {
  const mapping =
    LEGAL_STATUSES[item.legal_status ?? ""] ??
    LEGAL_STATUSES.DANG_HIEU_LUC;
  return {
    id: item.id,
    title: item.title,
    type: item.issued_by ?? undefined,
    documentNumber: item.document_number,
    version: "1",
    status: mapping.status,
    statusLabel: mapping.statusLabel,
    updatedAt: item.effective_date ?? "",
    updatedLabel: item.effective_date ?? "—",
    href: `/documents/${item.id}`,
  };
}

export type HomeDashboardProps = { userName?: string };

export function HomeDashboard({ userName: propUserName }: HomeDashboardProps = {}) {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const [question, setQuestion] = useState("");
  const [recentDocs, setRecentDocs] = useState<RecentDocumentItem[]>([]);
  const [documentState, setDocumentState] = useState<
    "loading" | "success" | "error"
  >("loading");
  const [documentError, setDocumentError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const res = await apiRequest<{ items?: ApiDocument[] }>(
          "/api/v1/regulatory-documents?page=1&page_size=4",
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setRecentDocs((res.items ?? []).map(mapRecentDocument));
        setDocumentState("success");
        setDocumentError(null);
      } catch (err) {
        if (controller.signal.aborted) return;
        if ((err as Error).name === "AbortError") return;
        setDocumentError(
          err instanceof Error
            ? `Không tải được danh sách văn bản: ${err.message}`
            : "Không tải được danh sách văn bản.",
        );
        setDocumentState("error");
      }
    })();
    return () => controller.abort();
  }, []);

  const greetingName =
    propUserName ??
    (currentUser.isAuthenticated
      ? currentUser.name?.split(/\s+/).slice(-1)[0] || "bạn"
      : "bạn");

  function ask(value: string) {
    if (!value.trim()) return;
    router.push(`/ask?q=${encodeURIComponent(value)}`);
  }

  const homeSuggested = (suggestedQuestions ?? []).slice(0, 3);

  return (
    <div className={styles.dashboard}>
      <MotionReveal distance={14}>
        <section className={styles.hero} aria-label="Tra cứu quy chế">
          <div className={styles.heroMain}>
            <WelcomeSection userName={greetingName} />
            <AskAiComposer
              value={question}
              onValueChange={setQuestion}
              onSubmit={(value) => ask(value)}
            />
            <SuggestedQuestions
              questions={homeSuggested}
              onSelect={(suggestion) => {
                setQuestion(suggestion.text);
                ask(suggestion.text);
              }}
            />
          </div>
          <EvidencePreview />
        </section>
      </MotionReveal>

      <MotionReveal delay={0.04}>
        <TopicsSection topics={policyTopics} />
      </MotionReveal>

      <MotionReveal>
        <section
          className={styles.lowerGrid}
          aria-label="Cập nhật và không gian cá nhân"
        >
          <div className={styles.documentsPanel}>
            {documentState === "loading" && (
              <section
                className={styles.documentState}
                role="status"
                aria-live="polite"
                aria-busy="true"
              >
                <h2>Văn bản mới cập nhật</h2>
                <span className="sr-only">
                  Đang tải văn bản mới cập nhật
                </span>
                <div aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </div>
              </section>
            )}
            {documentState === "error" && (
              <section className={styles.documentError} role="alert">
                <strong>Chưa tải được văn bản mới</strong>
                <span>{documentError ?? "Kiểm tra kết nối backend rồi tải lại trang."}</span>
              </section>
            )}
            {documentState === "success" && recentDocs.length > 0 && (
              <RecentDocumentsSection documents={recentDocs} />
            )}
            {documentState === "success" && recentDocs.length === 0 && (
              <section className={styles.documentError}>
                <strong>Chưa có văn bản nào</strong>
                <span>
                  Danh sách sẽ xuất hiện khi kho tài liệu có dữ liệu.
                </span>
              </section>
            )}
          </div>
          <PersonalSpace />
        </section>
      </MotionReveal>

      <PolicyMateStory />
    </div>
  );
}
