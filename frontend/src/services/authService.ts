import { apiRequest, ApiClientError } from "@/lib/api";
import { notifyAuthChanged } from "@/hooks/useCurrentUser";
import type { RegisterResponse } from "@/lib/api";

const ACCESS_TOKEN_KEY = "policymate_access_token";
const REFRESH_TOKEN_KEY = "policymate_refresh_token";

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  expires_at?: string;
};

/**
 * Authentication service for the demo frontend.
 *
 * Wires up login / register / logout against the backend and keeps the
 * client-side session cache in lock-step with `useCurrentUser`. The
 * demo's `useCurrentUser` already has its own internal hydrate-from-
 * localStorage logic; we trigger `notifyAuthChanged()` after each
 * mutation so other tabs and the layout components re-render with the
 * new auth state.
 */
export const authService = {
  async login(email: string, password: string): Promise<AuthTokens> {
    const tokens = await apiRequest<AuthTokens>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        device_id:
          typeof window !== "undefined"
            ? `web-${window.navigator.userAgent.slice(0, 32)}`
            : "web-login",
      }),
    });
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
      window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    }
    notifyAuthChanged();
    return tokens;
  },

  async register(input: {
    email: string;
    password: string;
    full_name: string;
    school_code: string;
  }): Promise<RegisterResponse> {
    const response = await apiRequest<RegisterResponse>(
      "/api/v1/auth/register",
      {
        method: "POST",
        body: JSON.stringify(input),
      },
    );
    if (typeof window !== "undefined" && "access_token" in response) {
      const tokens = response as unknown as AuthTokens;
      window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
      window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
      notifyAuthChanged();
    }
    return response;
  },

  async logout(): Promise<void> {
    if (typeof window === "undefined") return;
    const refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY);
    try {
      if (refreshToken) {
        await apiRequest<void>("/api/v1/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshToken }),
        }).catch(() => undefined);
      }
    } finally {
      window.localStorage.removeItem(ACCESS_TOKEN_KEY);
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
      notifyAuthChanged();
    }
  },
};

// Avoid an unused-import warning: ApiClientError is re-exported so
// callers can do `import { authService, ApiClientError } from "..."`.
export { ApiClientError };
