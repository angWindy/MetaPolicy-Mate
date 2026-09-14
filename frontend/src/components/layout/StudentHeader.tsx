"use client";

import {
  Bell,
  BookOpenCheck,
  ChevronDown,
  LogOut,
  Menu,
  Search,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
  type Ref,
} from "react";

import { AUTH_REQUIRED } from "@/lib/authMode";
import { authService } from "@/services/authService";
import { notificationService } from "@/services/notificationService";
import { useCurrentUser } from "@/hooks/useCurrentUser";

import type { UserProfileCardUser } from "./UserProfileCard";
import styles from "./StudentHeader.module.css";

export type HeaderAccountItem = {
  href: string;
  label: string;
};

export type HeaderNavItem = {
  href: string;
  label: string;
  icon?: ReactNode;
};

export type StudentHeaderProps = {
  title: string;
  user: UserProfileCardUser;
  /**
   * True for user-facing pages — renders the brand chip instead of the
   * breadcrumb title. Admin pages pass `false`.
   */
  studentMode?: boolean;
  /**
   * When the layout already shows the brand in a left sidebar
   * (admin shell), pass `true` so the header doesn't duplicate it.
   */
  hideBrand?: boolean;
  /**
   * Optional explicit nav list. When omitted and `studentMode` is true,
   * the default `studentLinks` are used.
   */
  navItems?: HeaderNavItem[];
  showSearch?: boolean;
  searchPlaceholder?: string;
  notificationCount?: number;
  accountItems?: HeaderAccountItem[];
  onSearch?: (query: string) => void;
  onNotificationsClick?: () => void;
  onMenuClick?: () => void;
  menuOpen?: boolean;
  menuButtonRef?: Ref<HTMLButtonElement>;
};

const studentLinks: HeaderNavItem[] = [
  { href: "/student", label: "Trang chủ" },
  { href: "/documents", label: "Thư viện văn bản" },
  { href: "/history", label: "Lịch sử" },
  { href: "/saved", label: "Đã lưu" },
];

const defaultAccountItems: HeaderAccountItem[] = [
  { href: "/profile", label: "Hồ sơ cá nhân" },
  { href: "/logout", label: "Đăng xuất" },
];

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

/**
 * Resolve where the brand link should send the user.
 *
 * Order of precedence:
 *   1. Visitor currently on an `/admin/*` route → `/admin`
 *      (so clicking the brand from any admin sub-page lands back on
 *      the admin dashboard, even if the JWT role hasn't loaded yet).
 *   2. Authenticated ADMIN → `/admin`
 *   3. Authenticated USER  → `/student`
 *   4. Everyone else (anonymous / loading) → `/`
 */
function brandHrefFor(
  isAdminRoute: boolean,
  rawRole: string | null,
  isAuthenticated: boolean,
): string {
  if (isAdminRoute) return "/admin";
  if (isAuthenticated) {
    if ((rawRole ?? "").toUpperCase() === "ADMIN") return "/admin";
    if (isAuthenticated) return "/student";
  }
  return "/";
}

/**
 * Brand block: a single icon-as-button that takes the user back to
 * their role-appropriate home route (admin → /admin, user → /student).
 *
 * The textual "PolicyMate AI" caption next to the icon is *purely
 * decorative* — when the top bar gets tight (admin mode, narrow view,
 * many nav items) the caption auto-hides via CSS so the icon still
 * fits. The aria-label always carries the full destination phrase so
 * screen readers don't lose context when the caption is invisible.
 */
