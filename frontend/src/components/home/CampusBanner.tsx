import { ArrowRight, BadgeCheck, BookOpenCheck, Clock3 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import styles from "./CampusBanner.module.css";

const qualities = [
  { icon: BookOpenCheck, label: "Nguồn chính thức" },
  { icon: BadgeCheck, label: "Có căn cứ trích dẫn" },
  { icon: Clock3, label: "Theo dõi hiệu lực" },
];

export function CampusBanner() {
  return (
    <section className={styles.banner} aria-labelledby="campus-banner-title">
      <Image
        className={styles.image}
        src="/images/institutional/hust-campus-banner.jpg"
        alt="Tòa nhà Tạ Quang Bửu tại Đại học Bách khoa Hà Nội"
        fill
        loading="eager"
        sizes="(max-width: 900px) 100vw, 1360px"
      />
      <div className={styles.veil} aria-hidden="true" />
      <div className={styles.content}>
        <p>Đồng hành cùng người học</p>
        <h2 id="campus-banner-title">Một nguồn tin cậy cho hành trình học tập.</h2>
        <span>Tra cứu quy định, kiểm tra văn bản gốc và theo dõi hiệu lực trong cùng một không gian.</span>
        <Link href="/documents">Khám phá thư viện <ArrowRight size={16} aria-hidden="true" /></Link>
      </div>
      <ul className={styles.qualities} aria-label="Giá trị của kho tri thức">
        {qualities.map(({ icon: Icon, label }) => <li key={label}><Icon size={17} aria-hidden="true" /><span>{label}</span></li>)}
      </ul>
    </section>
  );
}
