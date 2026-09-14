"use client";

import { ArrowRight, FileText } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { apiRequest } from "@/lib/api";

const STATUS_LIBRARY = {
  DANG_HIEU_LUC: { status: "active", statusLabel: "Đang hiệu lực" },
  CHO_XU_LY_NOI_DUNG: { status: "updated", statusLabel: "Mới cập nhật" },
  HET_HIEU_LUC: { status: "expired", statusLabel: "Hết hiệu lực" },
  BI_THAY_THE: { status: "expired", statusLabel: "Bị thay thế" },
  BAN_NHAP: { status: "active", statusLabel: "Bản nháp" },
} as const;

type ApiDocument = {
  id: string;
  document_number: string;
  title: string;
  issued_by?: string;
  issued_date?: string;
  effective_date?: string | null;
  legal_status?: string;
  updated_at?: string | null;
  created_at?: string;
};

type RecentDoc = {
  id: string;
  title: string;
  documentNumber: string;
  effectiveLabel: string;
  status: keyof typeof STATUS_LIBRARY;
  href: string;
};

// 2026-09-06: removed the "Chủ đề phổ biến" (popular topics) section
// from the student home page. The topic taxonomy (academic, tuition,
// exams, ...) is no longer surfaced here — users discover categories
// through the floating chatbot or the document library search.

const QUICK_TOPICS_FOR_AI = [
  { id: "credit-graduation", label: "Tín chỉ tốt nghiệp" },
  { id: "tuition", label: "Học phí" },
  { id: "leave", label: "Bảo lưu" },
  { id: "scholarship", label: "Học bổng" },
];

function mapRecentDoc(item: ApiDocument): RecentDoc {
  const status =
    (item.legal_status as keyof typeof STATUS_LIBRARY) ?? "DANG_HIEU_LUC";
  return {
    id: item.id,
    title: item.title,
    documentNumber: item.document_number,
    effectiveLabel: item.effective_date ?? item.issued_date ?? "—",
    status,
    href: `/documents/${item.id}`,
  };
}

const documentStatusStyles: Record<RecentDoc["status"], string> = {
  DANG_HIEU_LUC: "bg-[#F0FDF4] text-[#166534] ring-[#BBF7D0]",
  CHO_XU_LY_NOI_DUNG: "bg-[#FEFCE8] text-[#A16207] ring-[#FDE68A]",
  HET_HIEU_LUC: "bg-[#FEF2F2] text-[#B91C1C] ring-[#FECACA]",
  BI_THAY_THE: "bg-[#FEF2F2] text-[#B91C1C] ring-[#FECACA]",
  BAN_NHAP: "bg-[#FEFCE8] text-[#A16207] ring-[#FDE68A]",
};

export type StudentHomePageProps = {
  userName?: string;
};

/**
 * Content-only render of the student home dashboard. The surrounding
 * `AppLayout` (rendered by `AuthenticatedLayout` in `app/student/page.tsx`)
 * owns the top-bar navigation so this component just paints the page
 * body and lets the standard header carry the user's name / search /
 * account menu.
 */