function BrandLink({
  isAdminRoute,
  rawRole,
  isAuthenticated,
  title,
  studentMode,
}: {
  isAdminRoute: boolean;
  rawRole: string | null;
  isAuthenticated: boolean;
  title: string;
  studentMode: boolean;
}) {
  const href = brandHrefFor(isAdminRoute, rawRole, isAuthenticated);
  const isAdminHome = href === "/admin";

  const destinationPhrase = isAdminHome
    ? "trang quản trị"
    : "không gian của bạn";

  const subLine = isAdminRoute
    ? title || "Không gian quản trị"
    : isAdminHome
      ? "Không gian quản trị"
      : "Không gian của bạn";

  return (
    <Link
      className={`${styles.studentBrand} ${
        isAdminRoute ? styles.brandAdmin : ""
      } ${studentMode ? "" : styles.brandWithSub}`}
      href={href}
      aria-label={`PolicyMate AI - Về ${destinationPhrase}`}
      title={destinationPhrase}
    >
      <span className={styles.brandIcon} aria-hidden="true">
        {isAdminHome ? <ShieldCheck size={20} /> : <BookOpenCheck size={20} />}
      </span>
      <span className={styles.brandText}>
        <strong className={styles.brandTitle}>
          PolicyMate <b>AI</b>
        </strong>
        {!studentMode && <small className={styles.brandSub}>{subLine}</small>}
      </span>
    </Link>
  );
}

