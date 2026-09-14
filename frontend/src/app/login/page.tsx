"use client";

import {
  ArrowRight,
  Bot,
  CheckCircle2,
  FileSearch,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useCurrentUser } from "../../hooks/useCurrentUser";
import { authService } from "../../services/authService";
import { ApiClientError } from "../../lib/api";

interface LoginError {
  detail?: string;
  message?: string;
}

const QUICK_LOGINS = [
  { label: "Quản trị", email: "admin@p234.demo", password: "P234@123" },
  { label: "HUST", email: "hust@p234.demo", password: "P234@123" },
  { label: "HUCE", email: "huce@p234.demo", password: "P234@123" },
];

/**
 * Decide where to send the user after login.
 *
 * Priority:
 *   1. Explicit `?next=` query param, unless it points back to /login
 *      or the public landing / (those would loop).
 *   2. Role-based default derived from the JWT we just received:
 *        ADMIN → /admin
 *        USER  → /student
 */
function decodeJwtRole(token: string | null | undefined): string | null {
  if (!token) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const decoded = typeof atob === "function" ? atob(padded) : null;
    if (decoded === null) return null;
    const parsed = JSON.parse(decoded);
    if (parsed && typeof parsed === "object") {
      const role = (parsed as Record<string, unknown>).role;
      return typeof role === "string" ? role : null;
    }
  } catch {
    // fall through
  }
  return null;
}

