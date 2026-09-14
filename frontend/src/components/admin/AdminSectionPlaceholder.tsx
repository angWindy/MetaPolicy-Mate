import Link from "next/link";
import { ArrowLeft, CheckCircle2, Construction, ShieldCheck } from "lucide-react";

import styles from "./AdminSectionPlaceholder.module.css";

/**
 * Sections that have a dedicated page rendered elsewhere. The placeholder
 * is only shown for sections that don't yet have a real route (review,
 * users, permissions, activity, settings). Unknown sections (e.g. typos
 * like ``/admin/foo-bar``) render the not-found view instead of silently
 * falling through to ``settings``.
 */
const IMPLEMENTED_SECTIONS = new Set([
  "documents",
  "organizations",
  "users",
  "permissions",
]);

const sections: Record<
  string,
  {
    title: string;
    description: string;
    icon: typeof ShieldCheck;
    next: string[];
  }
> = {
  review: {
    title: "Duyệt tài liệu",
    description:
      "Kiểm tra metadata, phiên bản và đưa tài liệu qua quy trình approve → index → publish.",
    icon: CheckCircle2,
    next: [
      "Danh sách tài liệu chờ xử lý",
      "Xem trạng thái OCR và indexing",
      "Duyệt hoặc yêu cầu bổ sung",
    ],
  },
  users: {
    title: "Quản lý người dùng",
    description:
      "Quản lý tài khoản sinh viên, giảng viên, lãnh đạo và quản trị viên.",
    icon: ShieldCheck,
    next: [
      "Tìm theo tên, email hoặc mã người dùng",
      "Theo dõi trạng thái hoạt động",
      "Gán vai trò và quyền truy cập",
    ],
  },
  permissions: {
    title: "Phân quyền",
    description:
      "Kiểm soát quyền document.read, document.upload và document.update theo vai trò.",
    icon: ShieldCheck,
    next: [
      "Vai trò và permission hiện tại",
      "Phạm vi tài liệu theo đơn vị",
      "Kiểm tra quyền trước khi thao tác",
    ],
  },
  activity: {
    title: "Nhật ký hoạt động",
    description:
      "Theo dõi changelog tài liệu và các thao tác quan trọng trong hệ thống.",
    icon: CheckCircle2,
    next: [
      "Lọc theo hành động và thời gian",
      "Xem giá trị trước và sau thay đổi",
      "Giữ changelog ở chế độ read-only",
    ],
  },
  settings: {
    title: "Cài đặt hệ thống",
    description:
      "Thiết lập thông tin trường, cấu hình AI, thông báo và phiên quản trị.",
    icon: Construction,
    next: [
      "Thông tin hệ thống",
      "Cấu hình nguồn AI và tài liệu",
      "Bảo mật và phiên đăng nhập",
    ],
  },
};

export function AdminSectionPlaceholder({ section }: { section: string }) {
  // Implemented sections render their own page (not this placeholder) so
  // reaching this component with "documents" would be a bug in routing.
  if (IMPLEMENTED_SECTIONS.has(section)) {
    return null;
  }

  const config = sections[section];
  if (!config) {
    return (
      <div className={styles.page}>
        <Link href="/admin" className={styles.back}>
          <ArrowLeft size={16} aria-hidden="true" /> Về tổng quan
        </Link>
        <section className={styles.hero}>
          <h2>Trang không tồn tại</h2>
          <p>
            Mục <code>/admin/{section}</code> chưa được hỗ trợ. Vui lòng chọn
            một mục hợp lệ trong thanh bên.
          </p>
        </section>
      </div>
    );
  }

  const Icon = config.icon;
  return (
    <div className={styles.page}>
      <Link href="/admin" className={styles.back}>
        <ArrowLeft size={16} aria-hidden="true" /> Về tổng quan
      </Link>
      <section className={styles.hero}>
        <span className={styles.icon}>
          <Icon size={24} aria-hidden="true" />
        </span>
        <h2>{config.title}</h2>
        <p>{config.description}</p>
        <span className={styles.status}>
          Đã có backend contract · UI đang hoàn thiện
        </span>
      </section>
      <section className={styles.panel}>
        <h3>Phạm vi màn hình</h3>
        <ul>
          {config.next.map((item) => (
            <li key={item}>
              <CheckCircle2 size={17} aria-hidden="true" /> {item}
            </li>
          ))}
        </ul>
        <Link href="/admin/documents" className={styles.action}>
          Mở quản lý tài liệu{" "}
          <ArrowLeft size={16} aria-hidden="true" className={styles.arrow} />
        </Link>
      </section>
    </div>
  );
}