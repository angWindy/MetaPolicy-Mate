"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to login after showing message
    const timer = setTimeout(() => {
      router.push("/login");
    }, 5000);
    return () => clearTimeout(timer);
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 border border-slate-200 text-center">
        <div className="w-16 h-16 rounded-full bg-amber-100 flex items-center justify-center mx-auto mb-6">
          <AlertTriangle className="w-8 h-8 text-amber-600" />
        </div>

        <h1 className="text-2xl font-bold text-slate-900 mb-4">Đăng ký bị vô hiệu hóa</h1>

        <p className="text-slate-600 mb-6">
          Việc đăng ký tài khoản không được phép thực hiện trực tiếp.
          <br />
          Vui lòng liên hệ <strong>quản trị viên</strong> để được tạo tài khoản.
        </p>

        <div className="bg-slate-50 rounded-lg p-4 mb-6 text-left">
          <p className="text-sm font-medium text-slate-700 mb-2">Liên hệ quản trị viên:</p>
          <ul className="text-sm text-slate-600 space-y-1">
            <li>- Email: admin@p234.demo</li>
            <li>- Tài khoản demo: sử dụng form đăng nhập</li>
          </ul>
        </div>

        <Link
          href="/login"
          className="inline-block w-full px-6 py-3 bg-[#b5121b] text-white rounded-lg font-medium hover:bg-[#930f16] transition-colors"
        >
          Quay lại đăng nhập
        </Link>

        <p className="mt-4 text-xs text-slate-400">
          Chuyển hướng tự động sau 5 giây...
        </p>
      </div>
    </div>
  );
}
