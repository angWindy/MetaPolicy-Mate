import { test, expect } from "@playwright/test";

const BACKEND = "http://localhost:8000";

async function login(page: Parameters<typeof import("./auth.spec").loginViaApi>[0], email: string, password = "P234@123") {
  const { loginViaApi } = await import("./auth.spec");
  await loginViaApi(page, email, password);
}

test.describe("rbac-ui.spec.ts — UI gating based on role", () => {
  test("USER (hust) redirected from /admin", async ({ page }) => {
    await login(page, "hust@p234.demo");
    await page.goto("/admin");
    // AuthGate enforces role-level redirect; USER should not reach admin.
    await page.waitForURL(/^(?!.*\/admin)/, { timeout: 10_000 });
    expect(page.url()).not.toContain("/admin");
  });

  test("USER (huce) redirected from /admin", async ({ page }) => {
    await login(page, "huce@p234.demo");
    await page.goto("/admin");
    await page.waitForURL(/^(?!.*\/admin)/, { timeout: 10_000 });
    expect(page.url()).not.toContain("/admin");
  });

  test("ADMIN (admin@p234.demo) can access /admin", async ({ page }) => {
    await login(page, "admin@p234.demo");
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/admin/, { timeout: 10_000 });
    await expect(
      page.getByText(/tổng quan|admin|dashboard/i)
    ).toBeVisible({ timeout: 5_000 });
  });

  test("CROSS-SCHOOL admin can access /admin", async ({ page }) => {
    await login(page, "crossschool@p234.demo");
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/admin/, { timeout: 10_000 });
  });

  test("all roles can access /documents", async ({ page }) => {
    for (const email of [
      "admin@p234.demo",
      "hust@p234.demo",
      "huce@p234.demo",
    ]) {
      await login(page, email);
      await page.goto("/documents");
      await expect(page).toHaveURL(/\/documents/, { timeout: 10_000 });
      await expect(page.locator("body")).not.toBeEmpty({ timeout: 5_000 });
      // Clear localStorage for next iteration.
      await page.evaluate(() => {
        localStorage.removeItem("policymate_access_token");
        localStorage.removeItem("policymate_refresh_token");
        localStorage.removeItem("policymate_user_cache");
      });
    }
  });
});
