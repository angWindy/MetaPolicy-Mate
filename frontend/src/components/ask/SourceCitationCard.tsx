import Link from "next/link";

import type { ReferenceSource } from "../../types/ask";
import styles from "./SourceCitationCard.module.css";

export type SourceCitationCardProps = {
  source: ReferenceSource;
};

export function SourceCitationCard({ source }: SourceCitationCardProps) {
  const validityMessage =
    source.validityStatus === "expired"
      ? "Văn bản đã hết hiệu lực. Hãy kiểm tra văn bản thay thế trước khi áp dụng."
      : source.validityStatus === "superseded"
        ? "Nguồn này có phiên bản mới hơn. Nên ưu tiên phiên bản mới nhất."
        : null;

  return (
    <Link
      className={styles.card}
      href={source.href}
      aria-label={`Mở nguồn ${source.title}, ${source.reference}`}
    >
      <span className={styles.topline}>
        <span className={styles.documentType}>{source.documentType}</span>
        <span
          className={`${styles.validity} ${styles[source.validityStatus]}`}
        >
          {source.validityLabel}
        </span>
      </span>
      <strong>{source.title}</strong>
      <dl className={styles.metadata}>
        <div>
          <dt>Điều/khoản</dt>
          <dd>{source.reference}</dd>
        </div>
        <div>
          <dt>Trang</dt>
          <dd>{source.page}</dd>
        </div>
        <div>
          <dt>Phiên bản</dt>
          <dd>{source.version}</dd>
        </div>
        <div>
          <dt>Hiệu lực</dt>
          <dd>
            <time dateTime={source.effectiveDate}>
              {source.effectiveDateLabel}
            </time>
          </dd>
        </div>
      </dl>
      {validityMessage && (
        <span className={styles.validityNote} role="note">
          <span aria-hidden="true">!</span>
          {validityMessage}
        </span>
      )}
      {source.excerpt && <p>{source.excerpt}</p>}
    </Link>
  );
}
