import styles from "./Avatar.module.css";

export type AvatarProps = { name: string; src?: string; size?: "small" | "medium" | "large"; className?: string };

function getInitials(name: string) {
  return name.trim().split(/\s+/).slice(-2).map((part) => part.charAt(0).toUpperCase()).join("");
}

export function Avatar({ name, src, size = "medium", className = "" }: AvatarProps) {
  return (
    <span className={`${styles.avatar} ${styles[size]} ${className}`.trim()} aria-label={name} role="img">
      {src ? (
        // Avatar hosts are configured by the consuming application.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" />
      ) : getInitials(name)}
    </span>
  );
}
