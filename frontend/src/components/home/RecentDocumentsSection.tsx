import Link from "next/link";
import { ArrowRight, Bookmark, FileText } from "lucide-react";

import type { RecentDocument } from "../../types/home";
import styles from "./RecentDocumentsSection.module.css";

export type RecentDocumentsSectionProps = {
  documents: RecentDocument[];
  title?: string;
};

export function RecentDocumentsSection({
  documents,
  title = "Văn bản mới cập nhật",
}: RecentDocumentsSectionProps) {
  if (documents.length === 0) return null;

  return (
    <section className={styles.section} aria-labelledby="recent-documents-title">
      <div className={styles.sectionHeading}><h2 id="recent-documents-title">{title}</h2><Link href="/documents">Xem thư viện <ArrowRight size={14} aria-hidden="true" /></Link></div>
      <div className={styles.list}>
        {documents.map((document) => (
          <article key={document.id} className={styles.row}>
            <span className={styles.documentIcon} aria-hidden="true">
              <FileText size={18} />
            </span>
            <div className={styles.content}>
              <div className={styles.heading}>
                <h3>{document.title}</h3>
                <span
                  className={`${styles.status} ${styles[document.status]}`}
                >
                  {document.statusLabel}
                </span>
              </div>
              <p>{document.type}</p>
              <time dateTime={document.updatedAt}>
                Cập nhật: {document.updatedLabel}
              </time>
            </div>
            <Link className={styles.viewLink} href={document.href} aria-label={`Xem ${document.title}`}>Xem chi tiết</Link>
            <Link className={styles.saveLink} href="/saved" aria-label={`Mở mục đã lưu cho ${document.title}`}><Bookmark size={17} /></Link>
          </article>
        ))}
      </div>
    </section>
  );
}
