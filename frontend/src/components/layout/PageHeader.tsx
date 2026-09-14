import type { ReactNode } from "react";
import styles from "./PageHeader.module.css";
export type PageHeaderProps = { title: string; description?: string; eyebrow?: string; actions?: ReactNode; className?: string };
export function PageHeader({ title, description, eyebrow, actions, className = "" }: PageHeaderProps) { return <header className={`${styles.header} ${className}`.trim()}><div className={styles.content}>{eyebrow && <p className={styles.eyebrow}>{eyebrow}</p>}<h1 className={styles.title}>{title}</h1>{description && <p className={styles.description}>{description}</p>}</div>{actions && <div className={styles.actions}>{actions}</div>}</header>; }
