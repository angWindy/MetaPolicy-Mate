"use client";

import { useSyncExternalStore } from "react";

import type { UserProfileCardUser } from "../components/layout";
import { apiRequest } from "../lib/api";

const TOKEN_KEY = "policymate_access_token";
const USER_CACHE_KEY = "policymate_user_cache";

export type CurrentUser = UserProfileCardUser & {
  /** Raw JWT role claim (e.g. "ADMIN" or "USER"). */
  rawRole: string | null;
  /** E-mail claim from JWT, when present. */
  email: string | null;
  /** UUID subject claim. */
  userId: string | null;
  /** School UUID from JWT. */
  schoolId: string | null;
  /**
   * True iff the user has a valid JWT in localStorage. Stays false until
   * the hook's first sync runs, then mirrors the token's actual validity.
   */
  isAuthenticated: boolean;
  /**
   * True once the hook has read localStorage on the client at least once.
   * Pages that conditionally redirect to /login must wait for this flag
   * before deciding, otherwise they race the initial ANONYMOUS state and
   * bounce a freshly-authenticated user back to the login page.
   */
  isLoaded: boolean;
};

const ANONYMOUS: CurrentUser = {
  name: "",
  role: "",
  studentId: undefined,
  department: undefined,
  rawRole: null,
  email: null,
  userId: null,
  schoolId: null,
  isAuthenticated: false,
  isLoaded: false,
};

/**
 * Hydrated-but-still-anonymous state — what we render the very first
 * time the hook runs on the client when localStorage has no token.
 * Identical to ANONYMOUS except `isLoaded=true`, so AuthGate does not
 * bounce the user to /login when they simply have no session.
 */
const ANONYMOUS_LOADED: CurrentUser = { ...ANONYMOUS, isLoaded: true };

function safeBase64Decode(input: string): string | null {
  try {
    // JWT uses URL-safe base64: replace - with + and _ with /
    let normalized = input.replace(/-/g, "+").replace(/_/g, "/");
    const paddingNeeded = (4 - (normalized.length % 4)) % 4;
    normalized += "=".repeat(paddingNeeded);
    if (typeof atob === "function") {
      return atob(normalized);
    }
    return null;
  } catch {
    return null;
  }
}

function decodeJwtClaims(
  token: string,
): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const decoded = safeBase64Decode(parts[1]);
  if (decoded === null) return null;
  try {
    const parsed = JSON.parse(decoded);
    if (parsed && typeof parsed === "object") {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // fall through
  }
  return null;
}

function mapRole(role: string): string {
  const upper = role.toUpperCase();
  if (upper === "ADMIN") return "Quản trị viên";
  if (upper === "USER") return "Người dùng";
  // Legacy role codes kept for backward-compatibility with old JWTs.
  // New tokens always carry ADMIN or USER.
  if (upper === "REVIEWER") return "Người dùng";
  if (upper === "LECTURER") return "Người dùng";
  if (upper === "LEADER") return "Người dùng";
  return role;
}

function readCachedUser(): CurrentUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && parsed.isAuthenticated) {
      return parsed as CurrentUser;
    }
  } catch {
    // ignore
  }
  return null;
}

function writeCachedUser(user: CurrentUser | null): void {
  if (typeof window === "undefined") return;
  try {
    if (user) {
      window.localStorage.setItem(USER_CACHE_KEY, JSON.stringify(user));
    } else {
      window.localStorage.removeItem(USER_CACHE_KEY);
    }
  } catch {
    // ignore
  }
}

function readUserFromToken(
  token: string | null,
  cached: CurrentUser | null,
): CurrentUser {
  if (!token) return ANONYMOUS;
  const claims = decodeJwtClaims(token);
  if (!claims) return ANONYMOUS;

  const roleClaim = (claims.role ?? claims.Role ?? "").toString();
  const email = (claims.email ?? "").toString();
  const subject = (claims.sub ?? claims.user_id ?? "").toString();
  const schoolIdRaw = (
    claims.SchoolId ?? claims.school_id ?? ""
  ).toString();
  const nameClaim = (claims.full_name ?? claims.name ?? "").toString();
  const departmentClaim = (
    claims.department ?? claims.Department ?? ""
  ).toString();

  // Prefer cached user info (has full_name from API) if subject matches
  if (cached && cached.userId === subject) {
    return cached;
  }

  return {
    name: nameClaim || email.split("@")[0] || "Người dùng",
    role: mapRole(roleClaim),
    studentId: undefined,
    department: departmentClaim || undefined,
    rawRole: roleClaim || null,
    email: email || null,
    userId: subject || null,
    schoolId: schoolIdRaw || null,
    isAuthenticated: true,
    isLoaded: true,
  };
}

