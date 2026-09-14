"use client";

import { useEffect, type MouseEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, Search, Shield, Users } from "lucide-react";

import { useCurrentUser } from "@/hooks/useCurrentUser";

/**
 * Compute the post-login landing destination from the JWT `role` claim.
 * Kept in sync with backend RBAC:
 *   ADMIN → /admin
 *   USER  → /student
 */
function dashboardForRole(rawRole: string | null): string {
  if ((rawRole ?? "").toUpperCase() === "ADMIN") return "/admin";
  return "/student";
}

export default function LandingPage() {
  const router = useRouter();
  const currentUser = useCurrentUser();

  // Once we know the user is logged in, send them straight to the role-
  // appropriate dashboard. Otherwise the landing page below is a static
  // marketing splash — there is no "logged-in home" experience here, and
  // letting an authenticated user linger on / feels like a redirect loop.
  useEffect(() => {
    if (!currentUser.isLoaded) return;
    if (!currentUser.isAuthenticated) return;
    router.replace(dashboardForRole(currentUser.rawRole));
  }, [currentUser.isLoaded, currentUser.isAuthenticated, currentUser.rawRole, router]);

  const authed = currentUser.isLoaded && currentUser.isAuthenticated;
  const primaryHref = authed ? dashboardForRole(currentUser.rawRole) : "/login";
  const primaryLabel = authed ? "Vào hệ thống" : "Đăng nhập";

  // Allow middle-click / cmd-click to open the link in a new tab instead
  // of intercepting with router.push.
  function handlePrimaryClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
      return;
    }
    event.preventDefault();
    router.push(primaryHref);
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#fff1f2] to-white">
      {/* Header */}
      <header className="border-b border-[#f7d0d2] bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#b5121b] flex items-center justify-center">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-slate-900">PolicyMeta AI</span>
          </div>
          <Link
            href={primaryHref}
            onClick={handlePrimaryClick}
            className="px-4 py-2 bg-[#b5121b] text-white rounded-lg font-medium hover:bg-[#930f16] transition-colors"
          >
            {primaryLabel}
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <section className="max-w-6xl mx-auto px-4 py-20 text-center">
        <h1 className="text-4xl md:text-5xl font-bold text-slate-900 mb-6">
          Quản lý văn bản quy phạm
          <br />
          <span className="text-[#b5121b]">pháp luật thông minh</span>
        </h1>
        <p className="text-lg text-slate-600 max-w-2xl mx-auto mb-10">
          Hệ thống tìm kiếm và quản lý văn bản pháp luật với AI. Tìm kiếm nhanh chóng,
          chính xác và trích dẫn nguồn rõ ràng.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href={primaryHref}
            onClick={handlePrimaryClick}
            className="px-8 py-3 bg-[#b5121b] text-white rounded-xl font-medium text-lg hover:bg-[#930f16] transition-colors shadow-lg shadow-[#fcd5d6]"
          >
            {primaryLabel}
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-4 py-16">
        <h2 className="text-2xl font-bold text-slate-900 text-center mb-12">Tính năng nổi bật</h2>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
            <div className="w-12 h-12 rounded-xl bg-[#fff1f2] flex items-center justify-center mb-4">
              <Search className="w-6 h-6 text-[#b5121b]" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">Tìm kiếm thông minh</h3>
            <p className="text-slate-600">
              Tìm kiếm văn bản với AI, hiểu ngữ cảnh và trả về kết quả chính xác kèm trích dẫn.
            </p>
          </div>
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
            <div className="w-12 h-12 rounded-xl bg-[#ecfdf3] flex items-center justify-center mb-4">
              <Shield className="w-6 h-6 text-[#087443]" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">Phân quyền chặt chẽ</h3>
            <p className="text-slate-600">
              Kiểm soát truy cập theo đơn vị, đảm bảo an toàn thông tin và tuân thủ quy định.
            </p>
          </div>
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
            <div className="w-12 h-12 rounded-xl bg-[#faf5ff] flex items-center justify-center mb-4">
              <Users className="w-6 h-6 text-[#7c3aed]" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">Quản lý tập trung</h3>
            <p className="text-slate-600">
              Quản lý văn bản, phiên bản và quy trình phê duyệt tại một nơi duy nhất.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 mt-16">
        <div className="max-w-6xl mx-auto px-4 py-8 text-center text-slate-500">
          <p>PolicyMeta AI - Hệ thống quản lý văn bản quy phạm pháp luật</p>
          <p className="mt-2 text-sm">Liên hệ quản trị viên để được cấp tài khoản</p>
        </div>
      </footer>
    </div>
  );
}
