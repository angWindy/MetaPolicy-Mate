import Link from "next/link";

import styles from "./UserProfileCard.module.css";

export type UserProfileCardUser = {
  name: string;
  role: string;
  avatarUrl?: string;
  studentId?: string;
  department?: string;
  /**
   * True when the viewer has a valid JWT session. When this is explicitly
   * `false` the layout components swap the profile card for a login CTA
   * and hide authenticated-only navigation items. `undefined` is treated
   * as "unknown / treat as authenticated" to preserve existing call sites.
   */
  isAuthenticated?: boolean;
};

export type UserProfileCardProps = {
  user: UserProfileCardUser;
  href?: string;
  active?: boolean;
  onNavigate?: () => void;
};

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

export function UserProfileCard({
  user,
  href = "/profile",
  active = false,
  onNavigate,
}: UserProfileCardProps) {
  return (
    <Link
      className={`${styles.card} ${active ? styles.active : ""}`.trim()}
      href={href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
    >
      <span className={styles.avatar}>
        {user.avatarUrl ? (
          // Keep this component independent of deployment-specific image hosts.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={user.avatarUrl} alt="" />
        ) : (
          initials(user.name)
        )}
      </span>
      <span className={styles.details}>
        <strong>{user.name}</strong>
        <span>{user.role}</span>
      </span>
    </Link>
  );
}
