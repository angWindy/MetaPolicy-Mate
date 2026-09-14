"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { AuthGate, AuthLoading } from "@/components/layout";

/**
 * `/student/ask` is gone — the dedicated student ask page has been
 * folded into the floating chat widget anchored to the bottom-right of
 * every user page. Hitting the old URL bounces back to `/student` so
 * existing bookmarks land somewhere sensible instead of 404-ing.
 */
export default function StudentAskRoutePage() {
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