export function StudentHeader({
  title,
  user,
  studentMode = false,
  hideBrand = false,
  navItems,
  showSearch = true,
  searchPlaceholder = "Tìm văn bản, số hiệu...",
  notificationCount = 0,
  accountItems = defaultAccountItems,
  onSearch,
  onNotificationsClick,
  onMenuClick,
  menuOpen = false,
  menuButtonRef,
}: StudentHeaderProps) {
  const router = useRouter();
  const pathname = usePathname();
  const currentUser = useCurrentUser();
  const displayName = user.name?.trim() || "Người dùng";
  const [liveUnread, setLiveUnread] = useState<number | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Close mobile drawer on route change
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setMobileNavOpen(false);
    }
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [mobileNavOpen]);

  useEffect(() => {
    // Only auto-fetch when caller did not pass an explicit count.
    if (notificationCount > 0) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await notificationService.unreadCount();
        if (!cancelled) setLiveUnread(res.unread_count);
      } catch {
        // silent — defaults to 0
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [notificationCount]);

  const effectiveCount = notificationCount || (liveUnread ?? 0);

  const resolvedNav: HeaderNavItem[] = navItems ?? (studentMode ? studentLinks : []);
  const showTopNav = resolvedNav.length > 0;

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const query = String(formData.get("query") ?? "").trim();
    if (!query) return;
    if (onSearch) onSearch(query);
    else router.push(`/documents?q=${encodeURIComponent(query)}`);
  }

  async function logout() {
    try {
      await authService.logout();
    } catch {
      // ignore — best effort
    }
    router.replace("/login");
  }

  return (
    <header
      className={`${styles.header} ${studentMode ? styles.studentHeader : ""}`.trim()}
    >
      <div className={styles.titleGroup}>
        <button
          ref={menuButtonRef}
          className={styles.menuButton}
          type="button"
          aria-label="Mở menu"
          aria-controls="topnav-drawer"
          aria-expanded={mobileNavOpen}
          onClick={() => {
            setMobileNavOpen((prev) => !prev);
            onMenuClick?.();
          }}
        >
          <Menu size={20} />
        </button>
        {hideBrand ? (
          studentMode ? (
            <h1 className={styles.title}>{title}</h1>
          ) : (
            <div>
              <span className={styles.breadcrumb}>PolicyMate AI</span>
              <h1 className={styles.title}>{title}</h1>
            </div>
          )
        ) : (
          <BrandLink
            isAdminRoute={pathname.startsWith("/admin")}
            rawRole={currentUser.rawRole}
            isAuthenticated={currentUser.isAuthenticated}
            title={title}
            studentMode={studentMode}
          />
        )}
      </div>

      {showTopNav && (
        <nav className={styles.primaryNav} aria-label="Điều hướng chính">
          {resolvedNav.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href ||
                  pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`${styles.navLink} ${active ? styles.activeNav : ""}`.trim()}
                aria-current={active ? "page" : undefined}
              >
                {item.icon ? (
                  <span className={styles.navIcon} aria-hidden="true">
                    {item.icon}
                  </span>
                ) : null}
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      )}

      <div className={styles.actions}>
        {showSearch && (
          <form className={styles.search} role="search" onSubmit={handleSearch}>
            <Search size={17} />
            <label className="sr-only" htmlFor="student-header-search">
              {searchPlaceholder}
            </label>
            <input
              id="student-header-search"
              name="query"
              type="search"
              placeholder={searchPlaceholder}
            />
            <kbd>Enter</kbd>
          </form>
        )}

        {studentMode ? (
          <Link
            className={`${styles.notificationButton} ${
              pathname.startsWith("/notifications") ? styles.activeUtility : ""
            }`.trim()}
            href="/notifications"
            aria-label="Thông báo"
            aria-current={
              pathname.startsWith("/notifications") ? "page" : undefined
            }
            title="Thông báo"
          >
            <Bell size={19} />
            {effectiveCount > 0 && (
              <span className={styles.badge}>
                {effectiveCount > 99 ? "99+" : effectiveCount}
              </span>
            )}
          </Link>
        ) : (
          (effectiveCount > 0 || onNotificationsClick) && (
            <button
              className={styles.notificationButton}
              type="button"
              aria-label={
                effectiveCount > 0
                  ? `${effectiveCount} thông báo chưa đọc`
                  : "Thông báo"
              }
              onClick={onNotificationsClick}
            >
              <Bell size={19} />
              {effectiveCount > 0 && (
                <span className={styles.badge}>
                  {effectiveCount > 99 ? "99+" : effectiveCount}
                </span>
              )}
            </button>
          )
        )}

        <details
          className={`${styles.accountMenu} ${
            pathname.startsWith("/profile") ? styles.activeAccount : ""
          }`.trim()}
        >
          <summary
            aria-label={`Mở menu tài khoản của ${displayName}`}
          >
            <span className={styles.avatar}>
              {user.avatarUrl ? (
                // Keep remote image handling independent of Next image config.
                // eslint-disable-next-line @next/next/no-img-element
                <img src={user.avatarUrl} alt="" />
              ) : (
                initials(displayName)
              )}
            </span>
            <span className={styles.accountCopy}>
              <strong>{displayName}</strong>
              <small>{user.role}</small>
            </span>
            <ChevronDown size={15} />
          </summary>
          <nav className={styles.menuPanel} aria-label="Tài khoản">
            <div className={styles.menuIdentity}>
              <strong>{displayName}</strong>
              <span>{user.role}</span>
            </div>
            {user.role === "Quản trị viên" && (
              <Link href="/admin">
                <ShieldCheck size={15} /> Không gian quản trị
              </Link>
            )}
            {accountItems.map((item) => (
              <Link key={item.href} href={item.href}>
                {item.label}
              </Link>
            ))}
            {AUTH_REQUIRED && (
              <button type="button" onClick={() => void logout()}>
                <LogOut size={15} /> Đăng xuất
              </button>
            )}
          </nav>
        </details>
      </div>

      {showTopNav && (
        <>
          {mobileNavOpen && (
            <button
              type="button"
              className={styles.drawerBackdrop}
              aria-label="Đóng menu"
              onClick={() => setMobileNavOpen(false)}
            />
          )}
          <div
            id="topnav-drawer"
            className={`${styles.mobileDrawer} ${
              mobileNavOpen ? styles.mobileDrawerOpen : ""
            }`.trim()}
            aria-hidden={!mobileNavOpen}
          >
            <nav aria-label="Điều hướng chính (di động)">
              {resolvedNav.map((item) => {
                const active =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname === item.href ||
                      pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`${styles.drawerLink} ${
                      active ? styles.drawerLinkActive : ""
                    }`.trim()}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setMobileNavOpen(false)}
                  >
                    {item.icon ? (
                      <span className={styles.navIcon} aria-hidden="true">
                        {item.icon}
                      </span>
                    ) : null}
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        </>
      )}
    </header>
  );
}
