"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, FileText, Home } from "lucide-react";

const navItems = [
  { href: "/", label: "Trang chủ", icon: Home },
  { href: "/chat", label: "Tra cứu", icon: MessageSquare },
  { href: "/documents", label: "Tài liệu", icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();
  // Initialise to true so the SSR snapshot matches the first client render
  // and we never need a follow-up effect to flip a "mounted" flag.
  const [mounted] = useState(() => true);

  return (
    <aside className="w-64 flex-shrink-0 bg-white border-r border-[var(--color-border)] flex flex-col">
      <div className="px-6 py-5 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 grid place-items-center text-white font-bold text-base shadow-sm">
            P
          </div>
          <div className="leading-tight">
            <p className="font-semibold text-[var(--color-ink-primary)] text-[15px]">
              P234 RAG
            </p>
            <p className="text-[11px] text-[var(--color-ink-tertiary)] mt-0.5">
              Hệ thống tra cứu
            </p>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = mounted ? pathname === item.href : false;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  data-active={isActive}
                  className="group flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors
                             text-[var(--color-ink-secondary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-ink-primary)]
                             data-[active=true]:bg-brand-50 data-[active=true]:text-brand-700 data-[active=true]:font-medium"
                >
                  <Icon
                    className="w-4 h-4 transition-colors
                               text-[var(--color-ink-tertiary)] group-hover:text-[var(--color-ink-primary)]
                               group-data-[active=true]:text-brand-600"
                  />
                  <span>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="px-6 py-4 border-t border-[var(--color-border)]">
        <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-[var(--color-surface-muted)] text-[11px] text-[var(--color-ink-tertiary)]">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)]" />
          MVP v1.0
        </div>
      </div>
    </aside>
  );
}
