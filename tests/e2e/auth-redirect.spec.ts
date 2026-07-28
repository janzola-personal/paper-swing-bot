import { test, expect } from "@playwright/test";

/**
 * Smoke: unauthenticated browser hitting /dashboard lands on /login.
 * Run: npx playwright test tests/e2e/auth-redirect.spec.ts
 * Requires: npm run build && npm run start (or webServer in config).
 */
test("unauthenticated /dashboard redirects to /login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: /Paper Swing Bot/i })).toBeVisible();
});

test("unauthenticated /api/status returns 401", async ({ request }) => {
  const res = await request.get("/api/status");
  expect(res.status()).toBe(401);
});
