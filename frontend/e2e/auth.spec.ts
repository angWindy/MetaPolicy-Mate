import { test, expect, type Page } from "@playwright/test";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const BACKEND = "http://localhost:8000";

/**
 * Resolve the seeded demo accounts used by the quick-login buttons on
 * /login. These match the SQL seeded by e2e_full_smoke.py reset phase.
 */
const DEMO_ACCOUNTS = [
  { label: "Admin P-234", email: "admin@p234.demo", password: "P234@123" },
  { label: "HUCE User", email: "huce@p234.demo", password: "P234@123" },
  { label: "HUST User", email: "hust@p234.demo", password: "P234@123" },
  { label: "Cross-School", email: "crossschool@p234.demo", password: "P234@123" },
];

export async function loginViaApi(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  const res = await page.request.post(`${BACKEND}/api/v1/auth/login`, {
    data: {
      email,
      password,
      device_id: `playwright-${email.split("@")[0]}`,
    },
  });
  if (!res.ok()) {
    throw new Error(
      `Login failed for ${email}: ${res.status()} ${await res.text()}`
    );
  }
  const body = await res.json();
  // Persist tokens in localStorage so useCurrentUser picks them up.
  await page.evaluate(
    ({ access_token, refresh_token }) => {
      localStorage.setItem("policymate_access_token", access_token);
      localStorage.setItem("policymate_refresh_token", refresh_token);
    },
    body
  );
}

async function logout(page: Page): Promise<void> {
  await page.evaluate(() => {
    localStorage.removeItem("policymate_access_token");
    localStorage.removeItem("policymate_refresh_token");
    localStorage.removeItem("policymate_user_cache");
  });
  await page.goto("/");
}

// ─── Tests ───────────────────────────────────────────────────────────────────

test.describe("auth.spec.ts — Login / Logout flow", () => {
  test.beforeEach(async ({ page }) => {
    await logout(page);
  });

  test.afterEach(async ({ page }) => {
    await logout(page);
  });

  test("login page loads", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /PolicyMate/i })).toBeVisible();
    await expect(page.getByLabel(/Email/i)).toBeVisible();
    await expect(page.getByLabel(/Mật khẩu/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /đăng nhập/i })).toBeVisible();
  });

  for (const account of DEMO_ACCOUNTS) {
    test(`quick-login button "${account.label}" succeeds`, async ({
      page,
    }) => {
      await page.goto("/login");
      // Click the quick-login button matching the account label.
      const btn = page.getByRole("button", { name: new RegExp(account.label, "i") });
      await expect(btn).toBeVisible();
      const responsePromise = page.waitForResponse(
        (r) =>
          r.url().includes("/auth/login") && r.request().method() === "POST",
        { timeout: 10_000 }
      );
      await btn.click();
      const response = await responsePromise;
      expect(response.status()).toBe(200);
      // After login, expect to stay on the login page but with a redirect
      // in-flight (the login page calls `window.location.href = nextUrl`).
      // Wait for navigation to complete.
      await page.waitForURL(/^(?!.*\/login)/, { timeout: 10_000 });
      // The user should not be on /login anymore.
      expect(page.url()).not.toContain("/login");
    });
  }

  test("wrong password shows error message", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/Email/i).fill("admin@p234.demo");
    await page.getByLabel(/Mật khẩu/i).fill("wrongpassword");
    await page.getByRole("button", { name: /đăng nhập/i }).click();
    // The page shows an error (role=alert on the error message).
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 5_000 });
  });

  test("register link navigates to /register", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: /đăng ký/i }).click();
    await expect(page).toHaveURL(/\/register/);
  });

  test("logout clears session and redirects to login", async ({ page }) => {
    // Login first.
    await loginViaApi(page, "admin@p234.demo", "P234@123");
    await page.goto("/");
    // Navigate to logout.
    await page.goto("/logout");
    await page.waitForURL(/\/login/, { timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });

  test("authenticated user visiting /login is redirected to home", async ({
    page,
  }) => {
    await loginViaApi(page, "admin@p234.demo", "P234@123");
    await page.goto("/login");
    // After hydration, AuthGate should redirect away from /login.
    await page.waitForURL(/^(?!.*\/login)/, { timeout: 10_000 });
    expect(page.url()).not.toContain("/login");
  });
});
