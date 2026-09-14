import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  Clock3,
  FileCheck2,
  LibraryBig,
  LockKeyhole,
  MessagesSquare,
  ShieldCheck,
} from "lucide-react";

import styles from "./PolicyMateStory.module.css";
import { MotionReveal } from "../motion";
import { InstitutionalCarousel } from "./InstitutionalCarousel";

const capabilities = [
  { icon: BookOpenCheck, title: "Trả lời có trích dẫn", description: "Mỗi kết luận được đặt cạnh số hiệu, điều khoản và trang nguồn để người dùng có thể mở văn bản kiểm chứng.", fact: "Mục tiêu độ chính xác trích dẫn ≥85%" },
  { icon: Clock3, title: "Theo dõi phiên bản & hiệu lực", description: "Cảnh báo khi văn bản có phiên bản mới hoặc đã hết hiệu lực, giảm nguy cơ áp dụng nhầm quy định cũ.", fact: "Có cảnh báo thay đổi phiên bản" },
  { icon: LockKeyhole, title: "Phân quyền theo vai trò", description: "Phạm vi tra cứu được kiểm soát theo người dùng và đơn vị, phù hợp với kho công khai lẫn tài liệu nội bộ.", fact: "Mục tiêu hỗ trợ ≥2 vai trò" },
];

const assuranceItems = [
  { icon: FileCheck2, title: "Đánh giá chất lượng bằng RAGAS", description: "Theo dõi faithfulness và citation accuracy với ngưỡng mục tiêu từ 85% trở lên." },
  { icon: LibraryBig, title: "Quản lý tài liệu có RBAC", description: "Kho văn bản tách quyền người tra cứu và người quản trị tài liệu, không hiển thị vượt thẩm quyền." },
  { icon: ShieldCheck, title: "Guardrails và kiểm tra quyền", description: "Câu hỏi, nguồn trích dẫn và thao tác công cụ được kiểm soát trước khi trả kết quả cho người dùng." },
];