export function StudentHomePage({ userName }: StudentHomePageProps = {}) {
  const [recentDocs, setRecentDocs] = useState<RecentDoc[]>([]);
  const [recentDocsLoading, setRecentDocsLoading] = useState(true);
  const [recentDocsError, setRecentDocsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiRequest<{
          items?: ApiDocument[];
          total?: number;
        }>("/api/v1/regulatory-documents?page=1&page_size=3");
        if (cancelled) return;
        setRecentDocs((res.items ?? []).map(mapRecentDoc));
        setRecentDocsError(null);
      } catch (err) {
        if (cancelled) return;
        setRecentDocsError(
          err instanceof Error
            ? `Không tải được văn bản mới nhất: ${err.message}`
            : "Không tải được văn bản mới nhất.",
        );
      } finally {
        if (!cancelled) setRecentDocsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const greetingName = userName ?? "bạn";

  return (
    <div className="mx-auto w-full max-w-[1256px] px-4 py-6 sm:px-6 lg:px-7 lg:py-7">
      <section aria-labelledby="student-welcome-title" className="pb-5">
        <h2 id="student-welcome-title" className="text-[28px] font-bold leading-tight text-[#0F172A] sm:text-[32px]">
          Chào bạn, {greetingName}!
        </h2>
        <p className="mt-2 text-base font-medium text-[#334155]">Hôm nay bạn muốn tra cứu quy định nào?</p>
        <p className="mt-1 text-sm leading-6 text-[#64748B]">Tìm câu trả lời từ các văn bản chính thức của nhà trường.</p>
      </section>

      <section
        aria-label="Trợ lý PolicyMate"
        className="mb-5 flex flex-col gap-3 rounded-[14px] border border-[#E2E8F0] bg-white p-4 shadow-[var(--shadow-card)] sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="grid h-10 w-10 place-items-center rounded-[10px] bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
            </svg>
          </span>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-[#0F172A]">
              Trợ lý PolicyMate AI luôn sẵn sàng ở góc dưới phải
            </h3>
            <p className="text-[13px] leading-5 text-[#64748B]">
              Bấm vào biểu tượng chat để đặt câu hỏi về quy chế. Câu trả lời
              sẽ kèm nguồn văn bản để bạn đối chiếu.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 sm:flex-nowrap">
          {QUICK_TOPICS_FOR_AI.map((topic) => (
            <span
              key={topic.id}
              className="inline-flex min-h-9 items-center rounded-full border border-[#E2E8F0] bg-[#F8FAFC] px-3 text-[12px] font-medium text-[#334155]"
            >
              {topic.label}
            </span>
          ))}
        </div>
      </section>

      <HomeSection title="Văn bản mới cập nhật">
        {recentDocsLoading ? (
          <p className="rounded-[14px] border border-[#E2E8F0] bg-white p-4 text-sm text-[#64748B]">
            Đang tải văn bản mới nhất…
          </p>
        ) : recentDocsError ? (
          <p className="rounded-[14px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {recentDocsError}
          </p>
        ) : recentDocs.length === 0 ? (
          <p className="rounded-[14px] border border-dashed border-[#E2E8F0] bg-white p-4 text-sm text-[#64748B]">
            Chưa có văn bản nào được ban hành. Tải lên từ trang quản trị
            để bắt đầu.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-3">
            {recentDocs.map((document) => <RecentDocumentCardItem key={document.id} document={document} />)}
          </div>
        )}
      </HomeSection>

      <HomeSection
        title="Tra cứu gần đây"
        action={
          <Link
            href="/history"
            className="text-[13px] font-semibold text-[var(--color-primary)] underline-offset-4 hover:underline"
          >
            Xem tất cả lịch sử
          </Link>
        }
      >
        <div className="rounded-[14px] border border-dashed border-[#E2E8F0] bg-white p-4 text-sm text-[#64748B]">
          Tính năng tra cứu gần đây sẽ được đồng bộ với backend trong
          phiên cập nhật tiếp theo. Mọi câu hỏi gửi qua PolicyMate AI sẽ
          được lưu lại tự động khi endpoint lịch sử hoàn tất.
        </div>
      </HomeSection>
    </div>
  );
}

function HomeSection({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  const headingId = `student-${title.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replaceAll(" ", "-").toLowerCase()}`;
  return (
    <section className="mt-8" aria-labelledby={headingId}>
      <div className="mb-3.5 flex items-center justify-between gap-4">
        <h2 id={headingId} className="text-lg font-semibold text-[#0F172A]">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function RecentDocumentCardItem({ document }: { document: RecentDoc }) {
  const statusLabel = STATUS_LIBRARY[document.status] ?? STATUS_LIBRARY.DANG_HIEU_LUC;
  return (
    <article className="flex min-h-[168px] flex-col rounded-[14px] border border-[#E2E8F0] bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-[var(--color-primary-soft)] text-[var(--color-primary)]" aria-hidden="true"><FileText size={19} strokeWidth={1.8} /></span>
        <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ring-1 ring-inset ${documentStatusStyles[document.status]}`}>{statusLabel.statusLabel}</span>
      </div>
      <h3 className="mt-3 text-sm font-semibold leading-5 text-[#0F172A]">{document.title}</h3>
      <p className="mt-1 text-xs leading-5 text-[#64748B]">{document.documentNumber}</p>
      <div className="mt-auto flex items-end justify-between gap-3 pt-3">
        <span className="text-xs text-[#64748B]">Hiệu lực {document.effectiveLabel}</span>
        <Link href={document.href} className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-[8px] px-2 text-xs font-semibold text-[var(--color-primary)] transition-colors hover:bg-[var(--color-primary-soft)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]">Xem văn bản <ArrowRight aria-hidden="true" size={14} strokeWidth={1.8} /></Link>
      </div>
    </article>
  );
}
