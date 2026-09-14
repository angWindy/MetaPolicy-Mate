"use client";

import { useState } from "react";
import { Check, Loader2, Plus, Trash2, Upload } from "lucide-react";
import {
  approveVersion,
  deleteVersion,
  indexVersion,
  publishVersion,
} from "@/lib/api";
import type { DocumentVersion } from "@/lib/types";
import { LegalStatusBadge, ProcessingStatusBadge } from "./StatusBadge";

interface ActionDef {
  label: string;
  icon: typeof Check;
  tone: "success" | "violet" | "brand";
  handler: () => Promise<unknown>;
}

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("vi-VN");
}

export function VersionRow({
  version,
  onRefresh,
}: {
  version: DocumentVersion;
  onRefresh: () => void;
}) {
  const [isLoading, setIsLoading] = useState<Error | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const actions: ActionDef[] = [];
  if (version.processing_status === "review_required") {
    actions.push({
      label: "Duyệt",
      icon: Check,
      tone: "success",
      handler: () => approveVersion(version.id),
    });
  }
  if (version.processing_status === "approved") {
    actions.push({
      label: "Tạo vector",
      icon: Plus,
      tone: "violet",
      handler: () => indexVersion(version.id),
    });
  }
  if (version.processing_status === "indexed") {
    actions.push({
      label: "Xuất bản",
      icon: Upload,
      tone: "brand",
      handler: () => publishVersion(version.id),
    });
  }

  const handleAction = async (action: ActionDef) => {
    setBusyAction(action.label);
    setIsLoading(null);
    try {
      await action.handler();
      onRefresh();
    } catch (error) {
      setIsLoading(error instanceof Error ? error : new Error("Unknown error"));
    } finally {
      setBusyAction(null);
    }
  };

  const handleDelete = async () => {
    setBusyAction("Xóa");
    setIsLoading(null);
    try {
      await deleteVersion(version.id);
      onRefresh();
    } catch (error) {
      setIsLoading(error instanceof Error ? error : new Error("Unknown error"));
    } finally {
      setBusyAction(null);
      setConfirmingDelete(false);
    }
  };

  const actionToneClasses: Record<ActionDef["tone"], string> = {
    success: "bg-success-soft text-success hover:bg-success hover:text-white",
    violet: "bg-violet-soft text-violet hover:bg-violet hover:text-white",
    brand: "bg-brand-50 text-brand-700 hover:bg-brand-600 hover:text-white",
  };

  const isBusy = busyAction !== null;

  return (
    <div className="px-5 py-3.5 grid grid-cols-12 gap-3 items-center border-t border-[var(--color-border)] hover:bg-[var(--color-surface-muted)] transition-colors">
      <div className="col-span-3">
        <p className="font-medium text-[var(--color-ink-primary)] text-sm">
          Phiên bản {version.version_number}
        </p>
      </div>
      <div className="col-span-3">
        <ProcessingStatusBadge status={version.processing_status} />
      </div>
      <div className="col-span-2">
        <LegalStatusBadge status={version.legal_status} />
      </div>
      <div className="col-span-2 text-xs text-[var(--color-ink-secondary)] space-y-0.5">
        <p>
          <span className="text-[var(--color-ink-tertiary)]">Từ:</span>{" "}
          {fmtDate(version.effective_from)}
        </p>
        <p>
          <span className="text-[var(--color-ink-tertiary)]">Đến:</span>{" "}
          {fmtDate(version.effective_to)}
        </p>
      </div>
      <div className="col-span-2 flex items-center justify-end gap-2">
        {actions.map((action) => {
          const Icon = action.icon;
          const actionBusy = busyAction === action.label;
          return (
            <button
              key={action.label}
              type="button"
              onClick={() => handleAction(action)}
              disabled={isBusy}
              className={
                "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors disabled:opacity-50 " +
                actionToneClasses[action.tone]
              }
            >
              {actionBusy ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Icon className="w-3.5 h-3.5" />
              )}
              {action.label}
            </button>
          );
        })}

        {confirmingDelete ? (
          <>
            <button
              type="button"
              onClick={handleDelete}
              disabled={isBusy}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-danger-soft text-danger hover:bg-danger hover:text-white transition-colors disabled:opacity-50"
            >
              {busyAction === "Xóa" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              Xác nhận
            </button>
            <button
              type="button"
              onClick={() => setConfirmingDelete(false)}
              disabled={isBusy}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-[var(--color-surface-muted)] text-[var(--color-ink-secondary)] hover:bg-[var(--color-border)] transition-colors disabled:opacity-50"
            >
              Hủy
            </button>
          </>
        ) : version.processing_status === "failed" ? (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            disabled={isBusy}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-[var(--color-ink-tertiary)] hover:bg-danger-soft hover:text-danger transition-colors disabled:opacity-50"
            title="Xóa phiên bản"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        ) : null}
      </div>
      {isLoading && (
        <div className="col-span-12 -mt-1 flex items-center gap-1.5 text-xs text-danger">
          <span className="w-1 h-1 rounded-full bg-danger" />
          Lỗi: {isLoading.message}
        </div>
      )}
    </div>
  );
}