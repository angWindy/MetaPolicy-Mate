import { test, expect } from "@playwright/test";

const BACKEND = "http://localhost:8000";

async function login(page: Parameters<typeof import("./auth.spec").loginViaApi>[0], email: string, password = "P234@123") {
  const { loginViaApi } = await import("./auth.spec");
  await loginViaApi(page, email, password);
}

test.describe("ask-rag.spec.ts — RAG ask flow", () => {
  test("unauthenticated user redirected from /ask to /login", async ({
    page,
  }) => {
    await page.goto("/ask");
    await page.waitForURL(/\/login/, { timeout: 10_000 });
  });

  test("HUST user sees the ask page", async ({ page }) => {
    await login(page, "hust@p234.demo");
    await page.goto("/ask");
    // The ask page should load (title or composer visible).
    const heading = page.getByRole("heading", { name: /hỏi/i });
    const placeholder = page.getByPlaceholder(/câu hỏi/i);
    await expect(heading.or(placeholder)).toBeVisible({ timeout: 10_000 });
  });

  test("student /ask page loads (alternate route)", async ({ page }) => {
    await login(page, "hust@p234.demo");
    await page.goto("/student/ask");
    const heading = page.getByRole("heading", { name: /hỏi/i });
    const placeholder = page.getByPlaceholder(/câu hỏi/i);
    await expect(heading.or(placeholder)).toBeVisible({ timeout: 10_000 });
  });
});
