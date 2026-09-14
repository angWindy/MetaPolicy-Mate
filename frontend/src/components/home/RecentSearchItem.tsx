import Link from "next/link";

import type { RecentSearch } from "../../types/home";
import styles from "./RecentSearchItem.module.css";

export type RecentSearchItemProps = {
  item: RecentSearch;
};

export function RecentSearchItem({ item }: RecentSearchItemProps) {
  return (
    <li>
      <Link className={styles.item} href={item.href}>
        <span className={styles.clock} aria-hidden="true">
          ◷
        </span>
        <span className={styles.question}>{item.question}</span>
        {item.status && item.statusLabel && (
          <span className={`${styles.status} ${styles[item.status]}`}>
            {item.statusLabel}
          </span>
        )}
        <time dateTime={item.searchedAt}>{item.timeLabel}</time>
        <span className={styles.arrow} aria-hidden="true">
          →
        </span>
      </Link>
    </li>
  );
}
