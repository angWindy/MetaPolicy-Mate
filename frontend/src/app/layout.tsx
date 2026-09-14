import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "PolicyMate AI",
    template: "%s · PolicyMate AI",
  },
  description:
    "Không gian tra cứu quy chế học thuật đáng tin cậy — câu trả lời có căn cứ, tài liệu chính thức và quản trị có kiểm soát.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
