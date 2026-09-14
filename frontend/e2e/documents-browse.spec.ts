import { test, expect } from "@playwright/test";

const BACKEND = "http://localhost:8000";

async function login(page: Parameters<typeof import("./auth.spec").loginViaApi>[0], email: string, password = "P234@123") {
  const { loginViaApi } = await import("./auth.spec");
  await loginViaApi(page, email, password);
}

test.describe("documents-browse.spec.ts — Document browsing flow", () => {
  test("unauthenticated user is redirected to /login", async ({ page }) => {
    await page.goto("/documents");
    await page.waitForURL(/\/login/, { timeout: 10_000 });
  });

  test("HUST user can see the documents list page", async ({ page }) => {
    await login(page, "hust@p234.demo");
    await page.goto("/documents");
    await expect(page.getByText(/thư viện/i)).toBeVisible({ timeout: 10_000 });
  });

  test("documents list loads without crashing when empty", async ({ page }) => {
    await login(page, "admin@p234.demo");
    await page.goto("/documents");
    // Either the empty state or the document list should appear.
    const content = page.locator("body");
    await expect(
      content.getByText(/thư viện/i).or(content.getByText(/chưa có văn bản/i))
    ).toBeVisible({ timeout: 10_000 });
  });

  test("user can navigate from /documents to /admin", async ({ page }) => {
    await login(page, "admin@p234.demo");
    await page.goto("/documents");
    // The authenticated layout should have a sidebar link to admin.
    const adminLink = page.getByRole("link", { name: /quản trị/i }).or(
      page.locator('[href="/admin"]')
    );
    await expect(adminLink).toBeVisible({ timeout: 5_000 });
  });
});
