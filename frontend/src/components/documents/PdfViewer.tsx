"use client";

import { Download, ExternalLink, ZoomIn, ZoomOut } from "lucide-react";
import { useMemo, useState } from "react";

import styles from "./PdfViewer.module.css";

export type PdfViewerProps = {
  /** Fully-qualified URL of the PDF (e.g. http://localhost:8000/api/v1/regulatory-documents/.../source). */
  src: string;
  /** Bearer access token; appended as a query string because the browser's built-in PDF viewer ignores headers. */
  bearerToken?: string;
  /** Original filename; surfaced in the download link. */
  filename: string;
};

const ZOOM_LEVELS = [0.6, 0.8, 1, 1.25, 1.5, 2];

export function PdfViewer({
  src,
  bearerToken,
  filename,
}: PdfViewerProps) {
  const [zoomIndex, setZoomIndex] = useState(2);
  const [tokenInput, setTokenInput] = useState<string>(
    bearerToken ?? "",
  );

  const signedSrc = useMemo(() => {
    if (!tokenInput) return src;
    const separator = src.includes("?") ? "&" : "?";
    return `${src}${separator}access_token=${encodeURIComponent(
      tokenInput,
    )}`;
  }, [src, tokenInput]);

  const zoom = ZOOM_LEVELS[zoomIndex] ?? 1;

  return (
    <div className={styles.wrapper}>
      <div className={styles.toolbar}>
        <div className={styles.zoomControls}>
          <button
            type="button"
            aria-label="Thu nhỏ"
            onClick={() =>
              setZoomIndex((idx) =>
                Math.max(0, idx - 1),
              )
            }
            disabled={zoomIndex <= 0}
          >
            <ZoomOut size={16} aria-hidden="true" />
          </button>
          <span aria-live="polite">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            aria-label="Phóng to"
            onClick={() =>
              setZoomIndex((idx) =>
                Math.min(
                  ZOOM_LEVELS.length - 1,
                  idx + 1,
                ),
              )
            }
            disabled={
              zoomIndex >= ZOOM_LEVELS.length - 1
            }
          >
            <ZoomIn size={16} aria-hidden="true" />
          </button>
        </div>
        <a
          href={signedSrc}
          download={filename}
          className={styles.toolbarLink}
        >
          <Download size={15} aria-hidden="true" />
          Tải xuống
        </a>
        <a
          href={signedSrc}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.toolbarLink}
        >
          <ExternalLink size={15} aria-hidden="true" />
          Mở trong tab mới
        </a>
      </div>

      <div
        className={styles.frame}
        style={{
          transform: `scale(${zoom})`,
          transformOrigin: "top left",
        }}
      >
        <iframe
          title={filename}
          src={signedSrc}
          className={styles.iframe}
        />
      </div>

      {!bearerToken && (
        <details className={styles.tokenFallback}>
          <summary>
            Token truy cập trống — dán Bearer token để xem PDF:
          </summary>
          <input
            type="password"
            value={tokenInput}
            placeholder="eyJhbGciOi..."
            onChange={(event) =>
              setTokenInput(event.target.value)
            }
          />
        </details>
      )}
    </div>
  );
}