import { BadgeCheck, BookOpenText, ExternalLink, Scale } from "lucide-react";
import Link from "next/link";

import styles from "./EvidencePreview.module.css";

export function EvidencePreview() {
  return (
    <aside className={styles.preview} aria-labelledby="evidence-preview-title">
      <div className={styles.heading}>
        <span><Scale size={19} aria-hidden="true" /></span>
        <div><h2 id="evidence-preview-title">Câu trả lời có căn cứ</h2><p>Xem trước cách PolicyMate trình bày kết quả</p></div>
      </div>
      <p className={styles.summary}>Nội dung được tóm tắt rõ ràng và đặt cạnh căn cứ nguồn để bạn kiểm tra trước khi sử dụng.</p>
      <div className={styles.source}>
        <BookOpenText size={18} aria-hidden="true" />
        <span><small>Nguồn đối chiếu</small><strong>Điều khoản, số trang và hiệu lực văn bản</strong></span>
        <BadgeCheck size={18} aria-label="Có nguồn kiểm chứng" />
      </div>
      <Link href="/documents">Khám phá thư viện văn bản <ExternalLink size={15} aria-hidden="true" /></Link>
    </aside>
  );
}
