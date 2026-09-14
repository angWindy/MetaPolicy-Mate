import type {
  DocumentContentSection,
  PolicyDocument,
} from "../../types/documents";
import { DocumentDetailActions } from "./DocumentDetailActions";
import { DocumentSourceViewer } from "./DocumentSourceViewer";
import { DocumentTableOfContents } from "./DocumentTableOfContents";
import styles from "./DocumentDetail.module.css";

export type DocumentDetailProps = {
  document: PolicyDocument;
  sections: DocumentContentSection[];
};

export function DocumentDetail({
  document,
  sections,
}: DocumentDetailProps) {
  return (
    <article className={styles.page}>
      <header className={styles.documentHeader}>
        <div className={styles.titleRow}>
          <div>
            <span>{document.categoryLabel}</span>
            <h2>{document.title}</h2>
            <p>{document.documentNumber}</p>
          </div>
          <span className={`${styles.status} ${styles[document.status]}`}>
            {document.statusLabel}
          </span>
        </div>

        <dl className={styles.metadata}>
          <div>
            <dt>Loại văn bản</dt>
            <dd>{document.categoryLabel}</dd>
          </div>
          <div>
            <dt>Phiên bản</dt>
            <dd>{document.version}</dd>
          </div>
          <div>
            <dt>Ngày hiệu lực</dt>
            <dd>
              <time dateTime={document.effectiveDate}>
                {document.effectiveDateLabel}
              </time>
            </dd>
          </div>
        </dl>

        <DocumentDetailActions
          documentId={document.id}
          documentTitle={document.title}
        />
      </header>

      <div className={styles.bodyGrid}>
        <DocumentTableOfContents sections={sections} />
        <section className={styles.content} aria-labelledby="document-content-title">
          <h2 id="document-content-title">Nội dung văn bản</h2>
          {sections.map((section) => (
            <section
              id={section.id}
              key={section.id}
              className={styles.contentSection}
            >
              <h3>{section.heading}</h3>
              {section.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>
          ))}
        </section>
      </div>

      <DocumentSourceViewer
        documentId={document.id}
        filename={`${document.documentNumber || document.id}.pdf`}
      />
    </article>
  );
}
