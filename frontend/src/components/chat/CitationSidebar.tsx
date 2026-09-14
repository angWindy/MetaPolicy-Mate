"use client";

import {
  ExternalLink,
  FileText,
  X,
} from "lucide-react";

import type { Citation } from "../../lib/types";

export interface CitationSidebarProps {
  /** All citations for the current assistant message. */
  citations: Citation[];
  /** chunk_id currently being inspected (drives the detail panel). */
  selectedChunkId: string | null;
  /** Called when the user wants to dismiss the sidebar. */
  onClose: () => void;
  /** Called when the user picks a different citation from the list. */
  onSelect: (chunkId: string) => void;
}

/**
 * Citation sidebar — ChatGPT / Gemini-style right-side panel.
 *
 * Display rule (2026-09-06): each citation row shows ONLY the article /
 * clause locator PLUS the document number. There are no ``[1]`` /
 * ``[2]`` index chips anymore — those used to leak the LLM's
 * temporary evidence ordering into the UI, which confused users about
 * whether the numbers meant something semantic.
 *
 * Click behavior: clicking the detail header's "Xem văn bản" link, or
 * any citation row, opens the canonical document detail page at
 * ``/documents/{document_id}`` (NOT the library index page). When
 * ``document_id`` is missing, we fall back to the document library so
 * the user always lands somewhere useful.
 */
