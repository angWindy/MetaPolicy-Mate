const DEFAULT_API_URL = "http://localhost:8000";

const ACCESS_TOKEN_KEY = "policymate_access_token";
const REFRESH_TOKEN_KEY = "policymate_refresh_token";
const USER_CACHE_KEY = "policymate_user_cache";
const LOGIN_PATH = "/login";

// Module-level sentinel to serialize concurrent refresh attempts and prevent
// redirect storms when many requests fail simultaneously.
let _refreshPromise: Promise<void> | null = null;
// Guards against throwing inside the finally block (navigation may fail).
let _redirectPending = false;

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly payload?: unknown,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

function buildUrl(path: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL;
  const normalizedBase = baseUrl.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

/**
 * Attempts to obtain a fresh access token using the stored refresh token.
 *
 * - On 2xx: stores the new token pair and returns normally.
 * - On 401 / missing refresh token: clears all auth data and schedules a
 *   redirect to /login.  All callers that hit a 401 will wait for this
 *   function to settle before re-throwing, so the user is redirected only
 *   once regardless of how many in-flight requests fail simultaneously.
 * - On network / server errors: releases the lock and re-throws so the
 *   original caller handles the error.
 */
async function _refreshTokens(): Promise<void> {
  // Another request beat us — wait for it to finish and check the outcome.
  if (_refreshPromise) {
    await _refreshPromise;
    // If the previous refresh cleared tokens, propagate that by throwing.
    if (_redirectPending) throw new ApiClientError("Session expired.", 401);
    return;
  }

  // Serialize refresh attempts so we never fire two at the same time.
  _refreshPromise = (async () => {
    const refreshToken =
      typeof window !== "undefined"
        ? window.localStorage.getItem(REFRESH_TOKEN_KEY)
        : null;

    if (!refreshToken) {
      _clearAuth();
      return;
    }

    try {
      const res = await fetch(buildUrl("/api/v1/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken, device_id: "web-login" }),
      });

      if (!res.ok) {
        // Refresh token is also invalid (expired / revoked / replayed).
        _clearAuth();
        return;
      }

      const data: { access_token: string; refresh_token: string } = await res.json();

      if (typeof window !== "undefined") {
        window.localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
        window.localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
        window.dispatchEvent(new Event("storage"));
      }
    } catch {
      // Network error — release lock so callers can decide individually.
      _refreshPromise = null;
      throw new ApiClientError("Không thể kết nối đến hệ thống. Vui lòng kiểm tra mạng và thử lại.", 0);
    }
  })();

  try {
    await _refreshPromise;
  } catch (thrown) {
    // Network error was re-thrown inside; let caller handle it.
    _refreshPromise = null;
    throw thrown;
  } finally {
    _refreshPromise = null;
  }
}

/** Removes all auth data from localStorage and redirects to /login once. */
function _clearAuth(): void {
  if (typeof window === "undefined") return;
  if (_redirectPending) return;
  _redirectPending = true;
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    window.localStorage.removeItem(USER_CACHE_KEY);
    window.dispatchEvent(new Event("storage"));
    window.location.href = LOGIN_PATH;
  } catch {
    // Navigation may fail in test / non-browser environments.
    _redirectPending = false;
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (typeof window !== "undefined") {
    const accessToken = window.localStorage.getItem(ACCESS_TOKEN_KEY);
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  }

  // Development-only identity headers match the backend's local bypass mode.
  const devUserId = process.env.NEXT_PUBLIC_DEV_USER_ID;
  if (devUserId) {
    headers.set("X-User-Id", devUserId);
    headers.set("X-Tenant-Id", process.env.NEXT_PUBLIC_DEV_TENANT_ID ?? "hust");
    headers.set("X-Department", process.env.NEXT_PUBLIC_DEV_DEPARTMENT ?? "TCCB");
    headers.set("X-Roles", process.env.NEXT_PUBLIC_DEV_ROLES ?? "data_owner");
  }

  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response = await fetch(buildUrl(path), {
    ...init,
    headers,
  });

  // Auto-refresh once when the token has expired.
  if (response.status === 401 && !_redirectPending) {
    try {
      await _refreshTokens();
      // Retry once with the new token (fresh headers read from localStorage).
      const newAccessToken =
        typeof window !== "undefined"
          ? window.localStorage.getItem(ACCESS_TOKEN_KEY)
          : null;
      if (newAccessToken) {
        headers.set("Authorization", `Bearer ${newAccessToken}`);
        response = await fetch(buildUrl(path), { ...init, headers });
      }
    } catch {
      // Refresh failed (network error) — fall through to throw below so the
      // original ApiClientError is propagated.  Session-expired redirects
      // are handled inside _refreshTokens / _clearAuth.
    }
  }

  if (!response.ok) {
    let payload: unknown = undefined;
    try {
      payload = await response.json();
    } catch {
      // ignore JSON parse errors
    }
    const detail =
      typeof payload === "object" && payload !== null
        ? (payload as { detail?: string; message?: string })
        : {};
    throw new ApiClientError(
      detail.detail ??
        detail.message ??
        "Không thể hoàn thành yêu cầu. Vui lòng thử lại.",
      response.status,
      payload,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
