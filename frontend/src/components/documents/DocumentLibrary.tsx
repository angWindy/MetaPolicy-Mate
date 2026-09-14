"use client";

import { useMemo, useState } from "react";

import type { PolicyDocument } from "../../types/documents";
import { EmptyState } from "../ui";
import { DocumentRow } from "./DocumentRow";
import styles from "./DocumentLibrary.module.css";

export type DocumentLibraryProps = {
  documents: PolicyDocument[];
  initialQuery?: string;
};

type StatusFilter = "all" | "current" | "expired";

function normalizeSearchValue(value: string): string {
  return value.trim().normalize("NFC").toLocaleLowerCase("vi");
}

export function DocumentLibrary({ documents, initialQuery = "" }: DocumentLibraryProps) {
  const [query, setQuery] = useState(initialQuery);
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState<StatusFilter>("all");

  const categories = useMemo(
    () =>
      Array.from(
        new Map(
          documents.map((document) => [
            document.category,
            document.categoryLabel,
          ]),
        ),
      ),
    [documents],
  );

  const filteredDocuments = useMemo(() => {
    const normalizedQuery = normalizeSearchValue(query);

    return documents.filter((document) => {
      const matchesQuery =
        !normalizedQuery ||
        normalizeSearchValue(document.title).includes(normalizedQuery) ||
        normalizeSearchValue(document.documentNumber).includes(normalizedQuery);
      const matchesCategory =
        category === "all" || document.category === category;
      const matchesStatus = status === "all" || document.status === status;
      return matchesQuery && matchesCategory && matchesStatus;
    });
  }, [category, documents, query, status]);

  return (
    <div className={styles.library}>
      <section className={styles.introduction}>
        <h2>Thư viện Quy chế</h2>
        <p>Tra cứu các văn bản chính thức đang được áp dụng tại nhà trường.</p>
      </section>

      <section className={styles.filters} aria-label="Tìm kiếm và lọc văn bản">
        <label className={styles.searchField}>
          <span className={styles.srOnly}>Tìm văn bản</span>
          <input
            type="search"
            autoComplete="off"
            value={query}
            placeholder="Tìm theo tên hoặc số hiệu văn bản..."
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label>
          <span>Chủ đề</span>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="all">Tất cả chủ đề</option>
            {categories.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Hiệu lực</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
          >
            <option value="all">Tất cả trạng thái</option>
            <option value="current">Đang hiệu lực</option>
            <option value="expired">Hết hiệu lực</option>
          </select>
        </label>
      </section>

      <p className={styles.resultCount} aria-live="polite">
        {filteredDocuments.length} văn bản
      </p>

      {filteredDocuments.length > 0 ? (
        <ul className={styles.list}>
          {filteredDocuments.map((document) => (
            <li key={document.id}>
              <DocumentRow document={document} />
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="Không tìm thấy văn bản phù hợp"
          description={
            query.trim()
              ? `Không có kết quả cho từ khóa “${query.trim()}”. Hãy thử từ khóa hoặc bộ lọc khác.`
              : "Hãy thử thay đổi bộ lọc để xem thêm văn bản."
          }
          icon="▤"
        />
      )}
    </div>
  );
}
