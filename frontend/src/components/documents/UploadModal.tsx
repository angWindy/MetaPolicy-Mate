"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Upload, X } from "lucide-react";
import { fetchVersionStatus, ingestDocument, previewMetadata } from "@/lib/api";
import type { MetadataPreview, VersionStatusResponse } from "@/lib/types";
import { ConfidenceBadge, ProcessingStatusBadge } from "./StatusBadge";
import { ProcessingTimeline } from "./ProcessingTimeline";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function UploadModal({ isOpen, onClose, onSuccess }: UploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [preview, setPreview] = useState<MetadataPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [trackingVersionId, setTrackingVersionId] = useState<string | null>(null);
  const [trackStatus, setTrackStatus] = useState<VersionStatusResponse | null>(null);
  const [trackError, setTrackError] = useState<string | null>(null);
  const successFiredRef = useRef(false);

  const resetForm = () => {
    setFile(null);
    setPreview(null);
    setPreviewError(null);
    setTrackingVersionId(null);
    setTrackStatus(null);
    setTrackError(null);
    successFiredRef.current = false;
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const runPreview = async (selectedFile: File) => {
    setIsPreviewing(true);
    setPreview(null);
    setPreviewError(null);
    try {
      const result = await previewMetadata(selectedFile);
      setPreview(result);
    } catch (error) {
      setPreviewError(
        error instanceof Error ? error.message : "Preview failed",
      );
    } finally {
      setIsPreviewing(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    if (selected) void runPreview(selected);
    else {
      setPreview(null);
      setPreviewError(null);
    }
  };

  useEffect(() => {
    if (!trackingVersionId) return;
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;

    const tick = async () => {
      try {
        const status = await fetchVersionStatus(trackingVersionId);
        if (cancelled) return;
        setTrackStatus(status);
        const terminal =
          status.processing_status === "review_required" ||
          status.processing_status === "failed";
        if (terminal && !successFiredRef.current) {
          successFiredRef.current = true;
          onSuccess();
        }
        return terminal;
      } catch (err) {
        if (cancelled) return;
        setTrackError(err instanceof Error ? err.message : "Polling failed");
        return true;
      }
    };

    void tick().then((terminal) => {
      if (cancelled || terminal) return;
      interval = setInterval(async () => {
        const done = await tick();
        if (done && interval) clearInterval(interval);
      }, 3000);
    });

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [trackingVersionId, onSuccess]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      alert("Vui lòng chọn file");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await ingestDocument(file);
      setTrackingVersionId(result.version_id);
      setFile(null);
      setPreview(null);
      setPreviewError(null);
    } catch (error) {
      alert(`Lỗi: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  // ── Tracking view ────────────────────────────────────────────────────────

  if (trackingVersionId) {
    const status = trackStatus?.processing_status ?? "queued";
    const isFailed = status === "failed";
    const isDone = status === "review_required";
    const isTerminal = isDone || isFailed;

    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl w-full max-w-lg shadow-[var(--shadow-elevated)]">
          <div className="px-6 py-5 border-b border-[var(--color-border)] flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-[var(--color-ink-primary)]">
                {isFailed
                  ? "Xử lý thất bại"
                  : isDone
                  ? "Hoàn tất xử lý"
                  : "Đang xử lý tài liệu"}
              </h2>
              <p className="text-xs text-[var(--color-ink-tertiary)] mt-0.5 font-mono break-all">
                {trackingVersionId}
              </p>
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
            >
              <X className="w-4 h-4 text-[var(--color-ink-tertiary)]" />
            </button>
          </div>

          <div className="p-6 space-y-6">
            <div className="flex items-center gap-3">
              <ProcessingStatusBadge status={status} />
              {!isTerminal && (
                <span className="text-xs text-[var(--color-ink-secondary)]">
                  Cập nhật mỗi 3 giây
                </span>
              )}
            </div>

            <ProcessingTimeline status={status} failed={isFailed} />

            {!isTerminal && (
              <div className="h-1.5 w-full rounded-full bg-[var(--color-surface-muted)] overflow-hidden">
                <div className="h-full bg-gradient-to-r from-brand-500 to-brand-700 progress-indeterminate rounded-full" />
              </div>
            )}

            {trackStatus && (
              <div className="space-y-3">
                {trackStatus.chunk_count > 0 && (
                  <div className="flex items-center justify-between p-3 rounded-xl bg-[var(--color-surface-muted)]">
                    <span className="text-sm text-[var(--color-ink-secondary)]">
                      Số chunks đã tạo
                    </span>
                    <span className="font-semibold text-[var(--color-ink-primary)]">
                      {trackStatus.chunk_count}
                    </span>
                  </div>
                )}

                {trackStatus.warnings.length > 0 && (
                  <div className="p-4 rounded-xl bg-warning-soft border border-warning/30">
                    <div className="flex items-center gap-2 mb-2 text-warning">
                      <AlertTriangle className="w-4 h-4" />
                      <p className="font-medium text-sm">Cảnh báo</p>
                    </div>
                    <ul className="space-y-1 text-sm text-[var(--color-ink-secondary)]">
                      {trackStatus.warnings.map((w, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-warning flex-shrink-0" />
                          <span>{w}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {isFailed && trackStatus.error && (
                  <div className="p-4 rounded-xl bg-danger-soft border border-danger/30">
                    <p className="font-medium text-sm text-danger mb-1">
                      Lỗi xử lý
                    </p>
                    <p className="text-sm text-[var(--color-ink-secondary)]">
                      {trackStatus.error}
                    </p>
                  </div>
                )}

                {isDone && (
                  <div className="p-4 rounded-xl bg-success-soft border border-success/30 flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-[var(--color-ink-secondary)]">
                      Tài liệu đã sẵn sàng để duyệt và xuất bản. Bạn có thể đóng
                      cửa sổ này và tiếp tục từ danh sách tài liệu.
                    </p>
                  </div>
                )}
              </div>
            )}

            {trackError && (
              <div className="text-sm text-danger flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />
                {trackError}
              </div>
            )}
          </div>

          <div className="px-6 py-4 border-t border-[var(--color-border)] flex justify-end">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 rounded-lg bg-[var(--color-surface-muted)] text-[var(--color-ink-primary)] text-sm font-medium hover:bg-[var(--color-border)] transition-colors"
            >
              {isTerminal ? "Đóng" : "Đóng (tiếp tục xử lý nền)"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Form view ────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg shadow-[var(--shadow-elevated)] max-h-[90vh] overflow-hidden flex flex-col">
        <div className="px-6 py-5 border-b border-[var(--color-border)] flex items-center justify-between">
          <h2 className="text-lg font-semibold text-[var(--color-ink-primary)]">
            Upload tài liệu mới
          </h2>
          <button
            type="button"
            onClick={handleClose}
            className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
          >
            <X className="w-4 h-4 text-[var(--color-ink-tertiary)]" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto">
          {/* File picker */}
          <div>
            <label className="block text-sm font-medium text-[var(--color-ink-primary)] mb-1.5">
              File PDF <span className="text-brand-600">*</span>
            </label>
            <div className="relative">
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={handleFileChange}
                className="block w-full text-sm text-[var(--color-ink-secondary)]
                           file:mr-3 file:py-1.5 file:px-3 file:rounded-lg
                           file:border-0 file:bg-brand-50 file:text-brand-700
                           file:font-medium file:cursor-pointer hover:file:bg-brand-100
                           cursor-pointer border border-[var(--color-border)] rounded-lg
                           bg-white"
              />
            </div>
            {file && (
              <div className="mt-2 p-3 bg-[var(--color-surface-muted)] rounded-xl border border-[var(--color-border)]">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm text-[var(--color-ink-secondary)] truncate flex-1">
                    {file.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => file && runPreview(file)}
                    disabled={isPreviewing}
                    className="text-xs px-2.5 py-1 rounded-md border border-[var(--color-border)] hover:bg-white transition-colors disabled:opacity-50 inline-flex items-center gap-1"
                  >
                    {isPreviewing && <Loader2 className="w-3 h-3 animate-spin" />}
                    {isPreviewing ? "Đang phân tích" : "Preview lại"}
                  </button>
                </div>
                {isPreviewing && (
                  <div className="mt-2 flex items-center gap-2 text-[var(--color-ink-secondary)] text-xs">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Đang trích xuất metadata từ nội dung...
                  </div>
                )}
                {previewError && (
                  <div className="mt-2 flex items-center gap-2 text-danger text-xs">
                    <AlertTriangle className="w-3 h-3" />
                    {previewError}
                  </div>
                )}
                {preview && (
                  <div className="mt-3 space-y-2">
                    <p className="text-[11px] uppercase tracking-wide font-medium text-[var(--color-ink-tertiary)]">
                      Metadata sẽ được backend tự suy ra
                    </p>
                    <div className="space-y-1.5">
                      <PreviewRow label="Số hiệu">
                        {preview.document_number || <span className="italic text-[var(--color-ink-tertiary)]">chưa xác định</span>}
                      </PreviewRow>
                      <PreviewRow label="Tiêu đề">
                        {preview.title || <span className="italic text-[var(--color-ink-tertiary)]">chưa xác định</span>}
                      </PreviewRow>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <ConfidenceBadge
                        level={preview.document_number_confidence}
                        label={`Số hiệu ${Math.round(preview.document_number_confidence * 100)}%`}
                      />
                      <ConfidenceBadge
                        level={preview.title_confidence}
                        label={`Tiêu đề ${Math.round(preview.title_confidence * 100)}%`}
                      />
                      {preview.needs_human_review && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-warning-soft text-warning text-xs font-medium">
                          <AlertTriangle className="w-3 h-3" />
                          Cần xác nhận
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <p className="text-xs text-[var(--color-ink-tertiary)] -mt-1">
            Backend sẽ tự động suy ra số hiệu, tiêu đề, cơ quan ban hành và
            phòng ban từ nội dung file.
          </p>

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 px-4 py-2.5 rounded-lg border border-[var(--color-border)] text-[var(--color-ink-primary)] text-sm font-medium hover:bg-[var(--color-surface-muted)] transition-colors"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !file}
              className="flex-1 px-4 py-2.5 rounded-lg bg-gradient-to-br from-brand-600 to-brand-700 text-white text-sm font-medium hover:from-brand-700 hover:to-brand-700 transition-colors disabled:opacity-50 inline-flex items-center justify-center gap-2 shadow-sm"
            >
              {isSubmitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              Upload
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PreviewRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="text-[11px] uppercase tracking-wide font-medium text-[var(--color-ink-tertiary)] w-20 flex-shrink-0">
        {label}
      </span>
      <span className="text-[var(--color-ink-primary)] break-words">{children}</span>
    </div>
  );
}
