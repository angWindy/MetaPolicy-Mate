import Link from "next/link";

import type { PolicyDocument } from "../../types/documents";
import styles from "./DocumentRow.module.css";

export type DocumentRowProps = {
  document: PolicyDocument;
};

/**
 * Row rendering for a single document in a list / search result.
 *
 * The dedicated "Hỏi AI" action has been removed — the Ask AI surface
 * now lives exclusively in the floating chat widget anchored to the
 * bottom-right of every page. Users wanting to ask about a specific
 * document open the widget and reference the title / document number
 * in their question.
 */
export function DocumentRow({ document }: DocumentRowProps) {
  return (
    <article className={styles.document}>
      <span className={styles.icon} aria-hidden="true">
        ▤
      </span>
      <div className={styles.content}>
        <div className={styles.heading}>
          <h3>{document.title}</h3>
          <span className={`${styles.status} ${styles[document.status]}`}>
            {document.statusLabel}
          </span>
        </div>
        <p>
          {document.categoryLabel} · {document.documentNumber}
        </p>
        <dl>
          <div>
            <dt>Phiên bản</dt>
            <dd>{document.version}</dd>
          </div>
          <div>
            <dt>Hiệu lực</dt>
            <dd>
              <time dateTime={document.effectiveDate}>
                {document.effectiveDateLabel}
              </time>
            </dd>
          </div>
        </dl>
      </div>
      <div className={styles.actions}>
        <Link href={document.href} aria-label={`Xem ${document.title}`}>
          Xem văn bản
        </Link>
      </div>
    </article>
  );
}
