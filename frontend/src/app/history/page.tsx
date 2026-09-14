"use client";

import { useState } from "react";
import Link from "next/link";

import { AuthenticatedLayout, AuthGate, AuthLoading } from "@/components/layout";

type HistoryEntry = {
  id: string;
  question: string;
  answer: string;
  savedAt: string;
};

const LOCAL_KEY = "policymate.savedAnswers";

function loadEntries(): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LOCAL_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((e): e is HistoryEntry =>
        Boolean(e && typeof e === "object" && typeof e.answer === "string"),
      )
      .map((e, idx) => ({
        id: typeof e.id === "string" ? e.id : `local-${idx}`,
        question:
          typeof e.question === "string"
            ? e.question
            : "(không có câu hỏi)",
        answer: e.answer,
        savedAt:
          typeof e.savedAt === "string"
            ? e.savedAt
            : new Date().toISOString(),
      }))
      .sort((a, b) => b.savedAt.localeCompare(a.savedAt));
  } catch {
    return [];
  }
}

export default function HistoryPage() {
  // ``loadEntries()`` is synchronous, so we hydrate state lazily during the
  // first render instead of from a useEffect — this avoids the cascading
  // render that ``react-hooks/set-state-in-effect`` complains about.
  // Server-rendered HTML always sees the empty initial state, and the
  // client picks up the localStorage value on first render.
  const [items] = useState<HistoryEntry[]>(() => loadEntries());
  const [loading] = useState<boolean>(false);

  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải lịch sử…" />}
    >
      <AuthenticatedLayout title="Lịch sử tra cứu" notificationCount={0}>
      <section className="mx-auto max-w-3xl px-4 py-8">
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-[var(--color-text)]">
            Lịch sử tra cứu
          </h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Các câu trả lời bạn đã lưu trên thiết bị này. Khi backend hỗ trợ
            lịch sử trên server, danh sách này sẽ tự động đồng bộ.
          </p>
        </header>

        {loading && <p className="text-sm text-slate-500">Đang tải…</p>}

        {!loading && items.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
            <h2 className="text-base font-semibold text-slate-700">
              Chưa có câu trả lời đã lưu
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Trong ô trả lời, nhấn biểu tượng &ldquo;Lưu&rdquo; để thêm vào
              lịch sử này. Hoặc mở trợ lý ở góc dưới phải để tra cứu ngay.
            </p>
          </div>
        )}

        {!loading && items.length > 0 && (
          <ul className="space-y-3">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <Link
                  href={`/history/${encodeURIComponent(item.id)}`}
                  className="block"
                >
                  <h3 className="text-sm font-semibold text-slate-900">
                    {item.question}
                  </h3>
                  <p className="mt-2 line-clamp-3 text-sm text-slate-600">
                    {item.answer}
                  </p>
                  <span className="mt-3 block text-xs text-slate-400">
                    Lưu lúc{" "}
                    {new Date(item.savedAt).toLocaleString("vi-VN")}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </AuthenticatedLayout>
    </AuthGate>
  );
}