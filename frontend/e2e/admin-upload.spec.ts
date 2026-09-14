import { test, expect } from "@playwright/test";

const BACKEND = "http://localhost:8000";

async function login(page: Parameters<typeof import("./auth.spec").loginViaApi>[0], email: string, password = "P234@123") {
  const { loginViaApi } = await import("./auth.spec");
  await loginViaApi(page, email, password);
}

test.describe("admin-upload.spec.ts — Admin upload + delete flow", () => {
  test("unauthenticated user redirected from /admin to /login", async ({
    page,
  }) => {
    await page.goto("/admin");
    await page.waitForURL(/\/login/, { timeout: 10_000 });
  });

  test("HUST (USER) user is redirected from /admin by AuthGate", async ({
    page,
  }) => {
    await login(page, "hust@p234.demo");
    await page.goto("/admin");
    // AuthGate should redirect USER away from /admin.
    await page.waitForURL(/^(?!.*\/admin)/, { timeout: 10_000 });
    expect(page.url()).not.toContain("/admin");
  });

  test("admin user can see the admin dashboard", async ({ page }) => {
    await login(page, "admin@p234.demo");
    await page.goto("/admin");
    await expect(
      page.getByText(/tổng quan|admin|dashboard/i)
    ).toBeVisible({ timeout: 10_000 });
  });

  test("admin can navigate to /admin/documents", async ({ page }) => {
    await login(page, "admin@p234.demo");
    await page.goto("/admin/documents");
    // The page should load without crashing (may be empty).
    await expect(page.locator("body")).not.toBeEmpty({ timeout: 10_000 });
  });
});