function resolveLanding(nextParam: string | null, accessToken: string | null): string {
  if (nextParam) {
    if (nextParam.startsWith("/") && !nextParam.startsWith("//")) {
      const trimmed = nextParam.split(/[?#]/)[0] ?? "/";
      if (trimmed !== "/login" && trimmed !== "/") {
        return nextParam;
      }
    }
  }
  const role = decodeJwtRole(accessToken);
  if ((role ?? "").toUpperCase() === "ADMIN") return "/admin";
  return "/student";
}

export default function LoginPage() {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-redirect when an already-authenticated viewer hits /login.
  useEffect(() => {
    if (!currentUser.isLoaded) return;
    if (currentUser.isAuthenticated) {
      router.replace("/");
    }
  }, [currentUser.isLoaded, currentUser.isAuthenticated, router]);

  async function doLogin(emailValue: string, passwordValue: string) {
    setSubmitting(true);
    setError(null);
    try {
      const tokens = await authService.login(emailValue, passwordValue);
      const nextParam = new URLSearchParams(window.location.search).get("next");
      const nextTarget = resolveLanding(nextParam, tokens.access_token);
      router.replace(nextTarget);
    } catch (err) {
      const e = err as ApiClientError & { payload?: LoginError };
      const detail = e.payload?.detail ?? e.payload?.message ?? e.message;
      setError(
        e.status === 401 || e.status === 0
          ? "Email hoặc mật khẩu không đúng. Vui lòng thử lại."
          : (detail ?? `Lỗi HTTP ${e.status ?? "?"}`),
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await doLogin(email, password);
  }

  return (
    <main className="relative grid min-h-[100dvh] grid-cols-[minmax(0,1fr)] overflow-hidden bg-[#f5f7fa] lg:grid-cols-[1.05fr_.95fr]">
      <section className="relative hidden overflow-hidden bg-[#86131b] px-12 py-10 text-white lg:flex lg:flex-col lg:justify-between xl:px-20">
        <div className="flex items-center gap-3 text-xl font-bold">
          <span className="grid size-11 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/25">
            <Sparkles size={22} />
          </span>
          PolicyMate AI
        </div>
        <div className="max-w-xl">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold ring-1 ring-white/20">
            <ShieldCheck size={14} /> Nguồn chính thức · Câu trả lời tin cậy
          </span>
          <h1 className="mt-7 text-5xl font-bold leading-[1.08] tracking-[-.05em] xl:text-6xl">
            Hiểu quy chế.
            <br />
            Vững hành trình.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-rose-100">
            Tra cứu quy định học vụ nhanh chóng, rõ nguồn và luôn cập nhật
            trong một không gian dành riêng cho bạn.
          </p>
          <div className="mt-10 grid max-w-lg grid-cols-3 gap-3">
            {[
              { icon: FileSearch, label: "Tra cứu tức thì" },
              { icon: Bot, label: "AI có trích dẫn" },
              { icon: CheckCircle2, label: "Dữ liệu xác thực" },
            ].map(({ icon: Icon, label }) => (
              <div
                key={label}
                className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/20"
              >
                <Icon size={20} />
                <span className="mt-3 block text-xs font-medium text-rose-50">
                  {label}
                </span>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-rose-100">
          © 2026 PolicyMate AI · Nền tảng hỗ trợ sinh viên
        </p>
      </section>

      <section className="relative flex items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-[460px]">
          <div className="mb-9 flex items-center gap-3 text-xl font-bold lg:hidden">
            <span className="grid size-10 place-items-center rounded-xl bg-[#b5121b] text-white">
              <Sparkles size={19} />
            </span>
            PolicyMate AI
          </div>
          <div className="rounded-[24px] border border-[#e6e9ef] bg-white p-6 shadow-[0_24px_70px_rgba(47,31,34,.10)] sm:p-9">
            <span className="text-xs font-bold uppercase tracking-[.14em] text-[#b5121b]">
              Chào mừng trở lại
            </span>
            <h2 className="mt-3 text-3xl font-bold tracking-[-.04em] text-slate-900">
              Đăng nhập tài khoản
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Tiếp tục vào không gian PolicyMate của bạn.
            </p>
            <form onSubmit={handleSubmit} className="mt-7 space-y-4">
              <label className="block">
                <span className="mb-2 block text-xs font-semibold text-slate-700">
                  Email
                </span>
                <span className="flex h-12 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3.5 focus-within:border-[#c7434c] focus-within:bg-white focus-within:ring-4 focus-within:ring-rose-100">
                  <Mail size={17} className="text-slate-400" />
                  <input
                    className="min-w-0 flex-1 border-0 bg-transparent text-sm text-slate-900 outline-none"
                    id="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="email@school.edu"
                  />
                </span>
              </label>
              <label className="block">
                <span className="mb-2 block text-xs font-semibold text-slate-700">
                  Mật khẩu
                </span>
                <span className="flex h-12 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3.5 focus-within:border-[#c7434c] focus-within:bg-white focus-within:ring-4 focus-within:ring-rose-100">
                  <LockKeyhole size={17} className="text-slate-400" />
                  <input
                    className="min-w-0 flex-1 border-0 bg-transparent text-sm text-slate-900 outline-none"
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                </span>
              </label>
              {error && (
                <p
                  className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-sm text-rose-700"
                  role="alert"
                >
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={submitting}
                className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#b5121b] text-sm font-semibold text-white shadow-[0_10px_24px_rgba(181,18,27,.18)] transition hover:-translate-y-0.5 hover:bg-[#930f16] hover:shadow-[0_14px_30px_rgba(181,18,27,.22)] disabled:translate-y-0 disabled:opacity-50"
              >
                {submitting ? "Đang đăng nhập..." : "Đăng nhập"}
                <ArrowRight size={17} />
              </button>
            </form>
            <div className="mt-6 flex items-center justify-center gap-2">
              {QUICK_LOGINS.map((account) => (
                <button
                  key={account.email}
                  type="button"
                  disabled={submitting}
                  onClick={() => doLogin(account.email, account.password)}
                  className="min-h-9 rounded-lg border border-slate-200 bg-white px-4 text-xs font-medium text-[#6f2830] transition hover:border-[#d99da2] hover:bg-rose-50 hover:text-[#930f16] disabled:opacity-50"
                >
                  {account.label}
                </button>
              ))}
            </div>
          </div>
          <p className="mt-5 text-center text-xs text-slate-400">
            Đăng nhập đồng nghĩa với việc bạn đồng ý với điều khoản sử dụng.
          </p>
        </div>
      </section>
    </main>
  );
}
