import Link from "next/link";

import type { RecentSearch } from "../../types/home";
import { RecentSearchItem } from "./RecentSearchItem";
import styles from "./RecentSearchesSection.module.css";

export type RecentSearchesSectionProps = {
  searches: RecentSearch[];
  historyHref?: string;
  emptyMessage?: string;
};

export function RecentSearchesSection({
  searches,
  historyHref = "/history",
  emptyMessage = "Chưa có lượt tra cứu nào được ghi nhận.",
}: RecentSearchesSectionProps) {
  const showEmpty = searches.length === 0;
  return (
    <section
      className={styles.section}
      aria-labelledby="recent-searches-title"
    >
      <div className={styles.heading}>
        <h2 id="recent-searches-title">Tra cứu gần đây</h2>
        <Link href={historyHref}>Xem tất cả lịch sử →</Link>
      </div>
      {showEmpty ? (
        <p className={styles.placeholder}>{emptyMessage}</p>
      ) : (
        <ul className={styles.list}>
          {searches.map((search) => (
            <RecentSearchItem key={search.id} item={search} />
          ))}
        </ul>
      )}
    </section>
  );
}