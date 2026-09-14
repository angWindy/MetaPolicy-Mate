"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * The legacy /chat page is deprecated. New code links to /student
 * (which now exposes the Ask AI surface through the floating chat
 * widget anchored bottom-right).
 *
 * This redirect keeps existing bookmarks working.
 */
export default function ChatPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/student");
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm text-center">
        <p className="text-sm text-slate-500">Đang chuyển hướng…</p>
      </div>
    </div>
  );
}
