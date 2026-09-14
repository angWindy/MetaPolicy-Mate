import type { PolicyTopic } from "../../types/home";
import { TopicCard } from "./TopicCard";
import styles from "./TopicsSection.module.css";

export type TopicsSectionProps = {
  topics: PolicyTopic[];
  title?: string;
};

export function TopicsSection({
  topics,
  title = "Lĩnh vực nghiệp vụ",
}: TopicsSectionProps) {
  if (topics.length === 0) return null;

  return (
    <section className={styles.section} aria-labelledby="policy-topics-title">
      <h2 id="policy-topics-title">{title}</h2>
      <div className={styles.grid}>
        {topics.map((topic) => (
          <TopicCard
            key={topic.id}
            href={topic.href}
            title={topic.title}
            description={topic.description}
            icon={topic.icon}
          />
        ))}
      </div>
    </section>
  );
}
