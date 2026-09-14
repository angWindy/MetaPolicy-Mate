import { ArrowRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import styles from "./JourneyGuides.module.css";

const guides = [
  { image: "/images/institutional/graduation.jpg", alt: "Học viên trong lễ trao bằng", title: "Chuẩn bị tốt nghiệp", description: "Kiểm tra điều kiện, đối chiếu từng yêu cầu và chuẩn bị hồ sơ đúng quy định.", href: "/documents?q=tốt+nghiệp" },
  { image: "/images/institutional/legal-reference.jpg", alt: "Cân công lý và văn bản pháp lý", title: "Hiểu đúng quy chế", description: "Tra cứu điều khoản và văn bản gốc để hiểu đúng trước khi áp dụng.", href: "/ask?q=Giúp+tôi+tra+cứu+quy+chế" },
  { image: "/images/institutional/engineering-lab.jpg", alt: "Sinh viên học tập trong phòng thí nghiệm", title: "Học tập & nghiên cứu", description: "Tìm hướng dẫn về phòng thí nghiệm, nghiên cứu khoa học và các thủ tục liên quan.", href: "/documents?q=nghiên+cứu+khoa+học" },
];

export function JourneyGuides() {
  return (
    <section className={styles.section} aria-labelledby="journey-guides-title">
      <header><div><h2 id="journey-guides-title">Hỗ trợ theo từng chặng đường</h2><p>Tra cứu, hiểu đúng và thực hiện đúng theo quy định trong suốt hành trình học tập.</p></div><Link href="/documents">Xem tất cả hướng dẫn <ArrowRight size={15} aria-hidden="true" /></Link></header>
      <div className={styles.grid}>
        {guides.map((guide) => <article className={styles.guide} key={guide.title}><div className={styles.media}><Image src={guide.image} alt={guide.alt} fill sizes="(max-width: 700px) 100vw, (max-width: 1000px) 50vw, 33vw" /></div><div className={styles.copy}><h3>{guide.title}</h3><p>{guide.description}</p><Link href={guide.href}>Xem hướng dẫn <ArrowRight size={14} aria-hidden="true" /></Link></div></article>)}
      </div>
    </section>
  );
}
