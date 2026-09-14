"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Download, FileText, Loader2 } from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";

// Configure PDF.js worker — must be set before any rendering.
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface DocumentPdfViewerProps {
  documentId: string;
  documentTitle?: string;
  sourceFilename?: string;
}

/**
 * In-browser PDF renderer for the admin document detail page.
 *
 * Uses pdfjs-dist to render each page into a <canvas>, giving precise
 * control over scale and layout. No external dependencies beyond the
 * pdfjs-dist package itself.
 */
export function DocumentPdfViewer({
  documentId,
  documentTitle,
  sourceFilename,
}: DocumentPdfViewerProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [downloading, setDownloading] = useState<boolean>(false);
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [scale, setScale] = useState(1.4);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lastBlobRef = useRef<string | null>(null);

  // ── 1. Fetch PDF blob once ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        setLoading(true);
        setError(null);

        const token =
          typeof window !== "undefined"
            ? window.localStorage.getItem("policymate_access_token")
            : null;

        const response = await fetch(
          `/api/v1/regulatory-documents/${documentId}/source`,
          {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            credentials: "include",
          },
        );

        if (!response.ok) {
          throw new Error(
            `Không tải được tài liệu (HTTP ${response.status}).`,
          );
        }

        const blob = await response.blob();
        if (cancelled) return;

        const url = URL.createObjectURL(blob);
        if (lastBlobRef.current) URL.revokeObjectURL(lastBlobRef.current);
        lastBlobRef.current = url;
        setBlobUrl(url);

        // Load PDF with pdfjs-dist.
        const loadingTask = pdfjsLib.getDocument({ url });
        const pdfDoc = await loadingTask.promise;
        if (cancelled) return;

        setPdf(pdfDoc);
        setTotalPages(pdfDoc.numPages);
        setCurrentPage(1);
      } catch (e) {
        if (!cancelled) {
          setError(
            (e as Error).message ??
              "Không tải được tệp nguồn. Vui lòng thử lại.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (lastBlobRef.current) {
        URL.revokeObjectURL(lastBlobRef.current);
        lastBlobRef.current = null;
      }
    };
  }, [documentId]);

  // ── 2. Render current page whenever pdf / page / scale changes ─────────────
  useEffect(() => {
    if (!pdf || !canvasRef.current) return;

    let cancelled = false;

    (async () => {
      try {
        const page = await pdf.getPage(currentPage);
        if (cancelled) return;

        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const viewport = page.getViewport({ scale });
        canvas.width = viewport.width;
        canvas.height = viewport.height;

        await page.render({ canvas, canvasContext: ctx, viewport }).promise;
      } catch {
        // Silently ignore render errors during fast page changes.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdf, currentPage, scale]);

  // ── 3. Page navigation ───────────────────────────────────────────────────
  function goToPrev() {
    setCurrentPage((p) => Math.max(1, p - 1));
  }
  function goToNext() {
    setCurrentPage((p) => Math.min(totalPages, p + 1));
  }

  // ── 4. Download ──────────────────────────────────────────────────────────
  async function handleDownload() {
    if (!blobUrl) return;
    try {
      setDownloading(true);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = sourceFilename ?? `${documentTitle ?? "document"}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) {
      setError((e as Error).message ?? "Không tải xuống được.");
    } finally {
      setDownloading(false);
    }
  }

  // ── 5. Render ────────────────────────────────────────────────────────────
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        height: "100%",
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 14px",
          background: "#fff",
          border: "1px solid var(--color-border)",
          borderRadius: 10,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            color: "var(--color-text-muted)",
          }}
        >
          <FileText size={16} aria-hidden="true" />
          <span>
            Xem nội dung tài liệu{" "}
            {sourceFilename ? (
              <code style={{ fontSize: 12 }}>{sourceFilename}</code>
            ) : null}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* Zoom out */}
          <button
            type="button"
            onClick={() => setScale((s) => Math.max(0.6, s - 0.2))}
            style={{
              padding: "5px 10px",
              border: "1px solid var(--color-border)",
              borderRadius: 6,
              background: "#fff",
              fontSize: 12,
              cursor: "pointer",
            }}
            title="Thu nhỏ"
          >
            −
          </button>
          <span style={{ fontSize: 12, minWidth: 40, textAlign: "center" }}>
            {Math.round(scale * 100)}%
          </span>
          {/* Zoom in */}
          <button
            type="button"
            onClick={() => setScale((s) => Math.min(3, s + 0.2))}
            style={{
              padding: "5px 10px",
              border: "1px solid var(--color-border)",
              borderRadius: 6,
              background: "#fff",
              fontSize: 12,
              cursor: "pointer",
            }}
            title="Phóng to"
          >
            +
          </button>
        </div>

        <button
          type="button"
          onClick={handleDownload}
          disabled={downloading || loading || !!error}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "7px 14px",
            border: "1px solid var(--color-primary)",
            borderRadius: 8,
            background: "#fff",
            color: "var(--color-primary)",
            fontSize: 13,
            fontWeight: 600,
            cursor:
              downloading || loading || error ? "not-allowed" : "pointer",
            opacity: downloading || loading || error ? 0.6 : 1,
          }}
        >
          {downloading ? (
            <Loader2
              size={14}
              aria-hidden="true"
              className="animate-spin"
            />
          ) : (
            <Download size={14} aria-hidden="true" />
          )}
          {downloading ? "Đang tải…" : "Tải xuống"}
        </button>
      </div>

      {/* PDF canvas container */}
      <div
        style={{
          flex: 1,
          border: "1px solid var(--color-border)",
          borderRadius: 10,
          background: "#525659", // browser-like grey bg for scroll context
          overflowY: "auto",
          overflowX: "auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "16px 16px 24px",
        }}
      >
        {loading && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 10,
              padding: 40,
              color: "#fff",
              fontSize: 13,
            }}
          >
            <Loader2
              size={28}
              aria-hidden="true"
              className="animate-spin"
            />
            <span>Đang tải tệp nguồn…</span>
          </div>
        )}

        {error && (
          <div
            style={{
              padding: 24,
              textAlign: "center",
              color: "#dc2626",
              fontSize: 14,
              background: "#fff",
              borderRadius: 8,
              width: "100%",
            }}
          >
            <p style={{ fontWeight: 600, marginBottom: 8 }}>
              Không thể hiển thị tài liệu
            </p>
            <p style={{ color: "var(--color-text-muted)" }}>{error}</p>
          </div>
        )}

        {pdf && !loading && !error && (
          <>
            {/* Canvas */}
            <canvas
              ref={canvasRef}
              style={{
                display: "block",
                boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                background: "#fff",
              }}
            />

            {/* Page navigator */}
            {totalPages > 1 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginTop: 16,
                  background: "#fff",
                  borderRadius: 8,
                  padding: "8px 16px",
                }}
              >
                <button
                  type="button"
                  onClick={goToPrev}
                  disabled={currentPage <= 1}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 32,
                    height: 32,
                    border: "1px solid var(--color-border)",
                    borderRadius: 6,
                    background: "#fff",
                    cursor: currentPage <= 1 ? "not-allowed" : "pointer",
                    opacity: currentPage <= 1 ? 0.4 : 1,
                  }}
                  aria-label="Trang trước"
                >
                  <ChevronLeft size={16} aria-hidden="true" />
                </button>

                <span style={{ fontSize: 13, whiteSpace: "nowrap" }}>
                  Trang{" "}
                  <strong>{currentPage}</strong> / <strong>{totalPages}</strong>
                </span>

                <button
                  type="button"
                  onClick={goToNext}
                  disabled={currentPage >= totalPages}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 32,
                    height: 32,
                    border: "1px solid var(--color-border)",
                    borderRadius: 6,
                    background: "#fff",
                    cursor:
                      currentPage >= totalPages ? "not-allowed" : "pointer",
                    opacity: currentPage >= totalPages ? 0.4 : 1,
                  }}
                  aria-label="Trang sau"
                >
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