export function CitationSidebar({
  citations,
  selectedChunkId,
  onClose,
  onSelect,
}: CitationSidebarProps) {
  const selected =
    citations.find((citation) => citation.chunk_id === selectedChunkId) ??
    citations[0] ??
    null;

  const confidencePercent =
    selected && typeof selected.rerank_score === "number"
      ? Math.round(selected.rerank_score * 100)
      : null;

  const detailHref = selected
    ? buildDocumentHref(selected.document_id, selected.source_url)
    : null;

  return (
    <aside
      className="w-full md:w-96 lg:w-[28rem] flex-shrink-0 border-l border-[var(--color-border)] bg-white flex flex-col h-full"
      aria-label="Chi tiết trích dẫn"
    >
      <header className="px-5 py-4 border-b border-[var(--color-border)] flex items-center justify-between">
        <h3 className="font-semibold text-[var(--color-ink-primary)]">
          Nguồn trích dẫn
        </h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="Đóng bảng trích dẫn"
          className="p-1.5 rounded-md text-[var(--color-ink-tertiary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-ink-primary)] transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </header>

      {selected ? (
        <div className="px-5 py-5 border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] space-y-3 overflow-y-auto">
          <div className="flex items-start gap-2">
            <FileText className="w-4 h-4 text-brand-600 mt-0.5 flex-shrink-0" />
            <div className="min-w-0">
              <p className="font-medium text-[var(--color-ink-primary)] text-sm break-words">
                {selected.title || selected.document_number}
              </p>
              <p className="text-xs text-[var(--color-ink-secondary)] mt-0.5 break-words">
                {selected.document_number}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {selected.article && (
              <span className="text-xs px-2 py-0.5 rounded bg-white border border-[var(--color-border)] text-[var(--color-ink-secondary)]">
                Điều {selected.article}
              </span>
            )}
            {selected.clause && (
              <span className="text-xs px-2 py-0.5 rounded bg-white border border-[var(--color-border)] text-[var(--color-ink-secondary)]">
                Khoản {selected.clause}
              </span>
            )}
            {selected.section && (
              <span className="text-xs px-2 py-0.5 rounded bg-white border border-[var(--color-border)] text-[var(--color-ink-secondary)]">
                {selected.section}
              </span>
            )}
            {selected.page && (
              <span className="text-xs px-2 py-0.5 rounded bg-white border border-[var(--color-border)] text-[var(--color-ink-secondary)]">
                Trang {selected.page}
              </span>
            )}
            {selected.citation_kind === "winning" ? (
              <span className="text-xs px-2 py-0.5 rounded bg-brand-50 text-brand-700 font-medium">
                Trích dẫn chính
              </span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-ink-secondary)]">
                Mở rộng
              </span>
            )}
          </div>

          {confidencePercent !== null && (
            <div>
              <div className="flex items-center justify-between text-xs text-[var(--color-ink-secondary)] mb-1">
                <span>Độ tin cậy từ reranker</span>
                <span className="font-medium">{confidencePercent}%</span>
              </div>
              <div className="h-1.5 bg-[var(--color-surface)] rounded overflow-hidden">
                <div
                  className="h-full bg-brand-500 transition-all"
                  style={{ width: `${confidencePercent}%` }}
                  role="progressbar"
                  aria-valuenow={confidencePercent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
            </div>
          )}

          {selected.excerpt && (
            <blockquote className="text-sm italic text-[var(--color-ink-primary)] border-l-2 border-brand-500 pl-3 py-1">
              {selected.excerpt}
            </blockquote>
          )}

          {detailHref && (
            <a
              href={detailHref}
              className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700 transition-colors"
            >
              <ExternalLink className="w-3 h-3" />
              Xem văn bản
            </a>
          )}
        </div>
      ) : (
        <div className="px-5 py-5 text-sm text-[var(--color-ink-tertiary)]">
          Chọn một trích dẫn để xem chi tiết.
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <div className="px-5 py-3">
          <p className="text-xs font-medium text-[var(--color-ink-tertiary)] uppercase tracking-wide mb-2">
            Tất cả trích dẫn ({citations.length})
          </p>
          <ul className="space-y-1">
            {citations.map((citation) => {
              const isSelected =
                citation.chunk_id === (selectedChunkId ?? selected?.chunk_id);
              const href = buildDocumentHref(citation.document_id, citation.source_url);
              const locator = buildLocatorLabel(citation);
              return (
                <li key={citation.chunk_id}>
                  <a
                    href={href}
                    className={
                      "w-full text-left px-3 py-2 rounded-md flex items-start gap-2 transition-colors block " +
                      (isSelected
                        ? "bg-brand-50 text-brand-900"
                        : "hover:bg-[var(--color-surface-muted)] text-[var(--color-ink-primary)]")
                    }
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium break-words">
                        {locator}
                      </span>
                      <span className="block text-xs text-[var(--color-ink-secondary)] break-words">
                        {citation.document_number}
                      </span>
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </aside>
  );
}

/**
 * Build the document-detail URL for a citation.
 *
 * Prefer ``/documents/{document_id}`` (the canonical detail page); only
 * fall back to the library index or an external source URL when
 * ``document_id`` is missing. This is the change that ships with the
 * 2026-09-06 UX update — previously citations with no ``document_id``
 * silently sent users to ``/documents`` (the library), which felt like
 * a broken link.
 */
function buildDocumentHref(
  documentId: string | null | undefined,
  sourceUrl: string | null | undefined,
): string {
  if (documentId && documentId.trim()) {
    return `/documents/${documentId}`;
  }
  if (sourceUrl && sourceUrl.trim()) {
    return sourceUrl;
  }
  return "/documents";
}

/**
 * Build the locator label for a citation row. Format:
 *   - ``Điều X · Số hiệu văn bản`` when article exists
 *   - ``Số hiệu văn bản`` (only) when no article / clause is available
 *
 * The previous design used a numbered index chip like ``[1]`` /
 * ``[2]``; those are gone now because they were a UI-only construct
 * that had no semantic meaning once the LLM cites by-prose.
 */
function buildLocatorLabel(citation: Citation): string {
  const locatorParts: string[] = [];
  if (citation.article) {
    locatorParts.push(`Điều ${citation.article}`);
  }
  if (citation.clause) {
    locatorParts.push(`Khoản ${citation.clause}`);
  }
  const locator = locatorParts.join(" · ");
  return locator || citation.document_number || "Văn bản";
}