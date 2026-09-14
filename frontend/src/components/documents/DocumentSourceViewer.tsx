"use client";

import { useEffect, useState } from "react";

import { PdfViewer } from "./PdfViewer";

import styles from "./DocumentSourceViewer.module.css";

export type DocumentSourceViewerProps = {
  documentId: string;
  /** Filename to display in the download link; usually the same as the source filename. */
  filename?: string;
};

const DEFAULT_API_URL = "http://localhost:8000";

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; sourceUrl: string; filename: string }
  | { kind: "absent" }
  | { kind: "error"; message: string };

function buildBaseUrl(): string {
  const base =
    process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL;
  return base.replace(/\/+$/, "");
}

function resolveToken(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  try {
    return (
      window.localStorage.getItem(
        "policymate_access_token",
      ) ?? undefined
    );
  } catch {
    return undefined;
  }
}

async function fetchDocumentMeta(
  documentId: string,
): Promise<{
  title?: string;
  filename?: string;
  sourceExists?: boolean;
}> {
  const baseUrl = buildBaseUrl();
  const token = resolveToken();
  const headers = new Headers();
  headers.set("Accept", "application/json");
  if (token) {
    headers.set(
      "Authorization",
      `Bearer ${token}`,
    );
  }
  const response = await fetch(
    `${baseUrl}/api/v1/regulatory-documents/${documentId}`,
    { headers },
  );
  if (response.status === 404) {
    return { sourceExists: false };
  }
  if (!response.ok) {
    throw new Error(
      `GET document ${documentId} returned ${response.status}`,
    );
  }
  const payload = (await response.json()) as {
    id?: string;
    title?: string;
  };
  return {
    title: payload.title,
    sourceExists: true,
  };
}

export function DocumentSourceViewer({
  documentId,
  filename,
}: DocumentSourceViewerProps) {
  const [state, setState] = useState<FetchState>({
    kind: "loading",
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const meta = await fetchDocumentMeta(
          documentId,
        );
        if (cancelled) return;
        if (meta.sourceExists === false) {
          setState({ kind: "absent" });
          return;
        }
        const baseUrl = buildBaseUrl();
        const token = resolveToken();
        const sourceUrl = token
          ? `${baseUrl}/api/v1/regulatory-documents/${documentId}/source?access_token=${encodeURIComponent(
              token,
            )}`
          : `${baseUrl}/api/v1/regulatory-documents/${documentId}/source`;
        setState({
          kind: "ready",
          sourceUrl,
          filename:
            filename ??
            `${documentId}.pdf`,
        });
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            (err as Error).message ??
            "Không tải được văn bản PDF.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, filename]);

  if (state.kind === "loading") {
    return (
      <div className={styles.wrapper}>
        <p className={styles.placeholder}>
          Đang tải bản PDF gốc…
        </p>
      </div>
    );
  }
  if (state.kind === "absent") {
    return (
      <div className={styles.wrapper}>
        <p className={styles.placeholder}>
          Văn bản này chưa được cấp file PDF nguồn.
        </p>
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className={styles.wrapper}>
        <p className={styles.error}>
          Không tải được PDF: {state.message}
        </p>
      </div>
    );
  }
  return (
    <PdfViewer
      src={state.sourceUrl}
      bearerToken={resolveToken()}
      filename={state.filename}
    />
  );
}