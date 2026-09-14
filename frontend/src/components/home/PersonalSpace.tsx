import { ArrowRight, Bookmark, Clock3, Search } from "lucide-react";
import Link from "next/link";

import styles from "./PersonalSpace.module.css";

export function PersonalSpace() {
  return (
    <aside className={styles.space} aria-labelledby="personal-space-title">
      <h2 id="personal-space-title">Không gian cá nhân</h2>
      <div className={styles.group}>
        <h3><Clock3 size={16} aria-hidden="true" /> Tiếp tục tra cứu</h3>
        <Link href="/history"><Search size={15} aria-hidden="true" /><span><strong>Lịch sử câu hỏi</strong><small>Xem lại các nội dung đã tra cứu</small></span><ArrowRight size={14} aria-hidden="true" /></Link>
      </div>
      <div className={styles.group}>
        <h3><Bookmark size={16} aria-hidden="true" /> Đã lưu</h3>
        <Link href="/saved"><Bookmark size={15} aria-hidden="true" /><span><strong>Văn bản quan tâm</strong><small>Mở danh sách văn bản đã đánh dấu</small></span><ArrowRight size={14} aria-hidden="true" /></Link>
      </div>
    </aside>
  );
}