async function fetchUserFromApi(userId: string): Promise<CurrentUser | null> {
  try {
    const res = await apiRequest<{
      id: string;
      email: string;
      full_name?: string | null;
      department_id?: string | null;
      role?: string | null;
    }>(`/api/v1/users/${userId}`);
    if (!res) return null;
    // API returns flat fields; map them to the CurrentUser shape so the
    // cached entry matches the discriminated type used downstream.
    return {
      name: res.full_name ?? "",
      role: res.role ?? "",
      studentId: undefined,
      department: res.department_id ?? undefined,
      rawRole: res.role ?? null,
      email: res.email,
      userId: res.id,
      schoolId: null,
      isAuthenticated: true,
      isLoaded: true,
    };
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Module-level singleton store. The previous implementation created a
// separate React state per hook consumer, which let AuthGate, the page,
// and the AuthenticatedLayout race against each other: one would see
// isLoaded=true while another still saw isLoaded=false, leading to
// blank admin pages, redirect loops on /documents, and "Bạn chưa đăng
// nhập" flashes on /profile.
//
// The fix is to share one store across every consumer via
// useSyncExternalStore. State hydrates synchronously on module load
// from localStorage so the very first client render already reflects
// the real session, and external `storage` events / explicit
// `notifyAuthChanged()` calls trigger a re-render in every consumer.
// ─────────────────────────────────────────────────────────────────────────

let _state: CurrentUser = ANONYMOUS;
const _listeners = new Set<() => void>();
let _clientHydrated = false;
let _storageListenerInstalled = false;
let _inflightApiMerge: Promise<void> | null = null;

function getSnapshot(): CurrentUser {
  return _state;
}

/**
 * Server snapshot for `useSyncExternalStore` — must match the very first
 * client render. During the first render on the client we still return
 * ANONYMOUS (matching SSR), then trigger hydration synchronously below.
 */
function getServerSnapshot(): CurrentUser {
  return ANONYMOUS;
}

function subscribe(listener: () => void): () => void {
  _listeners.add(listener);
  return () => {
    _listeners.delete(listener);
  };
}

function setState(next: CurrentUser): void {
  if (next === _state) return;
  _state = next;
  for (const listener of _listeners) {
    listener();
  }
}

function installStorageListener(): void {
  if (_storageListenerInstalled) return;
  if (typeof window === "undefined") return;
  _storageListenerInstalled = true;
  window.addEventListener("storage", (event) => {
    // React to (a) native cross-tab StorageEvents for our auth keys,
    // and (b) manually-dispatched Events fired by the login / logout
    // pages to notify other tabs in the same window. For native
    // events we still filter by key so unrelated localStorage writes
    // don't trigger an unnecessary API round-trip.
    const isManual = !(event instanceof StorageEvent);
    if (
      !isManual &&
      event.key !== null &&
      event.key !== TOKEN_KEY &&
      event.key !== USER_CACHE_KEY
    ) {
      return;
    }
    void hydrateFromBrowser({ fireApiMerge: true });
  });
}

/**
 * Synchronous one-shot hydration. Reads the token and cached user from
 * localStorage and assigns the result to `_state` before the first React
 * render runs, so the initial paint already reflects the real session
 * instead of flashing "Khách" until a microtask eventually fires.
 *
 * Safe to call multiple times: the state is only rewritten if the new
 * value differs from the previous one (see `setState`).
 */
function hydrateFromBrowserSync(): void {
  if (typeof window === "undefined") return;
  const token = window.localStorage.getItem(TOKEN_KEY);
  const cached = readCachedUser();
  if (!token) {
    if (cached) writeCachedUser(null);
    setState(ANONYMOUS_LOADED);
    return;
  }
  setState(readUserFromToken(token, cached));
}

async function hydrateFromBrowser(opts: {
  fireApiMerge?: boolean;
} = {}): Promise<void> {
  if (typeof window === "undefined") return;
  const token = window.localStorage.getItem(TOKEN_KEY);
  const cached = readCachedUser();

  // No token: mark the user as loaded-but-anonymous so AuthGate does
  // not block forever waiting for `isLoaded=true`.
  if (!token) {
    if (cached) writeCachedUser(null);
    setState(ANONYMOUS_LOADED);
    return;
  }

  const fromToken = readUserFromToken(token, cached);
  setState(fromToken);

  if (!opts.fireApiMerge) return;
  if (_inflightApiMerge) return _inflightApiMerge;

  const claims = decodeJwtClaims(token);
  const userId = (claims?.sub ?? claims?.user_id ?? "").toString();
  if (!userId) return;

  _inflightApiMerge = (async () => {
    const apiUser = await fetchUserFromApi(userId);
    if (!apiUser) return;
    // Re-read token-derived data fresh because the active token may
    // have changed while the API call was in flight.
    const freshToken =
      typeof window !== "undefined"
        ? window.localStorage.getItem(TOKEN_KEY)
        : null;
    if (!freshToken) return;
    const freshFromToken = readUserFromToken(freshToken, cached);
    const merged: CurrentUser = {
      ...freshFromToken,
      name: apiUser.name || freshFromToken.name,
      email: apiUser.email || freshFromToken.email,
    };
    setState(merged);
    writeCachedUser(merged);
  })()
    .catch(() => {
      // swallow — cache fallback is good enough
    })
    .finally(() => {
      _inflightApiMerge = null;
    });
  return _inflightApiMerge;
}

/**
 * Public API for code paths that mutate auth state imperatively
 * (e.g. login page after a successful login, logout, or test setup).
 * Notifies every useCurrentUser consumer so the new auth state lands
 * in a single render cycle.
 */
export function notifyAuthChanged(): void {
  if (typeof window === "undefined") return;
  void hydrateFromBrowser({ fireApiMerge: true });
}

export function useCurrentUser(): CurrentUser {
  // Subscribe via useSyncExternalStore — the React-recommended pattern
  // for sharing state across many components. The store itself is the
  // module-level singleton at the top of this file, so every consumer
  // sees the same snapshot and the same auth state.
  //
  // Hydration strategy: the module body below hydrates _state
  // synchronously from localStorage when it loads on the client, so
  // by the time the very first useSyncExternalStore snapshot is read
  // it already reflects the real session. We still call
  // `installStorageListener()` here for safety in case the module
  // body hasn't run yet (e.g. in a test harness that stubs window
  // after import), and we kick off the optional API merge in a
  // microtask so it never blocks the first render.
  const snapshot = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );
  if (!_clientHydrated) {
    _clientHydrated = true;
    installStorageListener();
    // Kick off the (optional) API merge to enrich the user from
    // /api/v1/users/{id} when the token alone doesn't carry a
    // full_name. This is best-effort: if the endpoint rejects the
    // caller (e.g. LECTURER hitting `user.manage`) the cache fallback
    // in hydrateFromBrowser keeps the JWT-derived name visible.
    queueMicrotask(() => {
      void hydrateFromBrowser({ fireApiMerge: true });
    });
  }
  return snapshot;
}

/**
 * Imperative bootstrap helper. The module already installs its storage
 * listener and hydrates synchronously as soon as it loads on the
 * client, so most callers never need this. Tests and auth-mutating
 * code paths (login, logout, refresh) may call it explicitly to force
 * an immediate re-sync without waiting for the microtask.
 */
export function startClientHydration(): void {
  if (_clientHydrated) return;
  _clientHydrated = true;
  installStorageListener();
  hydrateFromBrowserSync();
  void hydrateFromBrowser({ fireApiMerge: true });
}

// Install the storage listener and hydrate state synchronously at
// module load so the very first client render reflects the real
// session. Without this, the header would flash "Khách" on every page
// load until the microtask in useCurrentUser eventually rehydrates.
// Guarded by `typeof window` so this is a no-op during SSR.
if (typeof window !== "undefined") {
  installStorageListener();
  hydrateFromBrowserSync();
}

/** Synchronous helper used inside non-React helpers. */
export function readJwtClaims(
  token: string | null,
): Record<string, unknown> | null {
  if (!token) return null;
  return decodeJwtClaims(token);
}

export const CURRENT_USER_TOKEN_KEY = TOKEN_KEY;
