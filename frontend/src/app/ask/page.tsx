"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { AuthGate, AuthLoading } from "@/components/layout";

/**
 * The standalone "Hỏi AI" page is gone — the Ask AI surface has been
 * folded into the floating chat widget anchored to the bottom-right of
 * every student page. Hitting the old URL (or a stale bookmark) routes
 * the user back to ``/student`` so the dead page never shows up.
 */
export default function AskPage() {
  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang chuyển hướng…" />}
    >
      <RedirectToStudent />
    </AuthGate>
  );
}

function RedirectToStudent() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/student");
  }, [router]);
  return <AuthLoading title="Đang chuyển hướng đến Trang chủ…" />;
}
