import type { DocumentContentSection } from "../../types/documents";
import styles from "./DocumentTableOfContents.module.css";

export type DocumentTableOfContentsProps = {
  sections: DocumentContentSection[];
};

export function DocumentTableOfContents({
  sections,
}: DocumentTableOfContentsProps) {
  if (sections.length === 0) return null;

  return (
    <nav className={styles.toc} aria-labelledby="document-toc-title">
      <h2 id="document-toc-title">Mục lục</h2>
      <ol>
        {sections.map((section) => (
          <li key={section.id}>
            <a href={`#${section.id}`}>{section.heading}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
