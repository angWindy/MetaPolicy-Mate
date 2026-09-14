"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AuthenticatedLayout, AuthGate, AuthLoading } from "@/components/layout";

type HistoryEntry = {
  id: string;
  question: string;
  answer: string;
  savedAt: string;
};

const LOCAL_KEY = "policymate.savedAnswers";

function readEntries(): HistoryEntry[] {
  try {
    const raw = window.localStorage.getItem(LOCAL_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((e): e is HistoryEntry =>
      Boolean(e && typeof e === "object" && typeof e.answer === "string"),
    );
  } catch {
    return [];
  }
}

function findEntry(id: string): HistoryEntry | null {
  const all = readEntries();
  const byId = all.find((e) => e.id === id);
  if (byId) return byId;
  if (id.startsWith("local-")) {
    const idx = parseInt(id.replace("local-", ""), 10);
    if (Number.isFinite(idx) && idx >= 0 && idx < all.length) {
      return all[idx] ?? null;
    }
  }
  return null;
}

export default function HistoryDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id ?? "");
  // Hydrate lazily on first render so we don't trigger cascading renders
  // via useEffect + setState.
  const [entry] = useState<HistoryEntry | null>(() => findEntry(id));
  const [loading] = useState<boolean>(false);

  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải chi tiết câu trả lời…" />}
    >
      <AuthenticatedLayout title="Chi tiết câu trả lời" notificationCount={0}>
      <section className="mx-auto max-w-3xl px-4 py-8">
        <Link
          href="/history"
          className="mb-4 inline-flex items-center text-sm text-[#b5121b] hover:underline"
        >
          ← Quay lại lịch sử
        </Link>

        {loading && <p className="text-sm text-slate-500">Đang tải…</p>}

        {!loading && !entry && (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
            <h2 className="text-base font-semibold text-slate-700">
              Không tìm thấy câu trả lời
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Có thể câu trả lời này đã bị xóa khỏi bộ nhớ cục bộ của bạn.
            </p>
            <Link
              href="/history"
              className="mt-4 inline-flex items-center justify-center rounded-lg bg-[#b5121b] px-4 py-2 text-sm font-medium text-white hover:bg-[#930f16]"
            >
              Về lịch sử
            </Link>
          </div>
        )}

        {!loading && entry && (
          <article className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <header>
              <p className="text-xs uppercase tracking-wider text-slate-500">
                Câu hỏi
              </p>
              <h1 className="mt-1 text-lg font-semibold text-slate-900">
                {entry.question || "(không có câu hỏi)"}
              </h1>
              <p className="mt-2 text-xs text-slate-400">
                Lưu lúc{" "}
                {new Date(entry.savedAt).toLocaleString("vi-VN")}
              </p>
            </header>

            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">
                Câu trả lời
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">
                {entry.answer}
              </p>
            </div>
          </article>
        )}
      </section>
    </AuthenticatedLayout>
    </AuthGate>
  );
}