"use client";

import { useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
import type { Document } from "@/lib/types";
import { Pill } from "./StatusBadge";
import { VersionRow } from "./VersionRow";

const ACCESS_LEVEL_CONFIG: Record<string, { label: string; tone: "neutral" | "brand" | "warning" }> = {
  public: { label: "Public", tone: "neutral" },
  internal: { label: "Internal", tone: "brand" },
  restricted: { label: "Restricted", tone: "warning" },
};

export function DocumentCard({
  document,
  onRefresh,
}: {
  document: Document;
  onRefresh: () => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const accessCfg =
    ACCESS_LEVEL_CONFIG[document.access_level] ??
    { label: document.access_level, tone: "neutral" as const };

  const hasInFlight = document.versions.some((v) =>
    ["queued", "received", "parsing"].includes(v.processing_status),
  );
  const versionCount = document.versions.length;

  return (
    <div className="bg-white rounded-2xl border border-[var(--color-border)] overflow-hidden transition-all hover:border-[var(--color-border-strong)] hover:shadow-[var(--shadow-card-hover)]">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-5 py-4 flex items-center justify-between gap-4 hover:bg-[var(--color-surface-muted)] transition-colors"
      >
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-100 to-brand-50 text-brand-700 grid place-items-center flex-shrink-0">
            <FileText className="w-5 h-5" />
          </div>
          <div className="text-left min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <h3 className="font-semibold text-[var(--color-ink-primary)] truncate">
                {document.title}
              </h3>
              {hasInFlight && (
                <span className="inline-flex items-center gap-1 text-[10px] text-info font-medium">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-info opacity-75 animate-ping" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-info" />
                  </span>
                  Đang xử lý
                </span>
              )}
            </div>
            <p className="text-sm text-[var(--color-ink-secondary)] mt-0.5 truncate">
              {document.document_number}
              <span className="mx-1.5 text-[var(--color-ink-tertiary)]">·</span>
              {document.owner_department}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-shrink-0">
          <Pill tone={accessCfg.tone} label={accessCfg.label} />
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-[var(--color-surface-muted)] text-[var(--color-ink-secondary)] text-xs">
            <span className="font-medium text-[var(--color-ink-primary)]">{versionCount}</span>
            phiên bản
          </span>
          <ChevronDown
            className={
              "w-4 h-4 text-[var(--color-ink-tertiary)] transition-transform " +
              (isExpanded ? "rotate-180" : "")
            }
          />
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-surface)]">
          <div className="px-5 py-2 grid grid-cols-12 gap-3 text-[11px] font-medium uppercase tracking-wide text-[var(--color-ink-tertiary)]">
            <div className="col-span-3">Phiên bản</div>
            <div className="col-span-3">Xử lý</div>
            <div className="col-span-2">Pháp lý</div>
            <div className="col-span-2">Hiệu lực</div>
            <div className="col-span-2 text-right">Thao tác</div>
          </div>
          {document.versions.length === 0 ? (
            <div className="px-5 py-6 text-sm text-[var(--color-ink-secondary)]">
              Chưa có phiên bản nào.
            </div>
          ) : (
            document.versions.map((version) => (
              <VersionRow
                key={version.id}
                version={version}
                onRefresh={onRefresh}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
