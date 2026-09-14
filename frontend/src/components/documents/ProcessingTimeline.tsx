"use client";

import { CheckCircle2, FileSearch, Inbox, Loader2, Scissors } from "lucide-react";
import { cn } from "@/lib/cn";
import type { LucideIcon } from "lucide-react";

type StepState = "done" | "active" | "pending";

interface Step {
  id: string;
  label: string;
  icon: LucideIcon;
}

const STEPS: Step[] = [
  { id: "queued", label: "Đã tiếp nhận", icon: Inbox },
  { id: "parsing", label: "Đang phân tích", icon: FileSearch },
  { id: "chunking", label: "Đang tạo chunks", icon: Scissors },
  { id: "review_required", label: "Chờ duyệt", icon: CheckCircle2 },
];

const TERMINAL_STATUSES = new Set([
  "review_required",
  "approved",
  "indexed",
  "published",
  "failed",
]);

function stateForIndex(index: number, current: number, status: string | null): StepState {
  if (status === "failed") {
    return index < current ? "done" : index === current ? "pending" : "pending";
  }
  if (status && TERMINAL_STATUSES.has(status) && index === STEPS.length - 1) {
    return "done";
  }
  if (index < current) return "done";
  if (index === current) return "active";
  return "pending";
}

export function ProcessingTimeline({
  status,
  failed,
}: {
  status: string | null | undefined;
  failed?: boolean;
}) {
  const idx = STEPS.findIndex((s) => s.id === status);
  const safeIdx = idx === -1 ? 0 : idx;

  return (
    <div className="w-full">
      <ol className="grid grid-cols-4 gap-2">
        {STEPS.map((step, index) => {
          const state = failed && index === safeIdx
            ? "pending"
            : stateForIndex(index, safeIdx, status ?? null);
          const Icon = step.icon;
          const isLast = index === STEPS.length - 1;

          return (
            <li key={step.id} className="relative flex flex-col items-center text-center">
              <div className="relative z-10 mb-2">
                <div
                  className={cn(
                    "w-10 h-10 rounded-xl grid place-items-center transition-all",
                    state === "active" &&
                      "bg-brand-50 border-2 border-brand-500 text-brand-700 shadow-[0_0_0_4px_var(--color-brand-50)]",
                    state === "done" && "bg-success-soft text-success",
                    state === "pending" &&
                      "bg-[var(--color-surface-muted)] text-[var(--color-ink-tertiary)]",
                  )}
                >
                  {state === "active" ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Icon className="w-4 h-4" />
                  )}
                </div>
              </div>
              <p
                className={cn(
                  "text-xs font-medium leading-tight",
                  state === "active" && "text-brand-700",
                  state === "done" && "text-success",
                  state === "pending" && "text-[var(--color-ink-tertiary)]",
                )}
              >
                {step.label}
              </p>
              {!isLast && (
                <div className="absolute top-5 left-1/2 w-full h-px -z-0">
                  <div
                    className={cn(
                      "h-px transition-all duration-500",
                      index < safeIdx
                        ? "bg-success"
                        : "bg-[var(--color-border)]",
                    )}
                    style={{ width: "100%" }}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
