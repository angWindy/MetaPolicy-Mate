"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileCheck2,
  FileText,
  MessageSquare,
  Plus,
  UploadCloud,
  Users,
  XCircle,
} from "lucide-react";

import { adminService } from "@/services/adminService";
import { userService } from "@/services/userService";
import type { AdminDocument, AdminStats } from "@/types/admin";
import type { UserResponse } from "@/types/api";
import { StatusBadge } from "@/components/ui";

import styles from "./AdminDashboard.module.css";

const statusMap = {
  DANG_HIEU_LUC: { label: "Đang hiệu lực", tone: "success" as const },
  CHO_XU_LY_NOI_DUNG: { label: "Chờ duyệt", tone: "warning" as const },
  HET_HIEU_LUC: { label: "Hết hiệu lực", tone: "danger" as const },
  BI_THAY_THE: { label: "Bị thay thế", tone: "neutral" as const },
  BAN_NHAP: { label: "Bản nháp", tone: "neutral" as const },
};

export function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [docs, setDocs] = useState<AdminDocument[]>([]);
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, d, u] = await Promise.all([
          adminService.stats(),
          adminService.listDocuments(),
          userService.list({ page: 1, page_size: 100 }),
        ]);
        if (cancelled) return;
        setStats(s);
        setDocs(d.items ?? []);
        setUsers(u.items ?? []);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message ?? "Không tải được dữ liệu");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const total = stats?.totalDocuments ?? 0;
  const active = stats?.activeDocuments ?? 0;
  const pending = stats?.pendingDocuments ?? 0;
  const expired = stats?.expiredDocuments ?? 0;

  const metrics = useMemo(
    () => [
      { label: "Tổng tài liệu", value: total, detail: "Tính từ database", icon: FileText, tone: "blue" },
      { label: "Đang hiệu lực", value: active, detail: `Tỉ lệ ${total ? Math.round((active / total) * 100) : 0}%`, icon: CheckCircle2, tone: "green" },
      { label: "Chờ duyệt", value: pending, detail: "Cần xử lý sớm", icon: Clock3, tone: "orange" },
      { label: "Hết hiệu lực", value: expired, detail: "Cần rà soát phiên bản mới", icon: XCircle, tone: "red" },
      { label: "Người dùng", value: stats?.users ?? users.length, detail: "Đang hoạt động", icon: Users, tone: "violet" },
      { label: "Câu hỏi hôm nay", value: stats?.questionsToday ?? 0, detail: "Đếm từ audit_logs", icon: MessageSquare, tone: "blue" },
    ],
    [total, active, pending, expired, stats?.users, stats?.questionsToday, users.length],
  );

  const recentDocs = useMemo(() => docs.slice(0, 4), [docs]);

  return (
    <div className={styles.page}>
      <section className={styles.welcome}>
        <div>
          <p className={styles.eyebrow}>Workspace quản trị</p>
          <h2>Tổng quan hệ thống</h2>
          <p>Theo dõi tài liệu, người dùng và hoạt động gần đây của PolicyMate AI.</p>
          {error && <p style={{ color: "crimson", marginTop: 8 }}>{error}</p>}
        </div>
        <div className={styles.welcomeActions}>
          <Link className={styles.secondaryButton} href="/admin/documents?status=pending">
            <FileCheck2 size={17} aria-hidden="true" /> Xem tài liệu chờ duyệt
          </Link>
          <Link className={styles.primaryButton} href="/admin/documents#upload">
            <Plus size={17} aria-hidden="true" /> Tải tài liệu lên
          </Link>
        </div>
      </section>

      <section className={styles.metrics} aria-label="Chỉ số hệ thống">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          return (
            <article key={metric.label} className={styles.metricCard}>
              <span className={`${styles.metricIcon} ${styles[metric.tone]}`}><Icon size={20} aria-hidden="true" /></span>
              <p>{metric.label}</p>
              <strong>{metric.value.toLocaleString("vi-VN")}</strong>
              <span>{metric.detail}</span>
            </article>
          );
        })}
      </section>

      <div className={styles.contentGrid}>
        <section className={styles.panel} aria-labelledby="admin-activity-title">
          <div className={styles.panelHeader}>
            <div><h2 id="admin-activity-title">Hoạt động gần đây</h2><p>Theo dõi thay đổi trong hệ thống</p></div>
            <Link href="/admin/activity">Xem tất cả <ArrowRight size={15} aria-hidden="true" /></Link>
          </div>
          <ol className={styles.activityList}>
            {recentDocs.length === 0 && (
              <li><span className={styles.activityIcon}><UploadCloud size={16} /></span><span><strong>Chưa có tài liệu nào được tải lên</strong><small>—</small></span></li>
            )}
            {recentDocs.map((document) => (
              <li key={document.id}>
                <span className={styles.activityIcon}><FileText size={16} aria-hidden="true" /></span>
                <span><strong>{document.title}</strong><small>v{document.version} · {document.documentNumber}</small></span>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.panel} aria-labelledby="admin-attention-title">
          <div className={styles.panelHeader}><div><h2 id="admin-attention-title">Cần xử lý</h2><p>Các việc nên hoàn tất sớm</p></div><AlertCircle size={20} className={styles.alertIcon} aria-hidden="true" /></div>
          <div className={styles.taskList}>
            <Task label="Tài liệu chờ duyệt" count={`${pending} tài liệu`} tone="danger" href="/admin/documents?status=pending" />
            <Task label="Văn bản sắp hết hiệu lực" count={`${expired} tài liệu`} tone="warning" href="/admin/documents?status=expired" />
            <Task label="Người dùng hoạt động" count={`${users.length} người`} tone="info" href="/admin/users" />
          </div>
        </section>
      </div>

      <section className={styles.panel} aria-labelledby="admin-documents-title">
        <div className={styles.panelHeader}><div><h2 id="admin-documents-title">Văn bản mới cập nhật</h2><p>Phiên bản và hiệu lực mới nhất</p></div><Link href="/admin/documents">Xem tất cả <ArrowRight size={15} aria-hidden="true" /></Link></div>
        <div className={styles.documentList}>
          {recentDocs.map((document) => {
            const status = statusMap[document.status as keyof typeof statusMap] ?? statusMap.DANG_HIEU_LUC;
            return <Link href={`/admin/documents/${document.id}`} className={styles.documentRow} key={document.id}><span className={styles.pdfIcon}><FileText size={18} aria-hidden="true" /></span><span className={styles.documentName}><strong>{document.title}</strong><small>{document.documentNumber} · Phiên bản {document.version}</small></span><StatusBadge tone={status.tone} showDot>{status.label}</StatusBadge><span className={styles.documentTime}>{document.updatedAt}</span><ArrowRight size={16} className={styles.rowArrow} aria-hidden="true" /></Link>;
          })}
          {recentDocs.length === 0 && (
            <p style={{ padding: 16, color: "#64748B" }}>Chưa có tài liệu nào. Tải lên văn bản đầu tiên để bắt đầu.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function Task({ label, count, tone, href }: { label: string; count: string; tone: "danger" | "warning" | "info"; href: string }) {
  return <Link href={href} className={styles.task}><span className={`${styles.taskIcon} ${styles[tone]}`}><AlertCircle size={18} aria-hidden="true" /></span><span><strong>{label}</strong><small>{count}</small></span><ArrowRight size={16} aria-hidden="true" /></Link>;
}
