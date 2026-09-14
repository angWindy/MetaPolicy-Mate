import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

type Accent = "brand" | "violet" | "success";

const ACCENT: Record<Accent, { bg: string; text: string; icon: string }> = {
  brand: {
    bg: "bg-brand-50",
    text: "text-brand-700",
    icon: "from-brand-500 to-brand-700",
  },
  violet: {
    bg: "bg-violet-soft",
    text: "text-violet",
    icon: "from-violet to-violet",
  },
  success: {
    bg: "bg-success-soft",
    text: "text-success",
    icon: "from-success to-success",
  },
};

export function StatCard({
  icon: Icon,
  label,
  value,
  accent = "brand",
  hint,
}: {
  icon: LucideIcon;
  label: string;
  value: number | string;
  accent?: Accent;
  hint?: string;
}) {
  const cfg = ACCENT[accent];
  return (
    <div
      className={cn(
        "bg-white rounded-2xl border border-[var(--color-border)] p-6 shadow-[var(--shadow-card)]",
        "transition-all hover:shadow-[var(--shadow-card-hover)] hover:border-[var(--color-border-strong)]",
      )}
    >
      <div className="flex items-start justify-between mb-4">
        <div
          className={cn(
            "w-11 h-11 rounded-xl grid place-items-center",
            cfg.bg,
            cfg.text,
          )}
        >
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <p className="text-3xl font-semibold tracking-tight text-[var(--color-ink-primary)]">
        {value}
      </p>
      <p className="text-sm text-[var(--color-ink-secondary)] mt-1">{label}</p>
      {hint && (
        <p className="text-xs text-[var(--color-ink-tertiary)] mt-2">{hint}</p>
      )}
    </div>
  );
}
