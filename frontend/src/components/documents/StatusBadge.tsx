import { cn } from "@/lib/cn";

type Tone = "info" | "warning" | "success" | "danger" | "neutral" | "violet" | "brand";

const TONE_CLASSES: Record<Tone, string> = {
  info: "bg-info-soft text-info",
  warning: "bg-warning-soft text-warning",
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
  neutral: "bg-[var(--color-surface-muted)] text-[var(--color-ink-secondary)]",
  violet: "bg-violet-soft text-violet",
  brand: "bg-brand-50 text-brand-700",
};

const DOT_TONE: Record<Tone, string> = {
  info: "bg-info",
  warning: "bg-warning",
  success: "bg-success",
  danger: "bg-danger",
  neutral: "bg-[var(--color-ink-tertiary)]",
  violet: "bg-violet",
  brand: "bg-brand-500",
};

interface BaseProps {
  label: string;
  pulsing?: boolean;
  className?: string;
}

export function Pill({ tone, label, pulsing = false, className }: BaseProps & { tone: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {pulsing ? (
        <span className="relative flex h-2 w-2">
          <span
            className={cn(
              "absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping",
              DOT_TONE[tone],
            )}
          />
          <span className={cn("relative inline-flex h-2 w-2 rounded-full", DOT_TONE[tone])} />
        </span>
      ) : (
        <span className={cn("h-1.5 w-1.5 rounded-full", DOT_TONE[tone])} />
      )}
      {label}
    </span>
  );
}

// ─── Processing status ───────────────────────────────────────────────────────

const PROCESSING_CONFIG: Record<string, { label: string; tone: Tone; pulse: boolean }> = {
  queued: { label: "Đã tiếp nhận", tone: "info", pulse: true },
  received: { label: "Đã nhận", tone: "info", pulse: true },
  quarantined: { label: "Cách ly", tone: "warning", pulse: false },
  parsing: { label: "Đang xử lý", tone: "info", pulse: true },
  parsed: { label: "Đã phân tích", tone: "brand", pulse: false },
  review_required: { label: "Chờ duyệt", tone: "warning", pulse: false },
  pending_review: { label: "Chờ xem xét", tone: "warning", pulse: false },
  pending_approval: { label: "Chờ duyệt cuối", tone: "warning", pulse: false },
  approved: { label: "Đã duyệt", tone: "success", pulse: false },
  rejected: { label: "Đã từ chối", tone: "danger", pulse: false },
  indexed: { label: "Đã tạo vector", tone: "violet", pulse: false },
  published: { label: "Đã xuất bản", tone: "success", pulse: false },
  failed: { label: "Thất bại", tone: "danger", pulse: false },
};

export function ProcessingStatusBadge({
  status,
  className,
}: {
  status: string | null | undefined;
  className?: string;
}) {
  const cfg = status ? PROCESSING_CONFIG[status] : null;
  if (!cfg) {
    return <Pill tone="neutral" label={status ?? "—"} className={className} />;
  }
  return (
    <Pill
      tone={cfg.tone}
      label={cfg.label}
      pulsing={cfg.pulse}
      className={className}
    />
  );
}

// ─── Legal status ────────────────────────────────────────────────────────────

const LEGAL_CONFIG: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Bản nháp", tone: "neutral" },
  scheduled: { label: "Sắp có hiệu lực", tone: "brand" },
  effective: { label: "Có hiệu lực", tone: "success" },
  superseded: { label: "Hết hiệu lực", tone: "neutral" },
  expired: { label: "Hết hạn", tone: "warning" },
  revoked: { label: "Đã thu hồi", tone: "danger" },
};

export function LegalStatusBadge({
  status,
  className,
}: {
  status: string | null | undefined;
  className?: string;
}) {
  const cfg = status ? LEGAL_CONFIG[status] : null;
  if (!cfg) {
    return <Pill tone="neutral" label={status ?? "—"} className={className} />;
  }
  return <Pill tone={cfg.tone} label={cfg.label} className={className} />;
}

// ─── Confidence badge (for chat + upload preview) ───────────────────────────

export function ConfidenceBadge({
  level,
  label,
}: {
  level: "high" | "medium" | "low" | number;
  label?: string;
}) {
  let tone: Tone = "neutral";
  let labelText: string;
  if (typeof level === "number") {
    tone = level >= 0.85 ? "success" : level >= 0.5 ? "warning" : "danger";
    labelText = label ?? String(level);
  } else {
    tone = level === "high" ? "success" : level === "medium" ? "warning" : "danger";
    labelText = label ?? level;
  }
  return <Pill tone={tone} label={labelText} />;
}
