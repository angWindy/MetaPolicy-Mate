import { Bell, Bookmark, Clock3, UserRound, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { AuthenticatedLayout } from "@/components/layout";

type StudentRoutePlaceholderProps = {
  kind: "history" | "saved" | "notifications" | "profile";
};

const routeContent: Record<
  StudentRoutePlaceholderProps["kind"],
  { title: string; description: string; icon: LucideIcon }
> = {
  history: {
    title: "Lịch sử tra cứu",
    description: "Các câu hỏi và lần tra cứu của bạn sẽ được quản lý tại đây.",
    icon: Clock3,
  },
  saved: {
    title: "Đã lưu",
    description: "Các câu trả lời và văn bản bạn đánh dấu sẽ xuất hiện tại đây.",
    icon: Bookmark,
  },
  notifications: {
    title: "Thông báo",
    description: "Các cập nhật quan trọng về quy chế và tài liệu sẽ xuất hiện tại đây.",
    icon: Bell,
  },
  profile: {
    title: "Hồ sơ sinh viên",
    description: "Thông tin tài khoản và tùy chọn cá nhân sẽ được quản lý tại đây.",
    icon: UserRound,
  },
};

export function StudentRoutePlaceholder({ kind }: StudentRoutePlaceholderProps) {
  const content = routeContent[kind];
  const Icon = content.icon;

  return (
    <AuthenticatedLayout title={content.title} notificationCount={0}>
      <section className="mx-auto grid min-h-[55vh] max-w-2xl place-items-center px-4 py-12 text-center">
        <div>
          <span
            className="mx-auto grid size-12 place-items-center rounded-xl bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
            aria-hidden="true"
          >
            <Icon size={22} strokeWidth={1.8} />
          </span>
          <h2 className="mt-4 text-xl font-semibold text-[var(--color-text)]">{content.title}</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">{content.description}</p>
          <Link
            href="/student"
            className="mt-6 inline-flex min-h-11 items-center justify-center rounded-[10px] bg-[var(--color-primary)] px-4 text-sm font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
          >
            Về trang chủ
          </Link>
        </div>
      </section>
    </AuthenticatedLayout>
  );
}
