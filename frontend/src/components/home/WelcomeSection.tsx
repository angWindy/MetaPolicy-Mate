import styles from "./WelcomeSection.module.css";

export type WelcomeSectionProps = { userName: string; greeting?: string; description?: string; supportingText?: string };

export function WelcomeSection({ userName, greeting = "Tra cứu đúng quy định.", description = "Làm việc có căn cứ.", supportingText = "Hỏi bằng ngôn ngữ tự nhiên, tìm quy chế phù hợp và đối chiếu trực tiếp với văn bản nguồn." }: WelcomeSectionProps) {
  return (
    <section className={styles.section} aria-labelledby="welcome-title">
      <div className={styles.copy}>
        <p className={styles.context}>Không gian tra cứu của {userName}</p>
        <h1 id="welcome-title" className={styles.title}>{greeting}<br /><span>{description}</span></h1>
        <p className={styles.supportingText}>{supportingText}</p>
      </div>
    </section>
  );
}