export function PolicyMateStory() {
  return (
    <div className={styles.story}>
      <MotionReveal distance={28}><section className={styles.showcase} aria-labelledby="showcase-title">
        <div className={styles.showcaseCopy}>
          <h2 id="showcase-title">Tra cứu bằng AI, nhưng quyết định dựa trên văn bản.</h2>
          <p>PolicyMate giúp cán bộ, giảng viên và sinh viên đi từ câu hỏi tự nhiên đến đúng quy định, đúng phiên bản và đúng phạm vi được phép truy cập.</p>
          <div className={styles.actions}>
            <Link className={styles.primaryAction} href="/login"><ArrowRight size={17} /> Bắt đầu tra cứu</Link>
            <Link className={styles.secondaryAction} href="/documents"><LibraryBig size={17} /> Mở thư viện</Link>
          </div>
        </div>
        <div className={styles.showcaseMedia}>
          <InstitutionalCarousel />
          <div className={styles.answerDemo}>
            <span className={styles.demoAvatar}><Image src="/images/policymate-mascot.jpg" width={44} height={44} alt="Mascot PolicyMate" /></span>
            <div>
              <strong>PolicyMate AI <i /></strong>
              <p>Kết quả hiển thị kèm điều khoản, số trang và trạng thái hiệu lực để đối chiếu.</p>
              <span><BadgeCheck size={15} /> Mẫu câu trả lời có căn cứ</span>
            </div>
          </div>
        </div>
      </section></MotionReveal>

      <MotionReveal><section className={styles.capabilitySection} aria-labelledby="capabilities-title">
        <header>
          <h2 id="capabilities-title">Ba lớp tin cậy trong một lần tra cứu</h2>
          <p>Không chỉ tìm nội dung gần đúng: hệ thống còn giữ lại nguồn, phiên bản và quyền truy cập cần thiết để bạn sử dụng kết quả có trách nhiệm.</p>
        </header>
        <div className={styles.capabilityGrid}>
          {capabilities.map(({ icon: Icon, title, description, fact }) => (
            <article key={title} className={styles.capabilityCard}>
              <span className={styles.capabilityIcon}><Icon size={22} /></span>
              <h3>{title}</h3>
              <p>{description}</p>
              <div className={styles.capabilityFact}><BadgeCheck size={16} /><strong>{fact}</strong></div>
            </article>
          ))}
        </div>
      </section></MotionReveal>

      <MotionReveal><section className={styles.assurance} aria-labelledby="assurance-title">
        <div className={styles.metricsBoard} aria-label="Mục tiêu đánh giá hệ thống">
          <div className={styles.boardHeader}><span><i /><i /><i /></span><strong>Khung đánh giá PolicyMate</strong></div>
          <div className={styles.metricPair}>
            <article><span>Độ chính xác trích dẫn</span><strong>≥85%</strong><small><BadgeCheck size={14} /> Mục tiêu bộ kiểm thử</small></article>
            <article><span>Thời gian tìm thông tin</span><strong>≥50%</strong><small><Clock3 size={14} /> Mục tiêu giảm thời gian</small></article>
          </div>
          <div className={styles.measureList}>
            <div><span>RAGAS: faithfulness & citation accuracy</span><strong>Ngưỡng ≥85%</strong><i className={styles.measure85} /></div>
            <div><span>Tối ưu quy trình tìm kiếm thông tin</span><strong>Giảm ≥50%</strong><i className={styles.measure50} /></div>
            <div className={styles.statusRow}><span>Phiên bản, hiệu lực và quyền truy cập</span><strong>Trạng thái được theo dõi</strong></div>
          </div>
        </div>
        <div className={styles.assuranceCopy}>
          <h2 id="assurance-title">Đo được chất lượng, nhìn rõ rủi ro.</h2>
          <p>Các mục tiêu của đề tài được đưa vào giao diện như tiêu chí đánh giá, giúp người dùng và quản trị viên hiểu hệ thống đang tối ưu điều gì.</p>
          <ul>
            {assuranceItems.map(({ icon: Icon, title, description }) => (
              <li key={title}><span><Icon size={18} /></span><div><strong>{title}</strong><p>{description}</p></div></li>
            ))}
          </ul>
        </div>
      </section></MotionReveal>

      <MotionReveal><section className={styles.cta} aria-labelledby="cta-title">
        <MessagesSquare size={29} aria-hidden="true" />
        <h2 id="cta-title">Bắt đầu từ một câu hỏi, kết thúc bằng một căn cứ rõ ràng.</h2>
        <p>Tra cứu quy định, mở văn bản nguồn và kiểm tra hiệu lực trong cùng một luồng làm việc.</p>
        <div className={styles.ctaActions}>
          <Link href="/login">Đăng nhập để tra cứu <ArrowRight size={17} /></Link>
          <Link href="/documents">Duyệt kho văn bản</Link>
        </div>
        <ul aria-label="Cam kết trải nghiệm">
          <li><BadgeCheck size={15} /> Trích dẫn có thể mở</li>
          <li><BadgeCheck size={15} /> Theo dõi hiệu lực</li>
          <li><BadgeCheck size={15} /> Kiểm soát theo vai trò</li>
        </ul>
      </section></MotionReveal>

      <footer className={styles.footer}>
        <div className={styles.footerBrand}>
          <div><span><BookOpenCheck size={20} /></span><strong>PolicyMate <b>AI</b></strong></div>
          <p>Trợ lý tra cứu quy định, quy chế có nguồn dành cho môi trường đại học.</p>
        </div>
        <nav aria-label="Tính năng PolicyMate"><strong>Sản phẩm</strong><Link href="/documents">Thư viện văn bản</Link><Link href="/saved">Văn bản đã lưu</Link></nav>
        <nav aria-label="Hỗ trợ PolicyMate"><strong>Hỗ trợ sử dụng</strong><Link href="/history">Lịch sử tra cứu</Link><Link href="/notifications">Thông báo hiệu lực</Link><Link href="/profile">Tài khoản cá nhân</Link></nav>
        <div className={styles.footerTrust}><strong>Nguyên tắc</strong><p><ShieldCheck size={17} /> AI hỗ trợ tra cứu; người dùng kiểm tra nguồn trước khi áp dụng.</p></div>
        <div className={styles.footerBottom}><span>PolicyMate AI · Institutional policy assistant</span><span>Có nguồn · Có phiên bản · Có kiểm soát</span></div>
      </footer>
    </div>
  );
}
