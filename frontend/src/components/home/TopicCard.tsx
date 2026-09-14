import Link from "next/link";
import {
  BedDouble,
  ClipboardCheck,
  GraduationCap,
  Landmark,
  PauseCircle,
  WalletCards,
  type LucideIcon,
} from "lucide-react";

import styles from "./TopicCard.module.css";

export type TopicIconKey =
  | "graduation"
  | "wallet"
  | "exam"
  | "conduct"
  | "leave"
  | "dormitory";

export type TopicCardProps = {
  href: string;
  title: string;
  description: string;
  icon?: TopicIconKey | string;
};

const ICONS: Record<TopicIconKey, LucideIcon> = {
  graduation: GraduationCap,
  wallet: WalletCards,
  exam: ClipboardCheck,
  conduct: Landmark,
  leave: PauseCircle,
  dormitory: BedDouble,
};

export function TopicCard({
  href,
  title,
  description,
  icon,
}: TopicCardProps) {
  const Icon: LucideIcon = (icon && ICONS[icon as TopicIconKey]) || GraduationCap;
  return (
    <Link className={styles.card} href={href}>
      <span className={styles.icon} aria-hidden="true">
        <Icon size={19} />
      </span>
      <span className={styles.content}>
        <strong>{title}</strong>
        <span>{description}</span>
      </span>
      <span className={styles.arrow} aria-hidden="true">
        ›
      </span>
    </Link>
  );
}
