/**
 * Authentication is opt-in while the project is being developed as a
 * frontend-only prototype. Set NEXT_PUBLIC_AUTH_REQUIRED=true when the real
 * backend and login flow are available.
 */
export const AUTH_REQUIRED = process.env.NEXT_PUBLIC_AUTH_REQUIRED === "true";
